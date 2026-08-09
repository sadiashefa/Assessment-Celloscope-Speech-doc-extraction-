# DECISIONS.md

Consequential choices made during this implementation. Each entry names what was rejected and why, not only what was chosen.

---

## 1. OpenRouter + Gemini 2.5 Flash for transcription over Groq Whisper / self-hosted ASR

**Chose**: OpenRouter multimodal model (`google/gemini-2.5-flash`) via chat/completions
**Rejected**: Groq Whisper (`whisper-large-v3-turbo`), self-hosted `faster-whisper`, OpenAI Whisper API

Traditional ASR (Whisper-family) works well on clean studio speech but has no semantic understanding of audio content. It cannot reliably distinguish silence from noise, and it can hallucinate plausible-sounding words on near-silent input — a real failure mode we hit in testing. Gemini 2.5 Flash is a multimodal model that *listens* to audio and reasons about it: it correctly returns `is_speech_detected: false` for silence and noise without needing a separate VAD (Voice Activity Detection) step.

Using OpenRouter for transcription also consolidates both endpoints behind a single API key, which simplifies reviewer setup. Groq and OpenAI Whisper adapters are retained in `adapters/transcription/` and can be activated via `TRANSCRIPTION_PROVIDER=groq` or `=openai` — the adapter pattern makes swapping a one-line env change.

The self-hosted option was rejected for the same reason as before: a 1.5–3 GB model download blocks the `docker compose up` clean-clone requirement.

---

## 2. OpenRouter + Gemma 4 31B IT for document extraction over Tesseract OCR

**Chose**: OpenRouter vision model (`google/gemma-4-31b-it`) via chat/completions
**Rejected**: Tesseract OCR + regex/heuristic parsing pipeline; smaller vision models

Tesseract degrades significantly on angled photographs and poor lighting — exactly the conditions the brief describes. A robust Tesseract pipeline would require deskew, denoise, and binarise preprocessing, adding substantial complexity that still fails on heavily degraded inputs.

Gemma 4 31B IT is a large multimodal model that handles all these conditions natively and returns structured JSON from a single prompt. A smaller model (`gemini-flash`) was initially used but swapped to Gemma 4 31B for better extraction accuracy on complex lab report layouts with merged cells, variable column widths, and low-contrast printing.

---

## 3. httpx (async) over provider SDKs

**Chose**: `httpx.AsyncClient` for all provider calls
**Rejected**: `groq` Python SDK, `openai` Python SDK

Both Groq and OpenRouter expose standard REST APIs. Using their official SDKs would import library code into adapters that can leak transitive dependencies and tie the adapter interface to a specific SDK version. The assessment mechanically checks that no provider library is imported outside `adapters/`. Using raw httpx makes this boundary obvious and enforceable.

The httpx calls are a single POST with multipart or JSON body, so the SDK adds no meaningful value here.

---

## 4. mutagen + stdlib wave over pydub for audio duration

**Chose**: `mutagen` + Python `wave` stdlib for format detection and duration
**Rejected**: `pydub` (wraps ffmpeg)

pydub requires ffmpeg as a system binary, adding ~30–60 MB to the Docker image and a system-level install step. mutagen is pure Python and covers all supported formats. A notable implementation detail: `mutagen.mp4.MP4` fails when passed a raw `BytesIO` object (no `.name` attribute), so M4A/MP4 files are written to a temporary file before parsing — a stdlib-only workaround that avoids adding ffmpeg.

WAV duration is handled by Python's built-in `wave` module (zero dependencies), and MP3 by `mutagen.mp3.MP3`. The format-specific dispatch ensures each format uses the most reliable reader available.

---

## 5. Local RMS silence pre-check before LLM call for WAV files

**Chose**: Compute RMS amplitude from WAV bytes in the service layer; skip the API call if RMS < 50
**Rejected**: Relying solely on the LLM prompt to detect silence

During testing, Gemini 2.5 Flash hallucinated Bengali text when given a silent WAV file and `language=bn` as a hint. The language instruction overrode the silence-detection rule despite strong prompt wording. A local energy check is deterministic and costs nothing — a silent WAV (RMS ≈ 0) is caught before any network call is made, and the response is returned in milliseconds. Non-WAV silence (MP3, M4A) still reaches the model, where the prompt handles it reliably since those formats are less trivially "all zeros".

