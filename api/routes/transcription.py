"""
POST /api/v1/transcribe

Accepts a multipart upload with:
  file     — audio file (mp3, wav, ogg, flac, m4a, webm)
  language — "bn" | "en" | "auto"

Returns TranscribeResponse on success.
Returns 422 with structured ErrorDetail for validation failures — never a stack trace.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status

from api.dependencies import get_transcription_adapter
from api.schemas.transcription import ErrorDetail, TranscribeResponse
from adapters.base import TranscriptionAdapter
from core.config import settings
from services.transcription import AudioValidationError, TranscriptionService

router = APIRouter()

_VALID_LANGUAGES = {"bn", "en", "auto"}


@router.post(
    "/transcribe",
    response_model=TranscribeResponse,
    responses={
        422: {"model": ErrorDetail, "description": "Validation error"},
    },
)
async def transcribe(
    file: UploadFile,
    language: Annotated[str, Form()],
    adapter: Annotated[TranscriptionAdapter, Depends(get_transcription_adapter)],
) -> TranscribeResponse:
    # Validate language field before reading bytes
    if language not in _VALID_LANGUAGES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=ErrorDetail(
                code="invalid_language",
                message=f"Language must be one of: {sorted(_VALID_LANGUAGES)}. Got '{language}'.",
            ).model_dump(),
        )

    # Size guard — check Content-Length header before reading the entire file
    if file.size is not None and file.size > settings.MAX_AUDIO_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=ErrorDetail(
                code="file_too_large",
                message="File exceeds the 25 MB limit.",
            ).model_dump(),
        )

    audio_bytes = await file.read()

    # Secondary size check after reading (Content-Length may be absent)
    if len(audio_bytes) > settings.MAX_AUDIO_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=ErrorDetail(
                code="file_too_large",
                message="File exceeds the 25 MB limit.",
            ).model_dump(),
        )

    service = TranscriptionService(adapter)

    try:
        result = await service.transcribe(audio_bytes, file.filename or "upload", language)
    except AudioValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=ErrorDetail(
                code="invalid_audio",
                message=str(exc),
            ).model_dump(),
        )

    return TranscribeResponse(
        transcript=result.transcript,
        detected_language=result.detected_language,
        duration_seconds=result.duration_seconds,
        provider=result.provider,
        is_speech_detected=result.is_speech_detected,
    )
