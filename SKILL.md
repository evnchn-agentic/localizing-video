---
name: localizing-video
description: Use when making a foreign-language video (esp. Mandarin/Japanese YouTube — talking-head + slides/screenshots) watchable in English with a SYNCED English dub AND/OR translated on-screen text burned in, preferring local/free tools (no paid APIs). Triggers: "translate this video", "dub to English", "make this video English", "subtitle + voiceover", "burn in translated subtitles", OCR on-screen text. macOS / Apple Silicon.
---

# localizing-video

Turn a foreign-language video into an English one — synced **dub** + English **subtitles** + translated **on-screen text** — 100% local/free on Apple Silicon. A capable agent will re-derive the plumbing (yt-dlp, whisper, ffmpeg, scene-detect, mux); this skill exists for the **tool choices and silent footguns that re-derivation gets wrong**, and for the proven reference implementation.

## Reference implementation (start here)
This repo ships the working pipeline: **`engine/`** is the generic, runnable engine (`build_dub.py` — chunk-anchored, drift-free (see the dub footgun), `make_ass.py`, `dense_ocr.py`, `dedup_spans.py`, `render_overlay.py`, `run.sh`); **`example/`** is a complete worked dataset. Read `engine/SETUP.md` + `example/README.md` and **run the engine** — don't write from scratch. Per video, the only new work is producing `en.srt` + `translations.json` (the translation step). Engine assumes a 1920×1080 source.

