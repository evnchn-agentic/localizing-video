#!/usr/bin/env python3
"""Stage-1 visual extraction: merge scene cuts into content intervals, OCR a
representative full-res frame per interval, filter out watermark + narrator
caption band, dump Chinese boxes to visual_boxes.json for translation."""
import subprocess, json, re, os
from ocrmac import ocrmac
from PIL import Image

FF="/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg"
FP="/opt/homebrew/opt/ffmpeg-full/bin/ffprobe"
W,H=1920,1080
WM=os.environ.get("WATERMARK","闪客")   # creator watermark substring to drop; per-video/creator
DUR=float(subprocess.check_output(
    [FP,"-v","error","-show_entries","format=duration","-of","default=nw=1:nk=1","source.mp4"]
).decode().strip())

if not os.path.exists("scene_times.txt"):   # auto-detect scene cuts if not supplied
    log=subprocess.run([FF,"-i","source.mp4","-filter:v","select='gt(scene,0.3)',showinfo",
                        "-f","null","-"], capture_output=True, text=True).stderr
    open("scene_times.txt","w").write("\n".join(re.findall(r"pts_time:([0-9.]+)", log)))
cuts=[float(x) for x in open("scene_times.txt").read().split()]
cuts=[0.0]+cuts+[DUR]
# merge cuts < 2.0s apart -> interval boundaries
bounds=[cuts[0]]
for c in cuts[1:]:
    if c-bounds[-1] >= 2.0: bounds.append(c)
if DUR-bounds[-1] > 0.5: bounds.append(DUR)
scenes=[(bounds[i],bounds[i+1]) for i in range(len(bounds)-1)]
print(f"{len(scenes)} content intervals")

def has_cjk(s): return bool(re.search(r'[一-鿿]',s))

out=[]
for si,(t0,t1) in enumerate(scenes):
    tm=(t0+t1)/2
    fr=f"vis_{si:02d}.png"
    subprocess.run([FF,"-v","error","-y","-ss",f"{tm:.2f}","-i","source.mp4","-frames:v","1",fr])
    res=ocrmac.OCR(fr, language_preference=["zh-Hans","en-US"]).recognize()
    boxes=[]
    for txt,conf,(x,y,w,h) in res:
        if conf<0.35 or not has_cjk(txt): continue
        if WM and WM in txt: continue                  # creator watermark (set WATERMARK env)
        px=x*W; py=(1-y-h)*H; pw=w*W; ph=h*H
        cy=py+ph/2; cx=px+pw/2
        # drop narrator caption: bottom ~13% and horizontally central
        if cy > 0.87*H and 0.2*W < cx < 0.8*W: continue
        boxes.append({"zh":txt.strip(),"conf":round(conf,2),
                      "x":round(px),"y":round(py),"w":round(pw),"h":round(ph)})
    if boxes:
        out.append({"scene":si,"t0":round(t0,2),"t1":round(t1,2),"frame":fr,"boxes":boxes})
        print(f"scene{si:02d} [{t0:6.1f}-{t1:6.1f}] {len(boxes)} zh boxes")

json.dump(out, open("visual_boxes.json","w"), ensure_ascii=False, indent=1)
allz=sorted({b["zh"] for s in out for b in s["boxes"]})
print(f"\n{len(out)} scenes with zh, {len(allz)} unique strings -> visual_boxes.json")
