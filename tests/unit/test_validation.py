"""
Validation tests — file size and format rejection.

These test the service validation layer directly, not HTTP status codes.
A failure here means the guard is broken, not just that a number changed.
"""

import io
import struct
import wave

import pytest

from services.transcription import AudioValidationError, TranscriptionService
from adapters.transcription.mock import MockTranscriptionAdapter


def _make_wav_bytes(duration_seconds: float = 1.0) -> bytes:
    """Generate a minimal valid WAV file in memory."""
    sample_rate = 8000
    num_samples = int(sample_rate * duration_seconds)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * num_samples)
    return buf.getvalue()


def _make_oversized_bytes(size_mb: float) -> bytes:
    """Return bytes of the given size that look like garbage (not a real audio format)."""
    return b"\xff\xfe" + b"\x00" * int(size_mb * 1024 * 1024)


service = TranscriptionService(MockTranscriptionAdapter())


def test_valid_wav_passes_validation():
    """A properly formed WAV file must not raise."""
    data = _make_wav_bytes()
    service.validate_audio(data, "en_speech.wav")  # should not raise


def test_oversized_file_raises():
    """Files over 25 MB must be rejected before reaching the provider."""
    data = _make_oversized_bytes(26)
    with pytest.raises(AudioValidationError, match="25 MB"):
        service.validate_audio(data, "big.mp3")


def test_exactly_25mb_passes():
    """Exactly 25 MB is allowed (the limit is exclusive >)."""
    data = b"\x00" * (25 * 1024 * 1024)
    # mutagen will reject this as not a real audio file — that's the format check
    # We just verify the SIZE check alone doesn't fire here by checking the error type
    try:
        service.validate_audio(data, "exactly25.wav")
    except AudioValidationError as exc:
        assert "25 MB" not in str(exc), "Size guard should not have fired at exactly 25 MB"


def test_non_audio_file_raises():
    """Uploading a JPEG as audio must be rejected with a clear format error."""
    jpeg_header = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"\x00" * 100
    with pytest.raises(AudioValidationError, match="Unsupported"):
        service.validate_audio(jpeg_header, "photo.jpg")


def test_empty_bytes_raises():
    """Empty file must be rejected."""
    with pytest.raises(AudioValidationError):
        service.validate_audio(b"", "empty.wav")
