#!/bin/bash
# Burn the English visual overlay (1fps PNG layer) + letterbox + EN subtitle bar + dub audio.
set -e
cd "$(dirname "$0")"
FF=/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg
OVDIR="$1"; OUT="$2"; BAR=200
python3 make_ass.py $BAR >/dev/null
"$FF" -y -i source.mp4 -framerate 1 -i "$OVDIR/ov_%04d.png" -i final_audio.wav \
  -filter_complex "[0:v][1:v]overlay=0:0:eof_action=pass:repeatlast=1[o];[o]pad=1920:$((1080+BAR)):0:0:black,subtitles=en.ass[v]" \
  -map "[v]" -map 2:a \
  -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p \
  -c:a aac -b:a 160k -shortest "$OUT"
echo "WROTE $OUT"
