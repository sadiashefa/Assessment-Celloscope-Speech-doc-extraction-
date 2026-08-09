"""
Integration tests for POST /api/v1/transcribe — mock adapter only.

These tests verify the full request/response cycle through the API layer.
They do not call any external service.
"""

import io
import math
import struct
import wave

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.dependencies import get_transcription_adapter
from adapters.transcription.mock import MockTranscriptionAdapter


def _make_wav_bytes(silent: bool = False) -> bytes:
    """
    Generate a minimal valid WAV file.
    silent=False  → 440 Hz sine tone (non-zero RMS, passes silence pre-check)
    silent=True   → pure zeros (triggers silence pre-check in service)
    """
    sample_rate = 8000
    n_samples = sample_rate  # 1 second
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        if silent:
            frames = b"\x00\x00" * n_samples
        else:
            # 440 Hz sine wave at ~50% amplitude — clearly non-silent
            frames = struct.pack(
                f"<{n_samples}h",
                *[int(16000 * math.sin(2 * math.pi * 440 * i / sample_rate))
                  for i in range(n_samples)],
            )
        wf.writeframes(frames)
    return buf.getvalue()


@pytest.fixture()
def client():
    """TestClient with mock transcription adapter wired in."""
    app.dependency_overrides[get_transcription_adapter] = lambda: MockTranscriptionAdapter()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_transcribe_english_happy_path(client):
    wav = _make_wav_bytes(silent=False)  # sine tone — must pass silence pre-check
    response = client.post(
        "/api/v1/transcribe",
        data={"language": "en"},
        files={"file": ("en_speech.wav", wav, "audio/wav")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_speech_detected"] is True
    assert body["detected_language"] == "en"
    assert len(body["transcript"]) > 0
    assert body["provider"] == "mock"
    assert body["duration_seconds"] > 0


def test_transcribe_bengali_returns_bn_language(client):
    wav = _make_wav_bytes(silent=False)
    response = client.post(
        "/api/v1/transcribe",
        data={"language": "bn"},
        files={"file": ("bn_speech.mp3", wav, "audio/wav")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["detected_language"] == "bn"
    assert body["is_speech_detected"] is True


def test_transcribe_silence_returns_no_speech(client):
    wav = _make_wav_bytes(silent=True)  # pure zeros — triggers local silence pre-check
    response = client.post(
        "/api/v1/transcribe",
        data={"language": "en"},
        files={"file": ("silence.wav", wav, "audio/wav")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_speech_detected"] is False
    assert body["transcript"] == ""


def test_transcribe_invalid_language_returns_422(client):
    wav = _make_wav_bytes(silent=False)
    response = client.post(
        "/api/v1/transcribe",
        data={"language": "fr"},
        files={"file": ("test.wav", wav, "audio/wav")},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_language"


def test_transcribe_missing_language_defaults_to_auto(client):
    """language field is optional — omitting it uses 'auto' and succeeds."""
    wav = _make_wav_bytes(silent=False)
    response = client.post(
        "/api/v1/transcribe",
        files={"file": ("test.wav", wav, "audio/wav")},
        # no language field
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_speech_detected"] is True


def test_transcribe_oversized_file_returns_422(client):
    big = b"\x00" * (26 * 1024 * 1024)
    response = client.post(
        "/api/v1/transcribe",
        data={"language": "en"},
        files={"file": ("big.wav", big, "audio/wav")},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "file_too_large"
