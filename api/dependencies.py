"""
Dependency injection factories.

The factory reads settings.PROVIDER and returns the appropriate adapter.
Startup guard: if PROVIDER=openrouter but OPENROUTER_API_KEY is empty,
fails with a clear message rather than a cryptic 401 from the API.
"""

from adapters.base import DocumentAdapter, TranscriptionAdapter
from adapters.documents.mock import MockDocumentAdapter
from adapters.documents.openrouter import OpenRouterDocumentAdapter
from adapters.transcription.mock import MockTranscriptionAdapter
from adapters.transcription.openrouter import GeminiTranscriptionAdapter
from core.config import settings


def get_transcription_adapter() -> TranscriptionAdapter:
    if settings.PROVIDER == "openrouter":
        if not settings.OPENROUTER_API_KEY:
            raise ValueError(
                "OPENROUTER_API_KEY must be set when PROVIDER=openrouter. "
                "Add it to your .env file."
            )
        return GeminiTranscriptionAdapter(
            api_key=settings.OPENROUTER_API_KEY,
            model=settings.TRANSCRIPTION_PROVIDER_MODEL,
        )
    return MockTranscriptionAdapter()


def get_document_adapter() -> DocumentAdapter:
    if settings.PROVIDER == "openrouter":
        if not settings.OPENROUTER_API_KEY:
            raise ValueError(
                "OPENROUTER_API_KEY must be set when PROVIDER=openrouter. "
                "Add it to your .env file."
            )
        return OpenRouterDocumentAdapter(
            api_key=settings.OPENROUTER_API_KEY,
            model=settings.DOCUMENT_EXTRACTION_PROVIDER_MODEL,
        )
    return MockDocumentAdapter()
