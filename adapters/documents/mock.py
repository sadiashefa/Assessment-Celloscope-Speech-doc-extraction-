"""
Mock document adapter.

Replays pre-recorded responses from fixtures/document_mock.json.
No network calls, no model loading.

Routing rules:
  filename contains "not_a_report"  → fixture key "not_a_report"
  anything else                     → fixture key "lab_report"
"""

import json
from pathlib import Path

from adapters.base import DocumentAdapter, RawLabExtraction, RawResultRow

_FIXTURE_PATH = Path(__file__).parent.parent.parent / "fixtures" / "document_mock.json"


def _load_fixtures() -> dict:
    with open(_FIXTURE_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _select_key(filename: str) -> str:
    if "not_a_report" in filename.lower():
        return "not_a_report"
    return "lab_report"


class MockDocumentAdapter:
    """Satisfies DocumentAdapter Protocol without any I/O."""

    async def extract(
        self,
        image_bytes: bytes,
        filename: str,
    ) -> RawLabExtraction:
        fixtures = _load_fixtures()
        key = _select_key(filename)
        data = fixtures[key]

        results = [
            RawResultRow(
                test_name=row["test_name"],
                raw_value=row["raw_value"],
                unit=row["unit"],
                reference_range=row["reference_range"],
                flag=row["flag"],
                raw_line=row["raw_line"],
            )
            for row in data.get("results", [])
        ]

        return RawLabExtraction(
            patient_name=data["patient_name"],
            age=data["age"],
            sex=data["sex"],
            report_date=data["report_date"],
            lab_name=data["lab_name"],
            reference_no=data["reference_no"],
            results=results,
            is_lab_report=data["is_lab_report"],
        )


assert isinstance(MockDocumentAdapter(), DocumentAdapter)
