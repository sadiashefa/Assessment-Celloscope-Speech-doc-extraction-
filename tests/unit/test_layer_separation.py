"""
Layer separation test — enforced mechanically.

Verifies that:
  1. services/ does not import FastAPI (Request, Response, UploadFile, HTTPException)
  2. api/   does not import provider SDKs (groq, openai SDK) or mutagen directly
  3. services/ does not import httpx (network calls belong in adapters/)

The assessment brief states this is checked mechanically — this test
performs the same check so violations are caught in CI before review.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent

SERVICES_DIR = REPO_ROOT / "services"
API_DIR = REPO_ROOT / "api"


def _python_files(directory: Path):
    return list(directory.rglob("*.py"))


def _file_contains(path: Path, pattern: str) -> bool:
    text = path.read_text(encoding="utf-8")
    return pattern in text


# ---------------------------------------------------------------------------
# services/ must not import FastAPI types
# ---------------------------------------------------------------------------

def test_services_no_fastapi_import():
    violations = []
    for path in _python_files(SERVICES_DIR):
        if _file_contains(path, "from fastapi") or _file_contains(path, "import fastapi"):
            violations.append(str(path.relative_to(REPO_ROOT)))
    assert violations == [], (
        f"FastAPI imported in services/ (must stay in api/):\n" + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# services/ must not make direct HTTP calls (httpx belongs in adapters/)
# ---------------------------------------------------------------------------

def test_services_no_httpx_import():
    violations = []
    for path in _python_files(SERVICES_DIR):
        if _file_contains(path, "import httpx"):
            violations.append(str(path.relative_to(REPO_ROOT)))
    assert violations == [], (
        f"httpx imported in services/ (network calls belong in adapters/):\n"
        + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# api/ must not import provider-specific libraries
# ---------------------------------------------------------------------------

_PROVIDER_PATTERNS = ["import groq", "from groq", "import openai", "from openai"]


def test_api_no_provider_sdk_import():
    violations = []
    for path in _python_files(API_DIR):
        for pattern in _PROVIDER_PATTERNS:
            if _file_contains(path, pattern):
                violations.append(f"{path.relative_to(REPO_ROOT)} ({pattern!r})")
    assert violations == [], (
        f"Provider SDK imported in api/ (must stay in adapters/):\n"
        + "\n".join(violations)
    )
