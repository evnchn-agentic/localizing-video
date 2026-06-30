# Worked example + the per-video step

The engine is generic. The only thing that changes per video is **two data files** that you (with an
agent in the loop) produce once, up front:

| File | What it is | How it's made |
|---|---|---|
| `en.srt` | English subtitles, one segment per spoken line, timestamps preserved | ASR the audio → translate each segment yourself (tone-aware, fix proper nouns) keeping a strict 1:1 segment↔timestamp mapping |
| `translations.json` | `{ "<on-screen Chinese string>": "<English>" }` | OCR the frames (`dense_ocr.py` → `dedup_spans.py` emits the unique strings) → translate each. `""` skips junk; a `~` prefix marks redundant/already-English text for full-mode only |

Everything else — dubbing, time-fitting, overlay rendering, muxing — is the engine and is the same for
every video. **That separation is the point: the engine is the reusable machine; these two files are the
content.** (The engine does still assume a 1920×1080 landscape source and the working-dir layout in
`../engine/SETUP.md` — it's decoupled from the *translation*, not from every format assumption.)

## The files here (a real, complete example)

From an 8-minute Mandarin commentary (`youtu.be/ll-OBB-iswM`):

- `loop_engineering.zh.srt` — raw Whisper transcript (Mandarin)
- `loop_engineering.en.srt` — the translated subtitles (244 segments)
- `loop_engineering.translations.json` — 155 on-screen strings translated

Drop these in a working dir as `en.srt` / `translations.json` next to the video's `source.mp4` and the
model files (per `../engine/SETUP.md`), and run `…/engine/run.sh` from that dir to reproduce the result.

## Producing the two files for a NEW video (the agent's job)

```bash
yt-dlp -f "bv*+ba/b" --merge-output-format mp4 -o source.mp4 "<URL>"
./venv-asr/bin/whisper source.mp4 --model large-v3-turbo --language zh \
    --word_timestamps True --output_format srt --output_dir .       # -> source.srt
```

Then the agent: translates `source.srt` → `en.srt`; and after `dense_ocr.py`+`dedup_spans.py` produce
the unique on-screen strings, translates those → `translations.json`. Verify proper nouns against the
on-screen captions (they're authoritative — but watch for deliberate gag captions that differ from the
spoken line). Then run the engine.
