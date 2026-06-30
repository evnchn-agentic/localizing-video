#!/usr/bin/env python3
"""Dense OCR: OCR every 1fps frame full-res, filter watermark + narrator caption,
keep Chinese boxes. Save raw per-second boxes to dense_raw.json (re-usable)."""
import json, re, glob, sys
from ocrmac import ocrmac
W,H=1920,1080
def has_cjk(s): return bool(re.search(r'[一-鿿]',s))

frames=sorted(glob.glob("f1/f_*.png"))
out={}
for idx,fr in enumerate(frames):
    t=idx  # f_0001 -> t≈0s
    res=ocrmac.OCR(fr, language_preference=["zh-Hans","en-US"]).recognize()
    boxes=[]
    for txt,conf,(x,y,w,h) in res:
        if conf<0.4 or not has_cjk(txt): continue
        if "闪客" in txt: continue
        px=x*W; py=(1-y-h)*H; pw=w*W; ph=h*H
        cx=px+pw/2; cy=py+ph/2
        if cy>0.87*H and 0.2*W<cx<0.8*W: continue      # narrator caption band
        boxes.append({"zh":txt.strip(),"conf":round(conf,2),
                      "x":round(px),"y":round(py),"w":round(pw),"h":round(ph)})
    out[t]=boxes
    if idx%40==0: print(f"...{idx}/{len(frames)}  ({len(boxes)} boxes @t={t})",flush=True)

json.dump(out, open("dense_raw.json","w"), ensure_ascii=False)
nb=sum(len(v) for v in out.values())
uniq=len({b['zh'] for v in out.values() for b in v})
print(f"done: {nb} boxes over {len(out)} frames, {uniq} unique strings -> dense_raw.json")
