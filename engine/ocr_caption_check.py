#!/usr/bin/env python3
"""OCR the narrator caption (bottom-center band) for every ASR segment and flag
where it diverges from the ASR text. The caption is the creator's authoritative
transcript, so divergences are candidate ASR errors to review."""
import re, subprocess, os, difflib, sys
from ocrmac import ocrmac
from PIL import Image

FF="/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
os.makedirs("capframes", exist_ok=True)

src=open("source.srt",encoding="utf-8").read()
blocks=re.split(r"\n\s*\n",src.strip())
segs=[]
for b in blocks:
    m=re.search(r"(\d+):(\d+):(\d+),(\d+) --> (\d+):(\d+):(\d+),(\d+)",b)
    g=list(map(int,m.groups())); a=g[0]*3600+g[1]*60+g[2]+g[3]/1000; e=g[4]*3600+g[5]*60+g[6]+g[7]/1000
    txt=[l for l in b.splitlines() if l.strip()][-1]
    segs.append((a,e,txt))

def norm(s):  # strip spaces/punct for comparison
    return re.sub(r"[\s,.，。、？！?!\":：;；…·\-—()（）]","",s)

def caption_of(frame):
    """pick the bottom-center caption among OCR boxes."""
    res=ocrmac.OCR(frame, language_preference=["zh-Hans"]).recognize()
    cands=[]
    for txt,conf,box in res:        # box = (x,y,w,h) normalized, origin bottom-left
        if conf<0.3: continue
        cx=box[0]+box[2]/2
        # caption: horizontally centered-ish, spans lower band
        cands.append((abs(cx-0.5),txt))
    cands.sort()
    # join the most-centered 1-2 boxes
    return " ".join(t for _,t in cands[:2]) if cands else ""

rows=[]
for i,(a,e,asr) in enumerate(segs,1):
    t=(a+e)/2
    fr=f"capframes/s{i}.png"
    subprocess.run([FF,"-v","error","-y","-ss",f"{t:.2f}","-i","source.mp4","-frames:v","1",
                    "-vf","crop=1920:150:0:935",fr])  # bottom caption band
    ocr=caption_of(fr)
    sim=difflib.SequenceMatcher(None,norm(asr),norm(ocr)).ratio()
    rows.append((sim,i,asr,ocr))
    if i%30==0: print(f"...{i}/{len(segs)}",flush=True)

rows.sort()
print("\n==== LOWEST-SIMILARITY SEGMENTS (candidate ASR errors) ====")
for sim,i,asr,ocr in rows[:50]:
    print(f"\nseg{i} sim={sim:.2f}\n  ASR: {asr}\n  OCR: {ocr}")
# save full
with open("ocr_check.tsv","w",encoding="utf-8") as f:
    for sim,i,asr,ocr in sorted(rows,key=lambda r:r[1]):
        f.write(f"{i}\t{sim:.2f}\t{asr}\t{ocr}\n")
print("\nwrote ocr_check.tsv (all segments, in order)")
