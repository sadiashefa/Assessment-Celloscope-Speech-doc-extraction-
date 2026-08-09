"""
Gemini transcription adapter via OpenRouter.

Uses google/gemini-2.5-flash (multimodal) through OpenRouter's chat/completions
endpoint. Audio is base64-encoded and sent as an input_audio content block.

The prompt instructs the model to:
  - Transcribe Bengali or English based on the language field
  - Auto-detect language when language="auto"
  - Return is_speech_detected=false for silence, noise, music, or static
  - Return strict JSON only — no markdown, no prose

Duration is computed locally via mutagen (no extra API call needed).
"""

import base64
import io
import json
import os
import re
import struct
import tempfile
import wave

import httpx
import mutagen
import mutagen.mp3
import mutagen.mp4
import mutagen.ogg
import mutagen.flac

from adapters.base import AdapterError, TranscriptionAdapter, TranscriptionResult

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_SYSTEM_PROMPT = """\
You are a precise audio transcription engine.

Your only job is to listen to audio and return a JSON object — no markdown, \
no explanation, nothing else.

CRITICAL RULE — check this FIRST before anything else:
If the audio contains ONLY silence, background noise, static, hiss, music, \
ambient sounds, or any non-human-speech content, you MUST return:
{"transcript": "", "detected_language": null, "is_speech_detected": false}
Do NOT transcribe noise, music, or silence as words. Do NOT hallucinate words \
that are not present in the audio.

Only if there is clear, intelligible human speech in the audio, transcribe it.

Output schema (return exactly this, no extra keys):
{
  "transcript": "<the exact spoken words verbatim, empty string if no speech>",
  "detected_language": "<ISO 639-1 code e.g. en or bn, or null if no speech>",
  "is_speech_detected": <true or false>
}

Additional rules:
- transcript must contain the exact words spoken — do not paraphrase or summarise.
- For Bengali audio, transcribe in Bengali Unicode script (e.g. রোগীর হিমোগ্লোবিন...).
- For English audio, transcribe in English.
- Never guess words you cannot hear. If a word is inaudible, omit it.
- detected_language is the language actually spoken, not the language requested.
"""


def _language_instruction(language: str) -> str:
    """
    Build a language hint for the model.
    Language detection always happens automatically — the hint only helps
    the model decide which script to use for transcription output.
    """
    if language == "bn":
        return (
            "The user indicated Bengali (বাংলা) audio. "
            "First verify there is actual speech — if not, return is_speech_detected=false. "
            "If speech is present, transcribe in Bengali Unicode script."
        )
    if language == "en":
        return (
            "The user indicated English audio. "
            "First verify there is actual speech — if not, return is_speech_detected=false. "
            "If speech is present, transcribe in English."
        )
    # auto (default)
    return (
        "Auto-detect the language from the audio. "
        "First check for the presence of speech. "
        "If no speech (silence, noise, music): return is_speech_detected=false. "
        "If speech is present: identify the language and transcribe accurately."
    )


def _extract_json(text: str) -> dict:
    """Strip markdown fences and parse JSON from model response."""
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text.strip())
    return json.loads(text)


def _m4a_duration(data: bytes) -> float | None:
    """
    Parse M4A/MP4 duration in pure Python by reading the ISO Base Media
    File Format (ISOBMFF) box structure.

    Scans top-level boxes for 'moov', then scans moov for 'mvhd'.
    The mvhd box contains timescale + duration — no external library needed.
    Works regardless of whether moov is at the start or end of the file.
    """
    def _read_boxes(buf: bytes):
        """Yield (name, payload) for each box in buf."""
        i = 0
        n = len(buf)
        while i + 8 <= n:
            size = struct.unpack(">I", buf[i : i + 4])[0]
            name = buf[i + 4 : i + 8]
            if size == 1:
                # 64-bit extended size
                if i + 16 > n:
                    break
                size = struct.unpack(">Q", buf[i + 8 : i + 16])[0]
                payload = buf[i + 16 : i + size]
            elif size == 0:
                # Box extends to end of file
                payload = buf[i + 8 :]
                yield name, payload
                break
            elif size < 8:
                break
            else:
                payload = buf[i + 8 : i + size]
            yield name, payload
            i += size

    for name, payload in _read_boxes(data):
        if name == b"moov":
            for sub_name, sub_payload in _read_boxes(payload):
                if sub_name == b"mvhd":
                    if len(sub_payload) < 4:
                        return None
                    version = sub_payload[0]
                    if version == 1 and len(sub_payload) >= 32:
                        timescale = struct.unpack(">I", sub_payload[20:24])[0]
                        duration = struct.unpack(">Q", sub_payload[24:32])[0]
                    elif version == 0 and len(sub_payload) >= 20:
                        timescale = struct.unpack(">I", sub_payload[12:16])[0]
                        duration = struct.unpack(">I", sub_payload[16:20])[0]
                    else:
                        return None
                    if timescale > 0:
                        return duration / timescale
    return None


