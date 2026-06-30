#!/usr/bin/env python3
"""en.srt -> en.ass with explicit PlayResY so libass doesn't rescale font/margins.
Canvas = 1920 x (1080+BAR). Subs sit centered in the bottom BAR."""
import re, sys
BAR = int(sys.argv[1]) if len(sys.argv) > 1 else 200
H = 1080 + BAR

def to_ass_t(t):
    h=int(t//3600); m=int(t%3600//60); s=t%60
    return f"{h}:{m:02d}:{s:05.2f}"

# stamps + text both come from en.srt (the per-video data file) — no source.srt dependency
en = open("en.srt", encoding="utf-8").read()
stamps = re.findall(r"(\d+):(\d+):(\d+),(\d+) --> (\d+):(\d+):(\d+),(\d+)", en)
blocks = re.split(r"\n\s*\n", en.strip())
texts = []
for b in blocks:
    lines=[l for l in b.splitlines() if l.strip()]
    ti=next(i for i,l in enumerate(lines) if "-->" in l)
    texts.append(" ".join(lines[ti+1:]).strip())
assert len(stamps)==len(texts)

header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,46,&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,3,0,2,80,80,40,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
with open("en.ass","w",encoding="utf-8") as f:
    f.write(header)
    for st,txt in zip(stamps,texts):
        h1,m1,s1,ms1,h2,m2,s2,ms2 = map(int,st)
        a=h1*3600+m1*60+s1+ms1/1000; b=h2*3600+m2*60+s2+ms2/1000
        txt=txt.replace("{","(").replace("}",")")
        f.write(f"Dialogue: 0,{to_ass_t(a)},{to_ass_t(b)},Default,,0,0,0,,{txt}\n")
print(f"wrote en.ass  (PlayResY={H}, bar={BAR})")
