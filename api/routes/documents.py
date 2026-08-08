"""
POST /api/v1/documents/extract

Accepts a multipart upload with:
  file — photograph or scan of a medical lab report (JPEG, PNG, WebP)

Returns ExtractResponse on success.
Returns 422 with structured ErrorDetail for validation failures or non-lab-report inputs.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from api.dependencies import get_document_adapter
from api.schemas.documents import ExtractResponse, LabMeta, LabResult
from api.schemas.transcription import ErrorDetail
from adapters.base import AdapterError, DocumentAdapter
from services.document import DocumentService, DocumentValidationError, NotALabReportError

router = APIRouter()


@router.post(
    "/documents/extract",
    response_model=ExtractResponse,
    responses={
        422: {"model": ErrorDetail, "description": "Validation error or not a lab report"},
    },
)
async def extract_document(
    file: UploadFile,
    adapter: Annotated[DocumentAdapter, Depends(get_document_adapter)],
) -> ExtractResponse:
    image_bytes = await file.read()

    service = DocumentService(adapter)

    try:
        extraction = await service.extract(image_bytes, file.filename or "upload")
    except DocumentValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=ErrorDetail(code="invalid_image", message=str(exc)).model_dump(),
        )
    except NotALabReportError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=ErrorDetail(code="not_a_lab_report", message=str(exc)).model_dump(),
        )
    except AdapterError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=ErrorDetail(code="provider_error", message=str(exc)).model_dump(),
        )

    return ExtractResponse(
        meta=LabMeta(
            patient_name=extraction.patient_name,
            age=extraction.age,
            sex=extraction.sex,
            report_date=extraction.report_date,
            lab_name=extraction.lab_name,
            reference_no=extraction.reference_no,
        ),
        results=[
            LabResult(
                test_name=r.test_name,
                value=r.value,
                comparator=r.comparator,
                unit=r.unit,
                reference_range=r.reference_range,
                flag=r.flag or None,
                raw_line=r.raw_line,
            )
            for r in extraction.results
        ],
    )