## Pipeline + the decision at each stage
1. **Download** `yt-dlp` (try `--extractor-args "youtube:player_client=web_safari,ios,tv"` on 403; HLS fmt often works when DASH is DRM'd).
2. **ASR** openai-whisper `whisper source.mp4 --model large-v3-turbo --language <zh/ja> --word_timestamps True --output_format all` (keep JSON). Pin the language. (torch has no py3.14 wheel → run whisper from a py3.12 venv.)
3. **Translate transcript YOURSELF** (the agent, in-loop) — free, tone-aware, jargon-consistent. Keep 1:1 segment↔timestamp mapping. Fix proper nouns by knowledge (ASR mishears them). **Preserve the joke, not just the words** — puns rarely survive literal translation; *trans-create* an English pun that carries the same mechanism, and land the payoff in the **subtitle** (the joke's primary carrier — the dub rides over the ducked original). Homophone puns are *invisible* in the ASR (see footgun), so OCR the caption to find them.
4. **Dub** — Kokoro-onnx TTS (see footguns). **Sentence-chunk** synth, **anchor each chunk to its true timestamp** (NOT per-segment drift-chasing — it accumulates lag), time-fit, mix. Retime the *visuals* to meet the dub, not just the dub to the clock — see **Time-density**.
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
| **English is denser-to-say than ZH/JA → dub runs late** | DON'T `atempo` (>1.25× = vocoder artifacts) — resynth at Kokoro **native `speed`**. DON'T chase drift with a running cursor (`cursor-start` catch-up): empirically it **accumulates ~+5s by mid-video** on dense back-to-back speech. Instead: **(a) anchor each utterance to its true start** (= the subtitle/video timeline) so drift *cannot* accumulate; **(b) chunk adjacent ASR segments into ~sentence utterances** so a long-English line borrows time from a short neighbour — per-*segment* fitting truncated **59%** of lines at a 1.9× cap; sentence-chunking dropped that to ~0. Anchoring kills *drift*, NOT *overrun* — a chunk whose audio exceeds its slot still collides with the next anchor. **Overflow fallback order:** (1) terser translation, (2) resynth faster within the ~1.9× cap ("compress" = native-`speed` resynth or shorter text — NOT `atempo`), (3) freeze-extend the slide under it (see **Time-density**), (4) borrow a low-density neighbour's slack; last resort, hard-cap + 30 ms fade the tail (the **subtitle still carries the full line**). |
| **English subs render OVER the video, huge** | SRT→libass defaults to `PlayResY=288` → font/margin scaled ~4.4×. Emit **ASS with explicit `PlayResY`** = padded height. And **letterbox** (pad a bottom bar, `Alignment=2`) so English doesn't collide with the source's own burned-in subs (you can't remove those). |
| **Vision OCR "needs a custom script"** | No — `pip install ocrmac`; `ocrmac.OCR(f, language_preference=["zh-Hans","en-US"]).recognize()` returns `(text, conf, (x,y,w,h))` normalized, origin **bottom-left**. |
| **Reconciling ASR against the on-screen caption** | The bottom caption IS authoritative ground-truth for the narration — great ASR cross-check. BUT creators plant **gag captions** (gibberish ≠ spoken line); never blindly replace ASR with OCR. Flag divergences, judge each. |
| **ASR silently flattens a homophone pun** | The joke can *be* the homophone: 人工智能 (AI) spoken as 人工**痔**能 ("hemorrhoid-tech"), or 搁置 ("shelve the project") as 割**痔**疮 ("hemorrhoid removal"). Whisper "corrects" the rare pun to the common word, so **the gag never reaches the transcript** — and no proper-noun fix recovers it. Creators usually *spell the pun out* in the burned-in caption, so here **OCR isn't a cross-check — it's usually the only reliable recovery path** (for a spelled-out homophone the caption wins, the opposite of the gag-caption case above). Tell: a line reads oddly literal, or the reaction/visual doesn't match the words → OCR that caption before you translate. |
| **Overlaying every Chinese box** | In commentary videos much on-screen "content" (articles, embedded talks, tweets) is **already English** with Chinese layered on — overlaying it is redundant + cluttered. Scope to **Chinese-only** elements. |
| **Static overlay on scrolling text** | Per-span (averaged-position) overlay **can't track continuous scroll** — Chinese stays uncovered. Needs per-frame OCR + box tracking; usually not worth it (that content is the already-English kind). |
| **Keep original English clips audible** | Where the source plays real English clips (interviews/demos), pass the **original audio through at full volume** in the gaps; duck it (~0.1) only under the dub. |
| **Reusing scripts on a NEW video** | Adapt, but check for hardcoded length/paths. `render_overlay.py` derived overlay duration from a hardcoded frame count — on a longer video the overlay silently stopped partway. **Derive duration from `len(glob('f1/f_*.png'))`, not a constant.** Re-translate `en.srt` + `translations.json` per video; the index-pairing assert + a side-by-side spot-check catches translation/key misalignment. |

## Time-density: retime the timeline, not just the dub
English carries **~1.5–2× fewer bits/second** than Mandarin/Japanese, so a faithful dub is *always* fighting for airtime on a dense source. Compressing the dub (native `speed`) is one lever and it caps ~1.9× before it sounds rushed. The bigger one: **the visual timeline is elastic — retime it to meet the dub.** Three levers, ranked cheapest-first:

- **Terser translation first (dense→shorter).** Reword the densest lines shorter. Free, loses nothing a viewer sees, and the burned **subtitle still carries the full meaning** if the dub trims a hair. This is the main lever for talking-head shots (you can't freeze a moving face without judder; re-cutting with B-roll is usually out of scope for a localize-in-place job).
- **Freeze-extend static slides (buy time where the pressure is).** The dub races hardest exactly when the narrator is reading out a screenshot/slide — and that frame is *static*, so **hold it a fraction longer at a natural pause** to buy airtime. Nearly invisible **IF** you respect three conditions: **(i) it's a timeline edit** — everything downstream shifts by the hold, so insert the freeze and regenerate sub/dub/overlay timing against the *held* timeline (or hold all tracks together at the mux), don't just anchor to original time; **(ii) freeze only where the audio bed also pauses** — a hold over continuous music/room-tone/original-audio desyncs the bed (extend/crossfade it, or only freeze under the dub where the bed is ducked/silent); **(iii) "static" must be truly static** — a cursor, blinking caret, laser pointer, or webcam inset in the frame breaks the illusion. Do **many tiny holds, never one long drag** (a multi-second hold reads as a stall/buffer).
- **Reclaim slack from low-density stretches (the inverse — less-dense→dense).** Intros, sign-offs, slow pans have spare room; let the dub breathe there, or borrow that slack forward to a dense stretch.

**Why this works out: density and freezability correlate.** The narration is densest *because* he's explaining a slide — and slides are exactly what's freezable. So most of the time-pressure tends to land where you can absorb it. **Measure it, don't assume it:** mark each second **static** by frame-to-frame motion (`mean|frame − prev|` on downscaled grayscale) — but the threshold is a **per-video calibration** (codec noise, bitrate, fps, grain all move it; ≈4/255 was one video's value), and a whole-frame mean **misses localized motion** (cursor/caret/pointer) → mask out the caption band and check a static *region*, not the whole frame. Then intersect the static mask with the fast-dub chunks to see how much pressure is freezable. In one measured 10-min explainer, a calm 1.4× ceiling needed **~14s** reclaimed and **74% of it sat over freezable static slides** (26% over the un-freezable talking head → terser wording) — but that split is **video-by-video**. Going *over* the source runtime is fine for a standalone file; nothing external syncs to it.

## Decision points to raise with the operator
- **Visual scope:** targeted (Chinese-only, recommended) vs full (also article paragraphs — degrades on scroll).
- **Dub voice:** which free Kokoro voice; offer paid (ElevenLabs) only if they relax the no-billing constraint.
- **Audio:** full replace vs keep original ducked under the dub.
- **Pacing effort:** accept a fast dub (subs carry full meaning) vs. retime for a calm ceiling (terser wording + freeze-extend slides — costs a measurement + re-mux). Offer the measurement number so they can decide.

## Verify (don't trust — see)
Frame-sample the FINAL mp4 (Read the JPGs) at: a narration moment, a slide/overlay moment, an English-clip gap, and the last line — confirm sub sync, overlay placement, letterbox, and A/V duration match. Pixels burn in permanently. **Sample a DENSE-slide moment specifically** (where the dub races) — that's where sync/drift breaks first; the burned Chinese caption at that timestamp is your sync oracle. (You can't audition audio yourself — sync is *structural* via the anchored timeline; say so and ask the operator for the last-mile listen.)

## Composes with
`hardsubbing-video` (the ffmpeg/libass burn-in footguns — this skill's stage 8).
