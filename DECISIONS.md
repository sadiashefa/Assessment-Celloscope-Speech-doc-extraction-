# DECISIONS.md

Key choices made during this implementation. Each entry explains what was picked, what was not picked, and why.

---

## 1. OpenRouter + Gemini 2.5 Flash for transcription instead of Groq Whisper or self-hosted ASR

**Picked**: OpenRouter multimodal model (`google/gemini-2.5-flash`) via chat/completions
**Not picked**: Groq Whisper (`whisper-large-v3-turbo`), self-hosted `faster-whisper`, OpenAI Whisper API

Whisper-style ASR models transcribe speech well on clean audio but they have no concept of audio content beyond speech. They can output text from near-silent input just by pattern-matching noise to likely words. Gemini 2.5 Flash actually listens to the audio and decides whether speech is present before transcribing. This made silence and noise detection much more reliable without adding a separate Voice Activity Detection (VAD) step.

Using OpenRouter for transcription also means both endpoints share one API key, which is simpler for the reviewer.

Groq and OpenAI Whisper adapters are still in `adapters/transcription/` and work if you set `TRANSCRIPTION_PROVIDER=groq` or `=openai`. The adapter pattern means switching is a one-line config change.

Self-hosting was not an option here because downloading a 1.5-3 GB Whisper model would break the `docker compose up` clean-clone requirement.

---

## 2. OpenRouter + Gemma 4 31B IT for document extraction instead of Tesseract OCR

**Picked**: OpenRouter vision model (`google/gemma-4-31b-it`) via chat/completions
**Not picked**: Tesseract OCR with a regex/heuristic parsing pipeline; smaller vision models

Tesseract works reasonably on flat, well-lit scans but starts failing badly on angled photos and dim lighting, which are exactly what the brief describes as expected inputs. Building a pipeline to deskew, denoise, and binarise images before feeding them to Tesseract is a lot of work and still breaks on difficult inputs.

A large vision model like Gemma 4 31B IT handles angled and dark photos without any preprocessing and returns structured JSON from a single prompt. We started with a smaller model (Gemini Flash) but moved to Gemma 4 31B for better accuracy on lab reports with complex layouts, merged cells, and faint text.

---

## 3. httpx over provider SDKs

**Picked**: `httpx.AsyncClient` for all provider API calls
**Not picked**: `groq` Python SDK, `openai` Python SDK

Both Groq and OpenRouter are standard REST APIs. Using their official SDKs would pull in extra dependencies and tie the code to specific library versions. The assessment also checks that no provider library is imported outside `adapters/`. Calling the APIs directly with httpx keeps this rule easy to follow and easy to verify.

The actual API calls are simple: one POST request with a JSON or multipart body. The SDK would not add anything useful here.

---

## 4. Pure Python parser for M4A duration instead of pydub or ffmpeg

**Picked**: Custom ISOBMFF box parser using Python `struct` from the standard library; `wave` stdlib for WAV; `mutagen.mp3.MP3` for MP3
**Not picked**: `pydub` (needs ffmpeg), `mutagen.mp4.MP4` with BytesIO

pydub needs ffmpeg installed as a system binary, which adds ~30-60 MB to the Docker image and an extra setup step. mutagen is pure Python and works for most formats, but `mutagen.mp4.MP4` throws an error when given a BytesIO object because it expects a file path with an extension. This was confirmed during testing.

The final approach picks the right reader per format:
- **WAV**: Python `wave` stdlib, reads frame count divided by sample rate
- **MP3**: `mutagen.mp3.MP3` with a BytesIO object
- **M4A/MP4/AAC**: a small custom parser that reads the ISOBMFF box structure directly, finds the `moov/mvhd` atom, and reads `timescale` and `duration` using `struct.unpack`. No temp files, no ffmpeg, works whether `moov` is at the start or the end of the file
- **Everything else**: `mutagen.File` with content sniffing as a fallback

---

## 5. Three steps to handle silence correctly

**Picked**: (a) RMS check on WAV bytes before the API call; (b) a `heard` field in the prompt that forces the model to describe audio before deciding; (c) removing the `language` hint from the API payload entirely
**Not picked**: VAD libraries; including `language` in the prompt; a single imperative rule in the system prompt

**Step 1 - WAV energy check:** The service reads WAV bytes, computes the RMS amplitude, and if it is below 50 (pure silence), returns `is_speech_detected: false` immediately without making an API call. This costs nothing and handles programmatically generated silence files reliably.

