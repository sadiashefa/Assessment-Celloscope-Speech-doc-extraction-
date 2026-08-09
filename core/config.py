from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # Single provider switch for both endpoints
    PROVIDER: Literal["mock", "openrouter"] = "mock"

    # Secret — only needed when PROVIDER=openrouter
    OPENROUTER_API_KEY: str = ""

    # Model used for POST /api/v1/transcribe
    TRANSCRIPTION_PROVIDER_MODEL: str = "google/gemini-2.5-flash"

    # Model used for POST /api/v1/documents/extract
    DOCUMENT_EXTRACTION_PROVIDER_MODEL: str = "google/gemini-2.5-flash"

    # Limits
    MAX_AUDIO_FILE_SIZE_BYTES: int = 25 * 1024 * 1024  # 25 MB

    # Supported audio MIME types
    SUPPORTED_AUDIO_MIME_TYPES: list[str] = [
        "audio/mpeg",
        "audio/mp3",
        "audio/wav",
        "audio/wave",
        "audio/x-wav",
        "audio/ogg",
        "audio/flac",
        "audio/x-flac",
        "audio/mp4",
        "audio/m4a",
        "audio/x-m4a",
        "audio/webm",
        "video/webm",  # some recorders send webm with video MIME
        "audio/mpeg3",
        "audio/x-mpeg-3",
    ]


settings = Settings()
