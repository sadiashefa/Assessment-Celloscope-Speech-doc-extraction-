from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # Provider selection — safe to commit, not secrets
    TRANSCRIPTION_PROVIDER: Literal["mock", "groq", "openai"] = "mock"
    DOCUMENT_PROVIDER: Literal["mock", "openrouter"] = "mock"

    # Secrets — default is always empty string, never a real key
    GROQ_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""

    # Model selection
    OPENROUTER_MODEL: str = "google/gemini-2.0-flash-001"

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
