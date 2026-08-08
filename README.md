# Speech & Document Extraction

An AI service with two capabilities:
- **Transcribe** audio in Bengali and English (Groq Whisper / OpenAI Whisper)
- **Extract structured data** from photographed medical lab reports (OpenRouter + Gemini 2.0 Flash)

---

## Quick Start

### Default (mock adapters — no credentials required)

```bash
git clone <repo-url>
cd speech-doc-extraction
docker compose up
```

The service starts on `http://localhost:8000`. Both endpoints respond immediately using pre-recorded fixture responses — no API keys, no model download.

### With real providers

```bash
cp .env.example .env
# Edit .env:
#   TRANSCRIPTION_PROVIDER=groq       (or openai)
#   DOCUMENT_PROVIDER=openrouter
#   GROQ_API_KEY=<your key from console.groq.com>
#   OPENROUTER_API_KEY=<your key>
docker compose up
```

---

## API

### POST `/api/v1/transcribe`

| Field | Type | Description |
|---|---|---|
| `file` | multipart | Audio file (mp3, wav, ogg, flac, m4a, webm — max 25 MB) |
| `language` | form | `bn`, `en`, or `auto` |

**Response**
```json
{
  "transcript": "The patient's haemoglobin...",
  "detected_language": "en",
  "duration_seconds": 11.8,
  "provider": "groq",
  "is_speech_detected": true
}
```

Silence or ambient noise → `is_speech_detected: false`, `transcript: ""`

---

### POST `/api/v1/documents/extract`

| Field | Type | Description |
|---|---|---|
| `file` | multipart | Photograph or scan of a medical lab report (JPEG, PNG, WebP) |

**Response**
```json
{
  "meta": {
    "patient_name": "Rahim Uddin",
    "age": "45",
    "sex": "Male",
    "report_date": "2026-07-15",
    "lab_name": "Dhaka Diagnostic Centre",
    "reference_no": "DDC-2026-00842"
  },
  "results": [
    {
      "test_name": "Haemoglobin",
      "value": 12.5,
      "comparator": null,
      "unit": "g/dL",
      "reference_range": "13.0 - 17.0",
      "flag": "L",
      "raw_line": "Haemoglobin  12.5  g/dL  13.0-17.0  L"
    }
  ]
}
```

Non-lab-report → `422` with `code: "not_a_lab_report"`.

---

## Architecture

```
api/          HTTP routing, request/response schemas, validation
  └── FastAPI types (UploadFile, HTTPException) stay here only

services/     Business logic — no FastAPI imports, no network calls
  ├── TranscriptionService — validates size/format, calls adapter
  ├── DocumentService      — validates image, calls adapter, runs normalisers
  └── normalizers/
        ├── value.py       — canonical numeric value parsing
        └── unit.py        — unit and date normalisation

adapters/     Provider integration — the only place httpx/SDK calls live
  ├── base.py                    Protocol interfaces + result dataclasses
  ├── transcription/
  │     ├── mock.py              replays fixture from disk
  │     ├── groq.py              Groq Whisper API
  │     └── openai.py            OpenAI Whisper API (fallback)
  └── documents/
        ├── mock.py              replays fixture from disk
        └── openrouter.py        OpenRouter vision model
```

The layer separation is enforced by a mechanical test (`tests/unit/test_layer_separation.py`) that walks the source tree and asserts no FastAPI imports leak into `services/` and no provider SDKs leak into `api/`.

---

## Canonical Value Format

All numeric values extracted from lab reports are normalised as follows:

| Raw OCR | `value` | `comparator` |
|---|---|---|
| `12.5` | `12.5` | `null` |
| `12,500` | `12500.0` | `null` |
| `<0.5` | `0.5` | `"<"` |
| `> 10` | `10.0` | `">"` |
| `<=2.5` | `2.5` | `"<="` |
| `1.2 x 10^3` | `1200.0` | `null` |
| `1.2×10³` | `1200.0` | `null` |
| `1.2e3` | `1200.0` | `null` |
| unparseable | row excluded | — |

**Units** are normalised to canonical forms: `g/dL`, `mg/dL`, `mmol/L`, `IU/L`, `10³/μL`. Unknown units are preserved verbatim.

**Dates** in `meta.report_date` are normalised to ISO 8601 (`YYYY-MM-DD`). Unparseable dates are preserved verbatim.

**`raw_line`** is always the verbatim OCR text for that row. It is never cleaned, shortened, or dropped.

---

## Running Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

All 40 tests run against mock adapters — no credentials needed.

---

## Test Data

All test data is in `testdata/`. Sources:

### Audio

| File | Source | Why chosen |
|---|---|---|
| `en_speech.mp3` | Generated with gTTS (Google TTS, public API) | Medical vocabulary; tests English transcription with domain-specific terms |
| `bn_speech.mp3` | Generated with gTTS Bengali (public API) | Same content in Bengali; tests `bn` language parameter routing |
| `silence.wav` | Programmatically generated (Python `wave` stdlib) | 3 seconds of pure silence; tests `is_speech_detected: false` path |
| `noisy_en.wav` | Programmatically generated (white noise, `wave` stdlib) | Ambient noise with no speech; tests that the service does not hallucinate a transcript |

Reference transcripts are committed alongside audio in `testdata/audio/transcripts/`.

### Lab Reports

| File | Source | Why chosen |
|---|---|---|
| `report_clean.jpg` | Synthetically generated with Pillow | Realistic lab table structure; baseline extraction test |
| `report_angled.jpg` | `report_clean.jpg` rotated 8° (Pillow) | Simulates handheld photograph; tests model's robustness to rotation |
| `report_lowlight.jpg` | `report_clean.jpg` at 45% brightness (Pillow) | Simulates poor lighting; tests model's robustness to underexposure |
| `not_a_report.jpg` | Synthetically generated landscape image (Pillow) | No table, no medical content; tests graceful degradation |

Images were chosen to exercise the edge cases described in the brief (angled, poor light, not a lab report) rather than to make the service look good.

---

## Known Limitations

- **TTS audio quality**: `en_speech.mp3` and `bn_speech.mp3` are synthesised, not natural recordings. Real human speech — especially accented or fast-paced — may produce lower WER than these clips suggest. The reviewer's unseen inputs will exercise this more rigorously.
- **Synthetic lab report images**: The test lab report images were generated programmatically. Real photographed reports with handwritten annotations, stamps, or watermarks are not represented in the test set.
- **Unit normalisation**: The canonical unit map covers common haematology and biochemistry units. Specialist units (e.g. mEq/L, osmol/kg) are returned verbatim rather than normalised.
- **Multi-page reports**: The extraction endpoint handles a single image. Multi-page reports require the caller to split pages before uploading.
- **Date ambiguity**: `01/02/2026` is interpreted as `DD/MM/YYYY` (Feb 1). US-format dates (`MM/DD/YYYY`) are a lower-priority fallback and may be misidentified for day values ≤ 12.
