"""
OpenRouter document extraction adapter.

Sends a base64-encoded image to an OpenRouter vision model and parses the
structured JSON response into a RawLabExtraction.

The prompt instructs the model to:
  1. Return a strict JSON object matching our schema.
  2. Preserve raw_line verbatim for every result row.
  3. Signal non-lab-report documents with {"is_lab_report": false} so the
     service layer can degrade gracefully without producing garbage output.
"""

import base64
import json
import re

import httpx

from adapters.base import DocumentAdapter, RawLabExtraction, RawResultRow

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

_SYSTEM_PROMPT = """\
You are a medical document parser. Extract structured data from lab report images.

Return ONLY a JSON object with this exact schema — no markdown, no explanation:
{
  "is_lab_report": true,
  "patient_name": "string",
  "age": "string",
  "sex": "string",
  "report_date": "string (as printed, do not reformat)",
  "lab_name": "string",
  "reference_no": "string",
  "results": [
    {
      "test_name": "string",
      "raw_value": "string (exactly as printed, e.g. '<0.5', '1.2 x 10^3')",
      "unit": "string (exactly as printed)",
      "reference_range": "string (exactly as printed)",
      "flag": "string (H, L, or empty)",
      "raw_line": "string (the complete verbatim OCR text for this row)"
    }
  ]
}

Rules:
- raw_line must be the exact text OCR returned for that row. Never clean it.
- raw_value must be the exact value as printed. Never interpret or round.
- If the document is NOT a medical lab report, return: {"is_lab_report": false}
- If a field is not visible, use an empty string — never guess.
"""


def _extract_json(text: str) -> dict:
    """Extract JSON from model response, stripping markdown fences if present."""
    # Strip ```json ... ``` or ``` ... ``` fences
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text.strip())
    return json.loads(text)


class OpenRouterDocumentAdapter:
    """Calls an OpenRouter vision model; satisfies DocumentAdapter Protocol."""

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    async def extract(
        self,
        image_bytes: bytes,
        filename: str,
    ) -> RawLabExtraction:
        b64 = base64.standard_b64encode(image_bytes).decode("ascii")

        # Detect image MIME type from magic bytes
        if image_bytes[:3] == b"\xff\xd8\xff":
            mime = "image/jpeg"
        elif image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
            mime = "image/png"
        elif image_bytes[:4] in (b"RIFF", b"WEBP"):
            mime = "image/webp"
        else:
            mime = "image/jpeg"  # safe fallback for most photos

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"},
                        },
                        {
                            "type": "text",
                            "text": "Extract the lab report data from this image.",
                        },
                    ],
                },
            ],
            "temperature": 0,  # deterministic — we want exact extraction, not creativity
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=90.0) as client:
            response = await client.post(_OPENROUTER_URL, headers=headers, json=payload)
            response.raise_for_status()

        content = response.json()["choices"][0]["message"]["content"]
        data = _extract_json(content)

        if not data.get("is_lab_report", True):
            return RawLabExtraction(
                patient_name="",
                age="",
                sex="",
                report_date="",
                lab_name="",
                reference_no="",
                results=[],
                is_lab_report=False,
            )

        results = [
            RawResultRow(
                test_name=row.get("test_name", ""),
                raw_value=row.get("raw_value", ""),
                unit=row.get("unit", ""),
                reference_range=row.get("reference_range", ""),
                flag=row.get("flag", ""),
                raw_line=row.get("raw_line", ""),
            )
            for row in data.get("results", [])
        ]

        return RawLabExtraction(
            patient_name=data.get("patient_name", ""),
            age=data.get("age", ""),
            sex=data.get("sex", ""),
            report_date=data.get("report_date", ""),
            lab_name=data.get("lab_name", ""),
            reference_no=data.get("reference_no", ""),
            results=results,
            is_lab_report=True,
        )


assert isinstance(OpenRouterDocumentAdapter(api_key="", model=""), DocumentAdapter)
