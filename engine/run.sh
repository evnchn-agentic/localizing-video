#!/bin/bash
# Generic localization engine. Run from a working dir that contains the PER-VIDEO data:
#   source.mp4   en.srt   translations.json   kokoro-v1.0.onnx   voices-v1.0.bin   venv-tts/
# (How to produce en.srt + translations.json for a new video: see ../example/README.md.)
# Output: <name>_v1.mp4 (dub+subs)  and  <name>_v2.mp4 (dub+subs+visual overlay).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
FF="${FF:-/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg}"
PY="${PY:-./venv-tts/bin/python}"
NAME="${1:-out}"; BAR="${BAR:-200}"

# This engine assumes a 1920x1080 landscape source (overlay geometry + letterbox math are
# fixed to it). Fail loudly rather than silently misplace overlays on other geometries.
DIM=$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0:s=x source.mp4)
[ "$DIM" = "1920x1080" ] || { echo "ERROR: source is ${DIM}; this engine currently supports 1920x1080 only."; exit 1; }

echo "[1/5] original audio (for dub gap-passthrough)"
"$FF" -v error -y -i source.mp4 -ac 1 -ar 24000 -c:a pcm_s16le orig24k.wav

echo "[2/5] English dub (Kokoro, drift catch-up, gaps kept audible)"
"$PY" "$HERE/build_dub.py" en.srt final_audio.wav "${VOICE:-am_michael}" "${MAXSPEED:-1.85}" orig24k.wav 0.10

echo "[3/5] frames + on-screen-text OCR -> temporal spans"
# f1/ is needed by render_overlay for BOTH duration and per-box background sampling,
# so always extract it if absent — independently of the OCR (spans.json) cache.
[ -d f1 ] && [ -n "$(ls -A f1 2>/dev/null)" ] || { mkdir -p f1; "$FF" -v error -y -i source.mp4 -vf fps=1 f1/f_%04d.png; }
[ -f spans.json ] || { "$PY" "$HERE/dense_ocr.py"; "$PY" "$HERE/dedup_spans.py"; }

echo "[4/5] render English overlay + subtitle file"
"$PY" "$HERE/render_overlay.py" "${SCOPE:-targeted}" ov
"$PY" "$HERE/make_ass.py" "$BAR"

echo "[5/5] mux"
# v1: dub + subtitles in a letterbox bar
"$FF" -y -i source.mp4 -i final_audio.wav \
  -filter_complex "[0:v]pad=1920:$((1080+BAR)):0:0:black,subtitles=en.ass[v]" \
  -map "[v]" -map 1:a -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p \
  -c:a aac -b:a 160k -shortest "${NAME}_v1.mp4"
# v2: + burned-in visual overlay (1fps layer held per second)
"$FF" -y -i source.mp4 -framerate 1 -i ov/ov_%04d.png -i final_audio.wav \
  -filter_complex "[0:v][1:v]overlay=0:0:eof_action=pass:repeatlast=1[o];[o]pad=1920:$((1080+BAR)):0:0:black,subtitles=en.ass[v]" \
  -map "[v]" -map 2:a -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p \
  -c:a aac -b:a 160k -shortest "${NAME}_v2.mp4"
echo "DONE -> ${NAME}_v1.mp4  ${NAME}_v2.mp4"
