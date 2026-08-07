"""
Groq Whisper transcription adapter.

Calls api.groq.com/openai/v1/audio/transcriptions using httpx (async).
Uses verbose_json response format to get duration and language in a single call.

Language mapping: the Groq Whisper API uses full English names for the
language parameter (e.g. "bengali"), not ISO codes. We map "bn" → "bengali"
and "en" → "english" before sending. "auto" omits the parameter entirely.
"""

import httpx

from adapters.base import TranscriptionAdapter, TranscriptionResult

_GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
_MODEL = "whisper-large-v3-turbo"

_LANGUAGE_MAP: dict[str, str] = {
    "bn": "bengali",
    "en": "english",
}

# Tokens Whisper emits for non-speech content
_NON_SPEECH_TOKENS = {"[music]", "[noise]", "[silence]", "[blank_audio]", "(music)", "(noise)"}


def _is_speech(transcript: str) -> bool:
    stripped = transcript.strip().lower()
    if not stripped:
        return False
    return stripped not in _NON_SPEECH_TOKENS


class GroqTranscriptionAdapter:
    """Calls Groq Whisper API; satisfies TranscriptionAdapter Protocol."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        language: str,
    ) -> TranscriptionResult:
        headers = {"Authorization": f"Bearer {self._api_key}"}

        data: dict[str, str] = {
            "model": _MODEL,
            "response_format": "verbose_json",
        }
        if language != "auto":
            data["language"] = _LANGUAGE_MAP.get(language, language)

        files = {"file": (filename, audio_bytes)}

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                _GROQ_URL,
                headers=headers,
                data=data,
                files=files,
            )
            response.raise_for_status()

        payload = response.json()
        transcript: str = payload.get("text", "").strip()
        detected_language: str | None = payload.get("language")
        duration: float = float(payload.get("duration", 0.0))

        return TranscriptionResult(
            transcript=transcript,
            detected_language=detected_language,
            duration_seconds=duration,
            provider="groq",
            is_speech_detected=_is_speech(transcript),
        )


assert isinstance(GroqTranscriptionAdapter(api_key=""), TranscriptionAdapter)
