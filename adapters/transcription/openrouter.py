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
import re

import httpx
import mutagen

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


def _get_duration(audio_bytes: bytes) -> float:
    """Compute audio duration locally via mutagen — no extra API call."""
    audio = mutagen.File(io.BytesIO(audio_bytes))
    if audio and hasattr(audio.info, "length"):
        return float(audio.info.length)
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
            duration_seconds=_get_duration(audio_bytes),
            provider="openrouter-gemini",
            is_speech_detected=is_speech,
        )


# Runtime protocol check
assert isinstance(GeminiTranscriptionAdapter(api_key=""), TranscriptionAdapter)

