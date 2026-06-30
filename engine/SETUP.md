# Engine setup (macOS / Apple Silicon)

One-time prerequisites for the generic pipeline.

```bash
# system tools
brew install yt-dlp espeak-ng
brew install ffmpeg-full          # default brew ffmpeg lacks the libass `subtitles` filter

# python env (onnxruntime-based; works on py3.12–3.14)
python3 -m venv venv-tts
./venv-tts/bin/pip install kokoro-onnx soundfile numpy ocrmac pillow

# neural TTS weights (~340 MB, free)
curl -L -o kokoro-v1.0.onnx https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
curl -L -o voices-v1.0.bin  https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin

# ASR (Mandarin/Japanese speech-to-text) — openai-whisper in a py3.12 venv (torch has no 3.14 wheel)
python3.12 -m venv venv-asr && ./venv-asr/bin/pip install openai-whisper   # large-v3-turbo
```

Kokoro's bundled espeak data path is broken on macOS; `build_dub.py` already monkeypatches
`espeakng_loader` to point at the Homebrew `espeak-ng` install — that's why `brew install espeak-ng`
is required.

## Running it

`run.sh` operates on its **current working directory**, which must hold the per-video data and the
shared assets. Set up a working dir per video:

```bash
mkdir my_video && cd my_video
#   put here: source.mp4, en.srt, translations.json   (en.srt/translations.json: see ../example/README.md)
#   plus (symlink the shared ones): kokoro-v1.0.onnx, voices-v1.0.bin, venv-tts/
ln -s /path/to/localizing-video/kokoro-v1.0.onnx .   # etc.

/path/to/localizing-video/engine/run.sh my_video     # -> my_video_v1.mp4, my_video_v2.mp4
# knobs: VOICE=am_michael MAXSPEED=1.85 SCOPE=targeted|full BAR=200
```

Source must be **1920×1080 landscape** (the overlay/letterbox geometry is fixed to it; `run.sh` checks
and aborts otherwise). Deriving geometry per-source is the obvious next enhancement.
