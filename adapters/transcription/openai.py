"""
OpenAI Whisper transcription adapter — fallback if Groq rate-limits.

Identical API shape to Groq (both are OpenAI-compatible). The only
differences are the base URL and the language parameter format.
OpenAI Whisper accepts ISO 639-1 codes directly ("bn", "en"),
so no mapping is required.
"""

import httpx

from adapters.base import TranscriptionAdapter, TranscriptionResult

_OPENAI_URL = "https://api.openai.com/v1/audio/transcriptions"
_MODEL = "whisper-1"

_NON_SPEECH_TOKENS = {"[music]", "[noise]", "[silence]", "[blank_audio]"}


def _is_speech(transcript: str) -> bool:
    stripped = transcript.strip().lower()
    if not stripped:
        return False
    return stripped not in _NON_SPEECH_TOKENS


class OpenAITranscriptionAdapter:
    """Calls OpenAI Whisper API; satisfies TranscriptionAdapter Protocol."""

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
            data["language"] = language  # OpenAI accepts ISO codes directly

        files = {"file": (filename, audio_bytes)}

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                _OPENAI_URL,
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
            provider="openai",
            is_speech_detected=_is_speech(transcript),
        )


assert isinstance(OpenAITranscriptionAdapter(api_key=""), TranscriptionAdapter)
