# DECISIONS.md

Consequential choices made during this implementation. Each entry names what was rejected and why, not only what was chosen.

---

## 1. Groq Whisper over self-hosted Whisper

**Chose**: Groq's hosted Whisper API (`whisper-large-v3-turbo`)
**Rejected**: `faster-whisper` or `whisper.cpp` as a self-hosted model inside Docker

The brief requires `docker compose up` on a clean clone to bring the service up with no model download. A self-hosted Whisper model is 1.5–3 GB depending on the variant. That blocks the clean-clone requirement for reviewers on the default compose path and adds significant pull time in CI. The brief explicitly says to keep self-hosted models off the default compose path if used.

Groq's free tier provides Whisper inference fast enough that latency is not a bottleneck during review. The OpenAI Whisper adapter is included as a fallback in case Groq rate-limits; both adapters are the same API shape so swapping costs one env-var change.

---

## 2. OpenRouter + Gemini 2.0 Flash over Tesseract OCR

**Chose**: OpenRouter vision model (`google/gemini-2.0-flash-001`)
**Rejected**: Tesseract OCR + regex/heuristic parsing pipeline

Tesseract OCR produces decent results on flat, well-lit documents but degrades significantly on angled photographs and poor lighting — exactly the conditions the brief describes. Building a robust pre-processing pipeline (deskew, denoise, binarise) adds substantial complexity and still fails on heavily degraded inputs.

Gemini Flash handles all these conditions natively as part of its vision model and returns structured JSON from a single prompt, which maps cleanly onto the extraction schema. The trade-off is latency (~2–4 s per request) and a dependency on an external API key, but the brief explicitly allows commercial APIs and the reviewer is expected to supply their own key.

---

## 3. httpx (async) over provider SDKs

**Chose**: `httpx.AsyncClient` for all provider calls
**Rejected**: `groq` Python SDK, `openai` Python SDK

Both Groq and OpenRouter expose standard REST APIs. Using their official SDKs would import library code into the adapters that can leak transitive dependencies and tie the adapter interface to a specific SDK version. More importantly, the assessment mechanically checks that no provider library is imported outside `adapters/`. Using raw httpx makes this boundary obvious and enforceable — there is nothing to accidentally import elsewhere.

The httpx calls are straightforward (a single POST with multipart or JSON body) and the response parsing is trivial, so the SDK adds no meaningful value here.

---

## 4. mutagen over pydub for audio validation

**Chose**: `mutagen` for audio format detection and duration
**Rejected**: `pydub` (which wraps ffmpeg)

pydub is a convenient library but requires ffmpeg as a system binary. Adding ffmpeg to the Docker image adds ~30–60 MB and requires a system-level install step in the Dockerfile. This complicates the clean-clone story and adds a non-Python dependency that can behave differently across OS versions.

mutagen is a pure Python library that reads audio metadata (format, duration, sample rate) from the file header without decoding the audio. It covers all the formats Whisper accepts (mp3, wav, ogg, flac, m4a, webm) and is sufficient for the two validation tasks we need: format detection and duration extraction.
