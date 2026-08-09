# Celloscope Assessment: Speech & Document Extraction

A FastAPI service with two endpoints:
- **Transcribe** audio in Bengali, English, or any language (OpenRouter + Gemini 2.5 Flash)
- **Extract lab report data** from photographs of medical reports (OpenRouter + Gemini 2.5 Flash)

Both endpoints use a single `OPENROUTER_API_KEY`.

## Quick Start

### Default (no credentials needed)

```bash
git clone <repo-url>
cd speech-doc-extraction
docker compose up
```

Service starts at `http://localhost:8000`. Both endpoints return pre-recorded fixture responses. No API keys or model downloads required.

### With real providers

```bash
cp .env.example .env
# Edit .env:
#
#   PROVIDER=openrouter
#
#   OPENROUTER_API_KEY=<your key from openrouter.ai>
#
#   TRANSCRIPTION_PROVIDER_MODEL=google/gemini-2.5-flash   # for /transcribe
#   DOCUMENT_EXTRACTION_PROVIDER_MODEL=google/gemini-2.5-flash   # for /documents/extract
#
docker compose up
```

---

## API

### POST `/api/v1/transcribe`

| Field | Type | Description |
|---|---|---|
| `file` | multipart | Audio file (mp3, wav, ogg, flac, m4a, webm - max 25 MB) |
| `language` | form | Optional. `bn`, `en`, or `auto`. Default: `auto`. The field is accepted but not sent to the model - the model picks up the language from the audio itself. Used only as a fallback for `detected_language` in the response if the model does not detect one. |

**Silence handling:**
- **WAV files:** The audio energy (RMS) is checked locally before any API call. If RMS is below 50, the request returns `is_speech_detected: false` immediately with no network call.
- **All formats:** The prompt asks the model to first write what it hears in a `heard` field before deciding `is_speech_detected`. This forces the model to think before outputting, so it cannot write "I hear Bengali speech" and then set `is_speech_detected: false` - it has to be consistent.
- **Language hint removed:** Passing `language=bn` in the prompt caused the model to write Bengali text even on silent audio. Removing the hint from the API payload fixed this. The model detects language from the audio on its own.

**Response**
```json
{
  "transcript": "রোগীর হিমোগ্লোবিনের মাত্রা বারো দশমিক পাঁচ গ্রাম...",
  "detected_language": "bn",
  "duration_seconds": 17.69,
  "provider": "openrouter-gemini",
  "is_speech_detected": true
}
```

Silence or ambient noise returns `is_speech_detected: false`, `transcript: ""`, `provider: "local-silence-check"`.

---

### POST `/api/v1/documents/extract`

| Field | Type | Description |
|---|---|---|
| `file` | multipart | Photo or scan of a medical lab report (JPEG, PNG, WebP) |

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

If the image is not a lab report, returns `422` with `code: "not_a_lab_report"`.

---

## Architecture

```
api/          HTTP layer - routes, request/response schemas, validation
  - FastAPI types (UploadFile, HTTPException) stay here only

services/     Business logic - no FastAPI imports, no HTTP calls
  - TranscriptionService: validates file size/format, WAV silence check, calls adapter
  - DocumentService: validates image, calls adapter, runs value/unit normalizers
  - normalizers/value.py: parses raw OCR numbers into float + comparator
  - normalizers/unit.py: maps unit variants to a standard form, parses dates

adapters/     All external API calls live here, nowhere else
  - base.py: Protocol interfaces and shared dataclasses
  - transcription/mock.py: reads from fixtures/ (default, no credentials)
  - transcription/openrouter.py: OpenRouter + Gemini 2.5 Flash (main real adapter)
  - transcription/groq.py: Groq Whisper (alternative)
  - transcription/openai.py: OpenAI Whisper (alternative)
  - documents/mock.py: reads from fixtures/ (default, no credentials)
  - documents/openrouter.py: OpenRouter + Gemini 2.5 Flash
```

Layer separation is checked by `tests/unit/test_layer_separation.py`, which reads source files and fails if FastAPI types appear in `services/` or provider imports appear in `api/`.

---

## Value Format

Lab report values are parsed and stored as follows:

| Raw OCR | `value` | `comparator` |
|---|---|---|
| `12.5` | `12.5` | `null` |
| `12,500` | `12500.0` | `null` |
| `<0.5` | `0.5` | `"<"` |
| `> 10` | `10.0` | `">"` |
| `<=2.5` | `2.5` | `"<="` |
| `1.2 x 10^3` | `1200.0` | `null` |
| `1.2e3` | `1200.0` | `null` |
| cannot parse | row skipped | - |

Units are mapped to standard forms: `g/dL`, `mg/dL`, `mmol/L`, `IU/L`, `10³/μL`. Unknown units are kept as-is.

Dates in `meta.report_date` are converted to `YYYY-MM-DD`. If a date cannot be parsed, it is kept as-is.

`raw_line` is the exact OCR text for that row. It is never changed or dropped.

---

## Running Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

