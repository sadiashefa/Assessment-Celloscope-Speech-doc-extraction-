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

## 2. OpenRouter + Gemini 2.5 Flash for document extraction instead of Tesseract OCR

**Picked**: OpenRouter vision model (`google/gemini-2.5-flash`) via chat/completions
**Not picked**: Tesseract OCR with a regex/heuristic parsing pipeline; Gemma 4 31B IT (tried earlier)

Tesseract works reasonably on flat, well-lit scans but starts failing badly on angled photos and dim lighting, which are exactly what the brief describes as expected inputs. Building a pipeline to deskew, denoise, and binarise images before feeding them to Tesseract is a lot of work and still breaks on difficult inputs.

Gemini 2.5 Flash handles angled and dark photos without any preprocessing and returns structured JSON from a single prompt. It is also the same model used for transcription, so both endpoints now share one model name. Gemma 4 31B IT was tried during development but switched back to Gemini 2.5 Flash for consistency and simpler reviewer setup.

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
