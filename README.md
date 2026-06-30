# localizing-video

A Claude Code skill for making a foreign-language video — typically a Mandarin or Japanese
YouTube talking-head with slides and screenshots — watchable in English, with all three layers
translated and in sync:

- **Dubbed audio** (neural TTS, time-fitted to the original)
- **English subtitles** (burned into a letterbox bar)
- **On-screen text** (OCR'd, translated, and burned back over the original)

100% local compute on Apple Silicon — no paid APIs.

## Why this exists

A capable agent re-derives the obvious plumbing (yt-dlp → Whisper → ffmpeg → mux) on its own.
What it gets wrong are the **tool choices and silent footguns**: reaching for robotic `say` instead
of Kokoro, stretching audio with `atempo` (artifacts) instead of native-speed resynthesis with drift
catch-up, fighting libass over subtitle placement, leaving Vision OCR as an "unwritten script", and
double-translating on-screen text that is already English. `SKILL.md` is the captured fix for each.

## Use

Invoke the skill on a foreign-language video you want in English. It walks the eight-stage pipeline
and the decision points (visual scope, dub voice, audio mix), and points at a working reference
implementation to adapt rather than rebuild from scratch.

## Requirements

macOS / Apple Silicon, with: `yt-dlp`, Homebrew `ffmpeg-full` (libass) and `espeak-ng`,
openai-whisper (`large-v3-turbo`), `kokoro-onnx` + model weights, and `ocrmac` (Apple Vision).

## Status

Validated end-to-end on two full videos (an 8-min and an 11.5-min Mandarin commentary), each
producing dub + subtitles + targeted visual overlay. Known weak spot: heavily stylized hand-drawn
on-screen text OCRs inconsistently, so a few such labels can go uncovered; static slide, screenshot,
and document text covers cleanly.

`SKILL.md` is the skill itself.
