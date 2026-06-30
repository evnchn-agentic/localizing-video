#!/bin/bash
# Letterbox (add bottom bar) + burn English subs in the bar + use the dub audio.
# Keeps the source's existing burned-in Chinese subs untouched (they stay in the 1080 area).
set -e
cd "$(dirname "$0")"
FF=/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg
BAR=200                      # bottom bar height (px); 1080+200 = 1280 (even)
OUT="${1:-loop_engineering_EN_dub.mp4}"

# en.ass carries explicit PlayResY=1280 so font/margins are real pixels (no libass rescale).
python3 make_ass.py $BAR

"$FF" -y -i source.mp4 -i final_audio.wav \
  -filter_complex "[0:v]pad=1920:$((1080+BAR)):0:0:black,subtitles=en.ass[v]" \
  -map "[v]" -map 1:a \
  -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p \
  -c:a aac -b:a 160k -shortest "$OUT"
echo "WROTE $OUT"
