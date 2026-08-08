"""
OpenRouter audio transcription adapter.

Uses OpenRouter's /audio/transcriptions endpoint with openai/gpt-transcribe model.
Sends base64-encoded audio as JSON (not multipart).
This allows a single OPENROUTER_API_KEY for both transcription and document extraction.
"""

import base64
import io

import httpx
import mutagen

from adapters.base import AdapterError, TranscriptionAdapter, TranscriptionResult

_OPENROUTER_AUDIO_URL = "https://openrouter.ai/api/v1/audio/transcriptions"

_NON_SPEECH_TOKENS = {"[music]", "[noise]", "[silence]", "[blank_audio]"}


def _is_speech(transcript: str) -> bool:
    stripped = transcript.strip().lower()
    if not stripped:
        return False
    return stripped not in _NON_SPEECH_TOKENS


def _get_duration(audio_bytes: bytes) -> float:
    """Get audio duration in seconds using mutagen (pure Python, no ffmpeg)."""
    audio = mutagen.File(io.BytesIO(audio_bytes))
    if audio and hasattr(audio.info, "length"):
        return float(audio.info.length)
    return 0.0


class OpenRouterTranscriptionAdapter:
    """Calls OpenRouter audio transcription; satisfies TranscriptionAdapter Protocol."""

    def __init__(self, api_key: str, model: str = "openai/gpt-transcribe") -> None:
        self._api_key = api_key
        self._model = model

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        language: str,
    ) -> TranscriptionResult:
        audio_b64 = base64.standard_b64encode(audio_bytes).decode("ascii")

        # Detect format from filename extension
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "mp3"

        payload: dict = {
            "model": self._model,
            "input_audio": {
                "data": audio_b64,
                "format": ext,
            },
        }
        if language != "auto":
            payload["language"] = language

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    _OPENROUTER_AUDIO_URL,
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise AdapterError(
                f"OpenRouter transcription error {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.RequestError as exc:
            raise AdapterError(f"OpenRouter network error: {exc}") from exc

        result = response.json()
        transcript: str = result.get("text", "").strip()
        detected_language: str | None = result.get("language") or (
            None if language == "auto" else language
        )
        duration = _get_duration(audio_bytes)

        return TranscriptionResult(
            transcript=transcript,
            detected_language=detected_language,
            duration_seconds=duration,
            provider="openrouter",
            is_speech_detected=_is_speech(transcript),
        )


assert isinstance(
    OpenRouterTranscriptionAdapter(api_key=""), TranscriptionAdapter
)
