"""
Mock transcription adapter.

Replays pre-recorded responses from fixtures/transcription_mock.json.
No network calls, no model loading. Selection is based on the uploaded
filename so tests can trigger specific scenarios deterministically.

Routing rules (checked in order):
  filename contains "silence"  → fixture key "silence"
  filename starts with "bn_"   → fixture key "bn"
  filename starts with "noisy" → fixture key "noisy"
  anything else                → fixture key "en"  (safe default)
"""

import json
from pathlib import Path

from adapters.base import TranscriptionAdapter, TranscriptionResult

_FIXTURE_PATH = Path(__file__).parent.parent.parent / "fixtures" / "transcription_mock.json"


def _load_fixtures() -> dict:
    with open(_FIXTURE_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _select_key(filename: str) -> str:
    name = filename.lower()
    if "silence" in name:
        return "silence"
    if name.startswith("bn_"):
        return "bn"
    if "noisy" in name:
        return "noisy"
    return "en"


class MockTranscriptionAdapter:
    """Satisfies TranscriptionAdapter Protocol without any I/O."""

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        language: str,
    ) -> TranscriptionResult:
        fixtures = _load_fixtures()
        key = _select_key(filename)
        data = fixtures[key]
        return TranscriptionResult(
            transcript=data["transcript"],
            detected_language=data["detected_language"],
            duration_seconds=data["duration_seconds"],
            provider=data["provider"],
            is_speech_detected=data["is_speech_detected"],
        )


# Runtime check that the class satisfies the Protocol
assert isinstance(MockTranscriptionAdapter(), TranscriptionAdapter)