def _get_duration(audio_bytes: bytes, filename: str = "") -> float:
    """
    Compute audio duration in seconds.

    Uses format-specific readers in order of reliability:
    WAV  → stdlib wave (always reliable)
    MP3  → mutagen.mp3.MP3
    M4A/MP4/AAC → mutagen.mp4.MP4
    OGG  → mutagen.ogg
    FLAC → mutagen.flac.FLAC
    Other → mutagen.File with filename hint
    Fallback → 0.0
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    # WAV: stdlib — works 100% from raw bytes
    if ext == "wav" or audio_bytes[:4] == b"RIFF":
        try:
            with wave.open(io.BytesIO(audio_bytes)) as wf:
                return wf.getnframes() / wf.getframerate()
        except Exception:
            pass

    # MP3
    if ext in ("mp3", "mpeg", "mpga"):
        try:
            return float(mutagen.mp3.MP3(io.BytesIO(audio_bytes)).info.length)
        except Exception:
            pass

    # M4A / MP4 / AAC — parse the ISOBMFF box structure in pure Python.
    # mutagen.mp4.MP4 and BytesIO don't mix reliably; the custom parser reads
    # the mvhd box directly from the raw bytes — no temp files, no ffmpeg.
    if ext in ("m4a", "m4b", "mp4", "aac") or audio_bytes[4:8] in (b"ftyp", b"moov"):
        result = _m4a_duration(audio_bytes)
        if result is not None:
            return result

    # OGG
    if ext == "ogg":
        try:
            return float(mutagen.ogg.OggFileType(io.BytesIO(audio_bytes)).info.length)
        except Exception:
            pass

    # FLAC
    if ext == "flac":
        try:
            return float(mutagen.flac.FLAC(io.BytesIO(audio_bytes)).info.length)
        except Exception:
            pass

    # Generic fallback — try sniffing from content
    try:
        audio = mutagen.File(io.BytesIO(audio_bytes))
        if audio and hasattr(audio.info, "length"):
            return float(audio.info.length)
    except Exception:
        pass

    return 0.0


class GeminiTranscriptionAdapter:
    """
    Transcribes audio via Gemini 2.5 Flash on OpenRouter.
    Satisfies TranscriptionAdapter Protocol.
    """

    def __init__(self, api_key: str, model: str = "google/gemini-2.5-flash") -> None:
        self._api_key = api_key
        self._model = model

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        language: str,
    ) -> TranscriptionResult:
        audio_b64 = base64.standard_b64encode(audio_bytes).decode("ascii")
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "mp3"

        payload = {
            "model": self._model,
            "temperature": 0,  # deterministic — we want exact transcription
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        # Audio block — Gemini reads this natively
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": audio_b64,
                                "format": ext,
                            },
                        },
                        # Language hint + task instruction
                        {
                            "type": "text",
                            "text": (
                                f"{_language_instruction(language)}\n\n"
                                "Now transcribe the audio and return the JSON object."
                            ),
                        },
                    ],
                },
            ],
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                response = await client.post(
                    _OPENROUTER_URL, headers=headers, json=payload
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise AdapterError(
                f"OpenRouter transcription error {exc.response.status_code}: "
                f"{exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            raise AdapterError(f"OpenRouter network error: {exc}") from exc

        raw_content = response.json()["choices"][0]["message"]["content"]

        try:
            data = _extract_json(raw_content)
        except (json.JSONDecodeError, KeyError) as exc:
            raise AdapterError(
                f"Gemini returned non-JSON response: {raw_content[:200]}"
            ) from exc

        transcript: str = data.get("transcript", "").strip()
        is_speech: bool = bool(data.get("is_speech_detected", bool(transcript)))
        detected_language: str | None = data.get("detected_language") or (
            None if not is_speech else language if language != "auto" else None
        )

        return TranscriptionResult(
            transcript=transcript,
            detected_language=detected_language,
            duration_seconds=_get_duration(audio_bytes, filename),
            provider="openrouter-gemini",
            is_speech_detected=is_speech,
        )


# Runtime protocol check
assert isinstance(GeminiTranscriptionAdapter(api_key=""), TranscriptionAdapter)

