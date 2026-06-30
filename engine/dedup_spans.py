#!/usr/bin/env python3
"""Group per-second OCR boxes into temporal spans (same text+position persisting
across frames). Output spans.json + strings_to_translate.json."""
import json, re, difflib
from collections import Counter

raw=json.load(open("dense_raw.json"))
raw={int(k):v for k,v in raw.items()}
W,H=1920,1080
def norm(s): return re.sub(r"[\s,.，。、？！?!\":：;；…·\-—()（）()【】\[\]]","",s)

# active spans get extended; closed when not seen for GAP seconds
GAP=2
spans=[]      # each: dict(zh_variants Counter, cx,cy,w,h sums/n, t0,t1, last)
open_spans=[]
for t in sorted(raw):
    used=set()
    for b in raw[t]:
        nb=norm(b["zh"])
        if not nb: continue
        cx=b["x"]+b["w"]/2; cy=b["y"]+b["h"]/2
        best=None;bd=1e9
        for s in open_spans:
            if id(s) in used: continue
            # position match (within 4% of frame) + text similarity
            d=((cx-s["cx"])**2+(cy-s["cy"])**2)**0.5
            sim=difflib.SequenceMatcher(None,nb,norm(s["rep"])).ratio()
            if d< max(60, b["h"]*1.2) and sim>0.5 and d<bd:
                best=s;bd=d
        if best is None:
            s=dict(variants=Counter(),cx=cx,cy=cy,w=b["w"],h=b["h"],t0=t,t1=t,last=t,n=1,rep=b["zh"])
            s["variants"][b["zh"]]+=1
            open_spans.append(s); spans.append(s); used.add(id(s))
        else:
            best["variants"][b["zh"]]+=1
            best["t1"]=t; best["last"]=t; best["n"]+=1
            # EMA position
            a=0.3; best["cx"]=(1-a)*best["cx"]+a*cx; best["cy"]=(1-a)*best["cy"]+a*cy
            best["w"]=max(best["w"],b["w"]); best["h"]=max(best["h"],b["h"])
            best["rep"]=best["variants"].most_common(1)[0][0]
            used.add(id(best))
    open_spans=[s for s in open_spans if t-s["last"]<=GAP]

result=[]
for s in spans:
    dur=s["t1"]-s["t0"]+1
    if dur<2 and s["n"]<2: continue           # drop 1-frame flickers
    rep=s["variants"].most_common(1)[0][0]
    result.append({"zh":rep,"t0":s["t0"],"t1":s["t1"]+1,
                   "x":round(s["cx"]-s["w"]/2),"y":round(s["cy"]-s["h"]/2),
                   "w":round(s["w"]),"h":round(s["h"]),"n":s["n"]})
result.sort(key=lambda r:(r["t0"],r["x"]))
json.dump(result, open("spans.json","w"), ensure_ascii=False, indent=1)

uniq=sorted({r["zh"] for r in result})
json.dump({z:"" for z in uniq}, open("strings_to_translate.json","w"), ensure_ascii=False, indent=1)
print(f"{len(result)} spans, {len(uniq)} unique strings")
print(f"total on-screen-text-seconds: {sum(r['t1']-r['t0'] for r in result)}")
