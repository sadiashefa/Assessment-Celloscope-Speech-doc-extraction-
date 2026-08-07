from pydantic import BaseModel


class TranscribeResponse(BaseModel):
    transcript: str
    detected_language: str | None
    duration_seconds: float
    provider: str
    is_speech_detected: bool


class ErrorDetail(BaseModel):
    code: str
    message: str
