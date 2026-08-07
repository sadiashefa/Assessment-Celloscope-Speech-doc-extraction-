"""
Dependency injection factories.

These are the only place where concrete adapter classes are instantiated.
The factory reads settings.TRANSCRIPTION_PROVIDER / settings.DOCUMENT_PROVIDER
and returns the appropriate adapter — services never need to know which one.

Startup guards: if a real provider is selected but its key is missing,
we fail loudly at request time with a clear message rather than a
cryptic 401 from the upstream API.
"""

from adapters.base import DocumentAdapter, TranscriptionAdapter
from adapters.documents.mock import MockDocumentAdapter
from adapters.documents.openrouter import OpenRouterDocumentAdapter
from adapters.transcription.groq import GroqTranscriptionAdapter
from adapters.transcription.mock import MockTranscriptionAdapter
from adapters.transcription.openai import OpenAITranscriptionAdapter
from core.config import settings


def get_transcription_adapter() -> TranscriptionAdapter:
    provider = settings.TRANSCRIPTION_PROVIDER

    if provider == "groq":
        if not settings.GROQ_API_KEY:
            raise ValueError(
                "GROQ_API_KEY must be set when TRANSCRIPTION_PROVIDER=groq. "
                "Add it to your .env file."
            )
        return GroqTranscriptionAdapter(api_key=settings.GROQ_API_KEY)

    if provider == "openai":
        if not settings.OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY must be set when TRANSCRIPTION_PROVIDER=openai. "
                "Add it to your .env file."
            )
        return OpenAITranscriptionAdapter(api_key=settings.OPENAI_API_KEY)

    return MockTranscriptionAdapter()


def get_document_adapter() -> DocumentAdapter:
    provider = settings.DOCUMENT_PROVIDER

    if provider == "openrouter":
        if not settings.OPENROUTER_API_KEY:
            raise ValueError(
                "OPENROUTER_API_KEY must be set when DOCUMENT_PROVIDER=openrouter. "
                "Add it to your .env file."
            )
        return OpenRouterDocumentAdapter(
            api_key=settings.OPENROUTER_API_KEY,
            model=settings.OPENROUTER_MODEL,
        )

    return MockDocumentAdapter()
