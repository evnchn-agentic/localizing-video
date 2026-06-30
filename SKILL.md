---
name: localizing-video
description: Use when making a foreign-language video (esp. Mandarin/Japanese YouTube — talking-head + slides/screenshots) watchable in English with a SYNCED English dub AND/OR translated on-screen text burned in, preferring local/free tools (no paid APIs). Triggers: "translate this video", "dub to English", "make this video English", "subtitle + voiceover", "burn in translated subtitles", OCR on-screen text. macOS / Apple Silicon.
---

# localizing-video

Turn a foreign-language video into an English one — synced **dub** + English **subtitles** + translated **on-screen text** — 100% local/free on Apple Silicon. A capable agent will re-derive the plumbing (yt-dlp, whisper, ffmpeg, scene-detect, mux); this skill exists for the **tool choices and silent footguns that re-derivation gets wrong**, and for the proven reference implementation.

## Reference implementation (start here)
`~/loop-engineering-translate/` is a complete, working build (8-min Mandarin → EN dub+subs+overlay). Read its `README.md`; **adapt its scripts** (`build_dub.py`, `make_ass.py`, `dense_ocr.py`, `dedup_spans.py`, `render_overlay.py`, `mux*.sh`) rather than writing from scratch. Swap URL → re-run ASR → re-translate `en.srt` + `translations.json`.

## Pipeline + the decision at each stage
1. **Download** `yt-dlp` (try `--extractor-args "youtube:player_client=web_safari,ios,tv"` on 403; HLS fmt often works when DASH is DRM'd).
2. **ASR** openai-whisper `large-v3-turbo --language <zh/ja>` (`~/ngaamjam/venv-asr/bin/whisper`), `--word_timestamps True`, output `all` (keep JSON). Pin the language.
3. **Translate transcript YOURSELF** (the agent, in-loop) — free, tone-aware, jargon-consistent. Keep 1:1 segment↔timestamp mapping. Fix proper nouns by knowledge (ASR mishears them).
4. **Dub** — Kokoro-onnx TTS (see footguns). Per-segment synth, time-fit, **drift catch-up**, mix.
5. **Subtitles** — burn English in a **letterbox bar**, NOT over the frame (see footguns).
6. **Visual OCR** — `ocrmac` (Apple Vision), dense 1fps, dedup to time-spans.
7. **Translate visual strings YOURSELF**; overlay English over Chinese-only boxes.
8. **Mux** — `ffmpeg-full` (libass), overlay → letterbox → subtitle burn → dub audio.

## Footguns — the actual reason this skill exists
| Trap | Reality / fix |
|---|---|
| **ffmpeg has no `subtitles` filter** | default brew ffmpeg lacks libass. Use `/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg`. (skill: `hardsubbing-video`) |
| **TTS = `say` is flat/robotic** | Default to **Kokoro-onnx** (free, neural, py3.14 OK via onnxruntime). Male `am_michael`/etc. |
| **Kokoro silently fails: `phontab ... No such file`** | bundled espeak data path is broken. `brew install espeak-ng`, then in-script override `espeakng_loader.get_data_path/get_library_path` → `/opt/homebrew/share/espeak-ng-data` + `/opt/homebrew/lib/libespeak-ng.dylib`. |
| **English is ~15% longer than ZH → dub drifts late** | DON'T rely on `atempo` (vocoder artifacts >1.25×). Use Kokoro **native `speed`** to resynth, + **active drift catch-up**: when `cursor-start` grows, raise the speed target to claw it back; silent gaps reset drift. Keeps audio≈subs≈visuals locked. |
| **English subs render OVER the video, huge** | SRT→libass defaults to `PlayResY=288` → font/margin scaled ~4.4×. Emit **ASS with explicit `PlayResY`** = padded height. And **letterbox** (pad a bottom bar, `Alignment=2`) so English doesn't collide with the source's own burned-in subs (you can't remove those). |
| **Vision OCR "needs a custom script"** | No — `pip install ocrmac`; `ocrmac.OCR(f, language_preference=["zh-Hans","en-US"]).recognize()` returns `(text, conf, (x,y,w,h))` normalized, origin **bottom-left**. |
| **Reconciling ASR against the on-screen caption** | The bottom caption IS authoritative ground-truth for the narration — great ASR cross-check. BUT creators plant **gag captions** (gibberish ≠ spoken line); never blindly replace ASR with OCR. Flag divergences, judge each. |
| **Overlaying every Chinese box** | In commentary videos much on-screen "content" (articles, embedded talks, tweets) is **already English** with Chinese layered on — overlaying it is redundant + cluttered. Scope to **Chinese-only** elements. |
| **Static overlay on scrolling text** | Per-span (averaged-position) overlay **can't track continuous scroll** — Chinese stays uncovered. Needs per-frame OCR + box tracking; usually not worth it (that content is the already-English kind). |
| **Keep original English clips audible** | Where the source plays real English clips (interviews/demos), pass the **original audio through at full volume** in the gaps; duck it (~0.1) only under the dub. |
| **Reusing scripts on a NEW video** | Adapt, but check for hardcoded length/paths. `render_overlay.py` derived overlay duration from a hardcoded frame count — on a longer video the overlay silently stopped partway. **Derive duration from `len(glob('f1/f_*.png'))`, not a constant.** Re-translate `en.srt` + `translations.json` per video; the index-pairing assert + a side-by-side spot-check catches translation/key misalignment. |

## Decision points to raise with the operator
- **Visual scope:** targeted (Chinese-only, recommended) vs full (also article paragraphs — degrades on scroll).
- **Dub voice:** which free Kokoro voice; offer paid (ElevenLabs) only if they relax the no-billing constraint.
- **Audio:** full replace vs keep original ducked under the dub.

## Verify (don't trust — see)
Frame-sample the FINAL mp4 (Read the JPGs) at: a narration moment, a slide/overlay moment, an English-clip gap, and the last line — confirm sub sync, overlay placement, letterbox, and A/V duration match. Pixels burn in permanently.

## Composes with
`hardsubbing-video` (the ffmpeg/libass burn-in footguns — this skill's stage 8).
