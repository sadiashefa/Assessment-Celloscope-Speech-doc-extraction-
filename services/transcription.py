"""
Transcription service — orchestrates validation and the adapter call.

Responsibilities:
  1. Validate file size (rejects > 25 MB before reading full bytes)
  2. Validate audio format using mutagen (pure Python, no ffmpeg needed)
  3. Call the injected TranscriptionAdapter
  4. Normalise silence: empty transcript → is_speech_detected=False

No FastAPI types (Request, UploadFile, HTTPException) are imported here.
The API layer is responsible for mapping service errors to HTTP responses.
"""

import io

import mutagen

from adapters.base import TranscriptionAdapter, TranscriptionResult
from core.config import settings


class AudioValidationError(Exception):
    """Raised when the audio file fails validation."""


class TranscriptionService:
    def __init__(self, adapter: TranscriptionAdapter) -> None:
        self._adapter = adapter

    def validate_audio(self, data: bytes, filename: str) -> None:
        """
        Validate audio bytes before sending to the provider.

        Raises AudioValidationError with a human-readable message on failure.
        """
        # 1. Size check
        if len(data) > settings.MAX_AUDIO_FILE_SIZE_BYTES:
            mb = len(data) / (1024 * 1024)
            raise AudioValidationError(
                f"File size {mb:.1f} MB exceeds the 25 MB limit."
            )

        # 2. Format check via mutagen (attempts to parse audio metadata)
        audio = mutagen.File(io.BytesIO(data), easy=True)
        if audio is None:
            raise AudioValidationError(
                f"Unsupported or unrecognised audio format: '{filename}'. "
                "Accepted formats: mp3, wav, ogg, flac, m4a, webm."
            )

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        language: str,
    ) -> TranscriptionResult:
        """
        Validate then transcribe.  Returns a TranscriptionResult.
        Raises AudioValidationError if the file is invalid.
        """
        self.validate_audio(audio_bytes, filename)
        return await self._adapter.transcribe(audio_bytes, filename, language)
