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

Output schema (return exactly this, no extra keys):
{
  "transcript": "<the exact spoken words verbatim>",
  "detected_language": "<ISO 639-1 code, e.g. en or bn, or null if no speech>",
  "is_speech_detected": <true or false>
}

Rules:
- transcript must contain the exact words spoken. Do not paraphrase or summarise.
- If the audio is silence, white noise, background noise, music, or static with \
no intelligible human speech: set is_speech_detected to false, transcript to "", \
and detected_language to null.
- detected_language must be the ISO 639-1 code of the language actually spoken \
(not the language requested by the user).
- For Bengali audio, transcribe in Bengali Unicode script (e.g. রোগীর হিমোগ্লোবিন...).
- For English audio, transcribe in English.
- Never guess words you cannot hear. If a word is inaudible, omit it rather than guess.
"""


def _language_instruction(language: str) -> str:
    """Return a user-facing language hint to prepend to the transcription request."""
    if language == "bn":
        return (
            "Language hint: the speaker is using Bengali (বাংলা). "
            "Transcribe every word in Bengali Unicode script. "
            "If there is no speech, return is_speech_detected as false."
        )
    if language == "en":
        return (
            "Language hint: the speaker is using English. "
            "Transcribe every word in English. "
            "If there is no speech, return is_speech_detected as false."
        )
    # auto
    return (
        "Language hint: detect the language automatically from the audio. "
        "If there is no intelligible speech (silence, noise, music), "
        "return is_speech_detected as false."
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