All 40 tests run against mock adapters. No credentials needed.

---

## Test Data

### Audio

| File | Source | Why chosen |
|---|---|---|
| `en_speech.mp3` | Generated with gTTS | Medical vocabulary in English; covers domain-specific words |
| `bn_speech.mp3` | Generated with gTTS (Bengali) | Same content in Bengali; tests the language detection path |
| `silence.wav` | Generated with Python `wave` stdlib | 3 seconds of silence; checks `is_speech_detected: false` |
| `noisy_en.wav` | Generated with Python `wave` stdlib (white noise) | Background noise with no speech; checks the model does not invent words |

Reference transcripts are in `testdata/audio/transcripts/`.

### Lab Reports

| File | Source | Why chosen |
|---|---|---|
| `report_clean.jpg` | Generated with Pillow | Straight-on, well-lit; baseline case |
| `report_angled.jpg` | `report_clean.jpg` rotated 8 degrees | Simulates a handheld photo; checks extraction on rotated input |
| `report_lowlight.jpg` | `report_clean.jpg` at 45% brightness | Simulates poor lighting |
| `not_a_report.jpg` | Generated landscape image (Pillow) | Not a lab report; checks the graceful error path |

These were picked to cover the edge cases in the brief (angled, poor light, wrong document), not to make the service look better than it is.

---

## Known Limitations

- `en_speech.mp3` and `bn_speech.mp3` are TTS recordings, not real speech. The model may perform differently on natural, accented, or fast speech.
- Test lab report images were generated programmatically. Photos with handwritten notes, stamps, or watermarks are not covered.
- The unit map covers common blood test units. Uncommon units (e.g. mEq/L, osmol/kg) are returned as-is without conversion.
- Only single-image uploads are supported. Multi-page reports need to be split before uploading.
- Dates like `01/02/2026` are read as DD/MM/YYYY (Feb 1). US-format dates may be misread for day values of 12 or below.


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
# Edit .env — only ONE key needed for both endpoints:
#
#   TRANSCRIPTION_PROVIDER=openrouter      # or: groq | openai
#   DOCUMENT_PROVIDER=openrouter
#
#   OPENROUTER_API_KEY=<your key from openrouter.ai>
#   GROQ_API_KEY=                          # only needed if TRANSCRIPTION_PROVIDER=groq
#
#   OPENROUTER_TRANSCRIPTION_MODEL=google/gemini-2.5-flash   # model for /transcribe
#   OPENROUTER_MODEL=google/gemma-4-31b-it                   # model for /documents/extract
#
docker compose up
```

---

## API

### POST `/api/v1/transcribe`

| Field | Type | Description |
|---|---|---|
| `file` | multipart | Audio file (mp3, wav, ogg, flac, m4a, webm — max 25 MB) |
| `language` | form | **Optional.** `bn`, `en`, or `auto`. Default: `auto`. Accepted per spec but **not sent to the model** — Gemini detects language natively. Used only as a fallback for `detected_language` in the response. |

**Silence handling (three layers):**
- **WAV files:** Local RMS energy check before any API call. RMS < 50 → `is_speech_detected: false` instantly, no network request.
- **All formats:** Prompt uses a mandatory `heard` field (chain-of-thought). Model must describe audio content before setting `is_speech_detected`.
- **No language hint sent to model:** The `language` param is never included in the API payload — it caused hallucination on silent audio. Model detects language freely from audio content.

**Response**
```json
{
  "transcript": "রোগীর হিমোগ্লোবিনের মাত্রা বারো দশমিক পাঁচ গ্রাম...",
  "detected_language": "bn",
  "duration_seconds": 17.69,
  "provider": "openrouter-gemini",
  "is_speech_detected": true
}
```

Silence or ambient noise → `is_speech_detected: false`, `transcript: ""`, `provider: "local-silence-check"`

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
  ├── TranscriptionService — size/format validation, WAV silence pre-check, calls adapter
  ├── DocumentService      — image validation, calls adapter, runs normalisers
  └── normalizers/
        ├── value.py       — canonical numeric value parsing
        └── unit.py        — unit and date normalisation

adapters/     Provider integration — the only place httpx calls live
  ├── base.py                    Protocol interfaces + result dataclasses + AdapterError
  ├── transcription/
  │     ├── mock.py              replays fixture from disk (default)
  │     ├── openrouter.py        OpenRouter + Gemini 2.5 Flash (multimodal, primary real adapter)
  │     ├── groq.py              Groq Whisper API (alternative, TRANSCRIPTION_PROVIDER=groq)
  │     └── openai.py            OpenAI Whisper API (alternative, TRANSCRIPTION_PROVIDER=openai)
  └── documents/
        ├── mock.py              replays fixture from disk (default)
        └── openrouter.py        OpenRouter + Gemma 4 31B IT (vision, primary real adapter)
```

Layer separation is enforced by a mechanical test (`tests/unit/test_layer_separation.py`) that asserts no FastAPI imports leak into `services/` and no provider SDKs leak into `api/`.

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
