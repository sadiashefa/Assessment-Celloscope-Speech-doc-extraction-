"""
Integration tests for POST /api/v1/documents/extract — mock adapter only.
"""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from api.main import app
from api.dependencies import get_document_adapter
from adapters.documents.mock import MockDocumentAdapter


def _make_jpeg_bytes() -> bytes:
    """Generate a minimal valid JPEG in memory."""
    buf = io.BytesIO()
    img = Image.new("RGB", (100, 100), color=(200, 200, 200))
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture()
def client():
    app.dependency_overrides[get_document_adapter] = lambda: MockDocumentAdapter()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_extract_lab_report_happy_path(client):
    jpeg = _make_jpeg_bytes()
    response = client.post(
        "/api/v1/documents/extract",
        files={"file": ("report_clean.jpg", jpeg, "image/jpeg")},
    )
    assert response.status_code == 200
    body = response.json()
    assert "meta" in body
    assert "results" in body
    assert len(body["results"]) > 0


def test_every_result_has_raw_line(client):
    """raw_line must be present and non-empty on every result row — requirement 5."""
    jpeg = _make_jpeg_bytes()
    response = client.post(
        "/api/v1/documents/extract",
        files={"file": ("report_clean.jpg", jpeg, "image/jpeg")},
    )
    assert response.status_code == 200
    for row in response.json()["results"]:
        assert "raw_line" in row
        assert len(row["raw_line"]) > 0


def test_every_result_has_numeric_value(client):
    """value must be a number — requirement 6."""
    jpeg = _make_jpeg_bytes()
    response = client.post(
        "/api/v1/documents/extract",
        files={"file": ("report_clean.jpg", jpeg, "image/jpeg")},
    )
    assert response.status_code == 200
    for row in response.json()["results"]:
        assert isinstance(row["value"], (int, float))


def test_not_a_report_returns_422(client):
    jpeg = _make_jpeg_bytes()
    response = client.post(
        "/api/v1/documents/extract",
        files={"file": ("not_a_report.jpg", jpeg, "image/jpeg")},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "not_a_lab_report"


def test_invalid_image_returns_422(client):
    """Uploading a text file as an image must be rejected."""
    response = client.post(
        "/api/v1/documents/extract",
        files={"file": ("report.txt", b"not an image", "text/plain")},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "invalid_image"


def test_meta_fields_present(client):
    jpeg = _make_jpeg_bytes()
    response = client.post(
        "/api/v1/documents/extract",
        files={"file": ("report_clean.jpg", jpeg, "image/jpeg")},
    )
    assert response.status_code == 200
    meta = response.json()["meta"]
    for field in ("patient_name", "age", "sex", "report_date", "lab_name", "reference_no"):
        assert field in meta
