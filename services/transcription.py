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
import math
import struct
import wave

import mutagen

from adapters.base import TranscriptionAdapter, TranscriptionResult
from core.config import settings

# WAV RMS below this value is treated as silence locally, skipping the API call.
# Pure silence.wav → RMS ≈ 0.  Normal speech → RMS typically > 500.
_SILENCE_RMS_THRESHOLD = 50


def _wav_rms(audio_bytes: bytes) -> float | None:
    """
    Compute RMS amplitude of a WAV file from its raw bytes.
    Returns None if the file is not a readable WAV.
    """
    try:
        buf = io.BytesIO(audio_bytes)
        with wave.open(buf) as wf:
            sampwidth = wf.getsampwidth()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)
        if sampwidth == 2:
            samples = struct.unpack(f"<{len(raw) // 2}h", raw)
        elif sampwidth == 1:
            # unsigned 8-bit → centre around zero
            samples = tuple(b - 128 for b in raw)
        else:
            return None  # 24/32-bit WAV — skip RMS check
        if not samples:
            return 0.0
        return math.sqrt(sum(s * s for s in samples) / len(samples))
    except Exception:
        return None


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

        # Pre-flight silence detection for WAV files.
        # Pure silence has RMS ≈ 0.  This avoids wasting an API call and
        # prevents LLMs from hallucinating text from a silent waveform.
        if filename.lower().endswith(".wav"):
            rms = _wav_rms(audio_bytes)
            if rms is not None and rms < _SILENCE_RMS_THRESHOLD:
                duration = 0.0
                audio = mutagen.File(io.BytesIO(audio_bytes))
                if audio and hasattr(audio.info, "length"):
                    duration = float(audio.info.length)
                return TranscriptionResult(
                    transcript="",
                    detected_language=None,
                    duration_seconds=duration,
                    provider="local-silence-check",
                    is_speech_detected=False,
                )

        return await self._adapter.transcribe(audio_bytes, filename, language)
