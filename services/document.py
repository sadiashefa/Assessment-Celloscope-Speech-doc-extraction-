"""
Document service — orchestrates validation, adapter call, and normalisation.

Responsibilities:
  1. Validate that the upload is a readable image (Pillow)
  2. Call the injected DocumentAdapter
  3. Handle non-lab-report signal gracefully (raises DocumentValidationError)
  4. Normalise each result row: value → NormalizedValue, unit → canonical form,
     date → ISO 8601
  5. Guarantee raw_line is always present and never cleaned

No FastAPI types are imported here.
"""

import io

from PIL import Image, UnidentifiedImageError

from adapters.base import DocumentAdapter, RawLabExtraction, RawResultRow
from services.normalizers.unit import normalize_date, normalize_unit
from services.normalizers.value import NormalizedValue, parse_value


class DocumentValidationError(Exception):
    """Raised when the uploaded file fails validation."""


class NotALabReportError(Exception):
    """Raised when the document is not a medical lab report."""


class NormalizedResult:
    """A fully normalised result row ready for the API response."""

    __slots__ = (
        "test_name",
        "value",
        "comparator",
        "unit",
        "reference_range",
        "flag",
        "raw_line",
    )

    def __init__(
        self,
        test_name: str,
        value: float,
        comparator: str | None,
        unit: str,
        reference_range: str,
        flag: str,
        raw_line: str,
    ) -> None:
        self.test_name = test_name
        self.value = value
        self.comparator = comparator
        self.unit = unit
        self.reference_range = reference_range
        self.flag = flag
        self.raw_line = raw_line  # never dropped, never cleaned


class NormalizedExtraction:
    """Fully normalised lab extraction ready for the API layer."""

    __slots__ = (
        "patient_name",
        "age",
        "sex",
        "report_date",
        "lab_name",
        "reference_no",
        "results",
    )

    def __init__(
        self,
        patient_name: str,
        age: str,
        sex: str,
        report_date: str,
        lab_name: str,
        reference_no: str,
        results: list[NormalizedResult],
    ) -> None:
        self.patient_name = patient_name
        self.age = age
        self.sex = sex
        self.report_date = report_date
        self.lab_name = lab_name
        self.reference_no = reference_no
        self.results = results


def _normalise_row(row: RawResultRow) -> NormalizedResult | None:
    """
    Normalise a single result row.

    Returns None (and the row is skipped) only when no numeric value can be
    extracted. raw_line is always preserved verbatim.
    """
    try:
        nv: NormalizedValue = parse_value(row.raw_value)
    except ValueError:
        # Cannot extract a numeric value — skip the row rather than guess
        return None

    return NormalizedResult(
        test_name=row.test_name,
        value=nv.numeric,
        comparator=nv.comparator,
        unit=normalize_unit(row.unit),
        reference_range=row.reference_range,
        flag=row.flag,
        raw_line=row.raw_line,  # verbatim — requirement 5
    )


class DocumentService:
    def __init__(self, adapter: DocumentAdapter) -> None:
        self._adapter = adapter

    def validate_image(self, data: bytes, filename: str) -> None:
        """
        Confirm that the upload is a readable image.

        Raises DocumentValidationError on failure.
        """
        try:
            with Image.open(io.BytesIO(data)) as img:
                img.verify()  # raises if corrupt
        except (UnidentifiedImageError, Exception) as exc:
            raise DocumentValidationError(
                f"Uploaded file '{filename}' is not a readable image: {exc}"
            )

    async def extract(
        self,
        image_bytes: bytes,
        filename: str,
    ) -> NormalizedExtraction:
        """
        Validate, extract, and normalise a lab report image.

        Raises:
          DocumentValidationError  — not a valid image
          NotALabReportError       — image is not a lab report
        """
        self.validate_image(image_bytes, filename)

        raw: RawLabExtraction = await self._adapter.extract(image_bytes, filename)

        if not raw.is_lab_report:
            raise NotALabReportError(
                "The uploaded document does not appear to be a medical lab report."
            )

        normalised_results: list[NormalizedResult] = []
        for row in raw.results:
            result = _normalise_row(row)
            if result is not None:
                normalised_results.append(result)

        return NormalizedExtraction(
            patient_name=raw.patient_name,
            age=raw.age,
            sex=raw.sex,
            report_date=normalize_date(raw.report_date),
            lab_name=raw.lab_name,
            reference_no=raw.reference_no,
            results=normalised_results,
        )
