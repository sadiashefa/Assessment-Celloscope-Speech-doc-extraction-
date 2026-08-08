"""
Shared adapter interfaces and result types.

Only this module is imported by services/. Concrete implementations
(groq.py, openrouter.py, mock.py) live alongside it but are never
imported outside adapters/.
"""

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


class AdapterError(Exception):
    """
    Raised by any adapter when the upstream provider returns an error.
    Wraps the original exception so the API layer can catch it without
    importing httpx or any provider SDK.
    """


@dataclass
class TranscriptionResult:
    """Returned by every TranscriptionAdapter implementation."""

    transcript: str
    detected_language: str | None  # ISO 639-1 code e.g. "en", "bn"; None if silence
    duration_seconds: float
    provider: str  # "groq" | "openai" | "mock"
    is_speech_detected: bool


@dataclass
class RawLabResult:
    """
    Raw extraction result from the document adapter.

    raw_text is the full OCR / model output as a string.
    The document service is responsible for parsing it into
    structured LabResult objects.
    """

    raw_text: str  # full JSON string from the vision model / mock


@dataclass
class RawResultRow:
    """A single un-normalised result row as the adapter produced it."""

    test_name: str
    raw_value: str        # e.g. "<0.5", "12,500", "1.2 x 10^3"
    unit: str             # e.g. "gm/dl", "10^3/μL"
    reference_range: str  # preserved verbatim
    flag: str             # "H", "L", "" etc.
    raw_line: str         # verbatim OCR line — never dropped


@dataclass
class RawLabExtraction:
    """Structured but un-normalised extraction from the document adapter."""

    patient_name: str
    age: str
    sex: str
    report_date: str   # raw string — normalised by the service
    lab_name: str
    reference_no: str
    results: list[RawResultRow] = field(default_factory=list)
    is_lab_report: bool = True  # False when model signals not-a-lab-report


@runtime_checkable
class TranscriptionAdapter(Protocol):
    """
    Async protocol that every transcription adapter must satisfy.

    Receives raw audio bytes and returns a TranscriptionResult.
    Implementations must not import FastAPI types.
    """

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str,
        language: str,  # "bn" | "en" | "auto"
    ) -> TranscriptionResult: ...


@runtime_checkable
class DocumentAdapter(Protocol):
    """
    Async protocol that every document adapter must satisfy.

    Receives raw image bytes and returns a RawLabExtraction.
    Implementations must not import FastAPI types.
    """

    async def extract(
        self,
        image_bytes: bytes,
        filename: str,
    ) -> RawLabExtraction: ...
