#!/usr/bin/env python3
"""Render per-second RGBA overlay PNGs that cover Chinese boxes with English.
Usage: render_overlay.py <targeted|full> <outdir> [only_second]"""
import json, sys, os, glob
import numpy as np
from PIL import Image, ImageDraw, ImageFont

mode   = sys.argv[1] if len(sys.argv)>1 else "targeted"
outdir = sys.argv[2] if len(sys.argv)>2 else f"ov_{mode}"
only   = int(sys.argv[3]) if len(sys.argv)>3 else None
os.makedirs(outdir, exist_ok=True)
W,H=1920,1080

spans=json.load(open("spans.json"))
trans=json.load(open("translations.json"))

FONT=None
for p in ["/System/Library/Fonts/Supplemental/Arial Bold.ttf",
          "/System/Library/Fonts/Supplemental/Arial.ttf",
          "/System/Library/Fonts/Helvetica.ttc"]:
    if os.path.exists(p): FONT=p; break
def font(sz): return ImageFont.truetype(FONT, sz)

def wrap(draw, text, fnt, maxw):
    words=text.split(); lines=[]; cur=""
    for w in words:
        t=(cur+" "+w).strip()
        if draw.textlength(t,font=fnt)<=maxw or not cur: cur=t
        else: lines.append(cur); cur=w
    if cur: lines.append(cur)
    return lines

def fit(draw, text, boxw, boxh):
    """largest font size whose wrapped text fits the box."""
    lo,hi,best=10,min(boxh,80),10
    while lo<=hi:
        mid=(lo+hi)//2; fnt=font(mid)
        lines=wrap(draw,text,fnt,boxw-8)
        lh=mid*1.18; total=lh*len(lines)
        widest=max((draw.textlength(l,font=fnt) for l in lines),default=0)
        if total<=boxh-4 and widest<=boxw-8: best=mid; lo=mid+1
        else: hi=mid-1
    return font(best), wrap(draw,text,font(best),boxw-8)

def active_at(s):
    out=[]
    for sp in spans:
        if not (sp["t0"]<=s<sp["t1"]): continue
        en=trans.get(sp["zh"],"")
        if not en: continue
        if en.startswith("~"):
            if mode!="full": continue
            en=en[1:]
        out.append((sp,en))
    return out

NF=len(glob.glob("f1/f_*.png")) or 481   # derive duration from extracted frames (not hardcoded)
secs=[only] if only is not None else range(NF)
frames_for_color={}
for s in secs:
    act=active_at(s)
    img=Image.new("RGBA",(W,H),(0,0,0,0))
    if act:
        d=ImageDraw.Draw(img)
        # source frame for bg-color sampling
        fp=f"f1/f_{s+1:04d}.png"
        src=np.asarray(Image.open(fp).convert("RGB")) if os.path.exists(fp) else None
        for sp,en in act:
            x,y,w,h=sp["x"],sp["y"],sp["w"],sp["h"]
            x=max(0,x);y=max(0,y);w=min(w,W-x);h=min(h,H-y)
            if w<8 or h<8: continue
            pad=4; bx0,by0,bx1,by1=max(0,x-pad),max(0,y-pad),min(W,x+w+pad),min(H,y+h+pad)
            # sample bg = median of the box region (text is minority of pixels)
            if src is not None:
                crop=src[by0:by1,bx0:bx1].reshape(-1,3)
                bg=tuple(int(v) for v in np.median(crop,axis=0))
            else: bg=(240,240,240)
            lum=0.299*bg[0]+0.587*bg[1]+0.114*bg[2]
            fg=(20,20,20) if lum>140 else (245,245,245)
            d.rectangle([bx0,by0,bx1,by1],fill=bg+(255,))
            fnt,lines=fit(d,en,w,h)
            lh=fnt.size*1.18; ty=y+(h-lh*len(lines))/2
            for ln in lines:
                tw=d.textlength(ln,font=fnt)
                d.text((x+(w-tw)/2,ty),ln,font=fnt,fill=fg+(255,))
                ty+=lh
    img.save(f"{outdir}/ov_{s:04d}.png")
print(f"{mode}: rendered {len(list(secs))} overlay frames -> {outdir}/")