**Step 2 - heard field:** The system prompt asks the model to fill in a `heard` field before setting `is_speech_detected`. The model has to write something like "complete silence, no sound" before it can decide. This stops it from contradicting itself: if the `heard` field says silence, it cannot then say `is_speech_detected: true`. The prompt also says: "if unsure, set false" to bias the model toward missing speech rather than inventing it.

**Step 3 - no language hint:** Even with steps 1 and 2, Gemini 2.5 Flash was still writing Bengali text on silent MP3 and M4A files when the user passed `language=bn`. The model was treating the language word as a signal to output that language, regardless of what the audio contained. This is just how language models work: a strong language token in the input can override other instructions. Removing the hint from the API payload fixed this completely. The model picks up the language from the audio on its own. The `language` parameter from the user is still accepted by the API (as required by the spec) but is only used as a fallback for `detected_language` in the response, never sent to the model.

VAD libraries like Silero VAD and WebRTC VAD were not used because they need model downloads or compiled binaries, which would break the clean-clone `docker compose up` requirement.


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

## 4. Pure Python ISOBMFF box parser for M4A duration over pydub/ffmpeg

**Chose**: Custom ISOBMFF box parser using Python `struct` stdlib; `wave` stdlib for WAV; `mutagen.mp3.MP3` for MP3
**Rejected**: `pydub` (wraps ffmpeg), `mutagen.mp4.MP4` for BytesIO input

pydub requires ffmpeg as a system binary, adding ~30–60 MB to the Docker image and a system-level install step. mutagen is pure Python and covers most formats, but `mutagen.mp4.MP4` raises `MP4StreamInfoError` when passed a raw `BytesIO` object because the parser expects a file-like object with a `.name` attribute — a limitation confirmed in testing.

The final approach uses a format-specific dispatch:
- **WAV** → Python `wave` stdlib (parses frame count ÷ sample rate; zero external deps)
- **MP3** → `mutagen.mp3.MP3(BytesIO(...))` (reliable for CBR/VBR)
- **M4A/MP4/AAC** → custom pure-Python reader that walks ISO Base Media File Format (ISOBMFF) boxes, locates the `moov/mvhd` atom, and reads `timescale` + `duration` directly using `struct.unpack`. No temp files, no ffmpeg, works regardless of whether the `moov` atom is at the start or end of the file.
- **Other formats** → `mutagen.File` sniffing fallback

---

## 5. Three-layer silence detection: RMS pre-check + prompt chain-of-thought + no language hint in API payload

**Chose**: (a) Local RMS amplitude check for WAV; (b) structured `heard` field for chain-of-thought reasoning; (c) completely removing the user-supplied `language` hint from the Gemini API payload
**Rejected**: VAD libraries; passing language hints alongside audio; relying on a single prompt instruction

**Layer 1 — local RMS pre-check (WAV only):** A local energy check on WAV bytes (RMS < 50 → silence) is deterministic and costs zero API credits. Silent WAV files are caught before any network call and returned immediately.

**Layer 2 — prompt chain-of-thought (all formats):** The system prompt requires the model to populate a `heard` field before deciding `is_speech_detected`. The model must first write what it actually hears (e.g. `"silence with faint hiss"`), which prevents logical inconsistency — if `heard` describes silence, the model cannot justify `is_speech_detected: true` without contradicting itself. An explicit tie-breaking rule (`When in doubt → false`) biases output toward caution.

**Layer 3 — language hint removed from API payload:** Despite layers 1 and 2, Gemini 2.5 Flash continued hallucinating Bengali text on silent MP3/M4A files when `language=bn` appeared in the user message. The model treated the language token as a content expectation rather than a metadata hint and generated plausible Bengali text from silence. The root cause is a fundamental LLM behaviour: language tokens activate language-specific output pathways regardless of input content. The fix is to send no language hint to the model at all — Gemini detects language natively and reliably from audio content. The user-supplied `language` parameter is still accepted by the API (per the assessment spec) but is used only as a `detected_language` fallback in the response, never as a prompt signal. This eliminated the hallucination entirely.

VAD libraries (e.g. Silero VAD, WebRTC VAD) were rejected: they require model downloads or native binaries and would break the `docker compose up` clean-clone requirement.

