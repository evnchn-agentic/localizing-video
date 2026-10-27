#!/usr/bin/env python3
"""
freeze_extend.py — buy the dub airtime by holding static frames (Time-density lever 2).

Run BEFORE build_dub / OCR. It plans the dub on the original timeline (same chunking and
speed choice as build_dub.py), finds chunks whose speech overruns their slot, and inserts
short freeze-frame holds where all three of the skill's conditions hold:
  (i)  timeline edit: the hold is inserted into video AND original audio, and every SRT
       timestamp after it shifts by the same frame-rounded amount;
  (ii) the bed pauses: the hold point sits inside an ffmpeg `silencedetect` span (a
       narrator's breath is enough: the original is ducked under the dub there anyway);
  (iii) the frame is static: the hold point sits inside an ffmpeg `freezedetect` span
       (caption band cropped off, so a caption change is not counted as motion).
Many tiny holds, never one drag: each hold is capped at MAX_HOLD seconds.

Usage: freeze_extend.py SOURCE.mp4 EN.srt OUTDIR [voice] [max_speed]
Writes OUTDIR/source.mp4, OUTDIR/en.srt, OUTDIR/holds.json. Then run the engine in OUTDIR.
PLAN=1 prints the plan and stops before the (slow) re-encode.
Tunables (env): MAX_HOLD=1.0  MARGIN=0.15  SIL_MIN=0.08  SIL_DB=-30  FREEZE_DB=-50  CAPTION_BAND=0.2
"""
import sys, os, re, json, subprocess, numpy as np, soundfile as sf
from build_dub import parse_srt, chunk_segs, fit, SR

FF = os.environ.get("FF", "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg")
MAX_HOLD = float(os.environ.get("MAX_HOLD", 1.0))   # seconds per hold
MARGIN = float(os.environ.get("MARGIN", 0.15))      # frame static this long on BOTH sides
SIL_MIN = float(os.environ.get("SIL_MIN", 0.08))    # shortest pause in the bed to hold inside
SIL_DB = os.environ.get("SIL_DB", "-30")  # ducked ~20 dB under the dub, so ~-50 dB heard
FREEZE_DB = os.environ.get("FREEZE_DB", "-50")
BAND = float(os.environ.get("CAPTION_BAND", 0.2))   # bottom fraction ignored for "static"


def spans(log, kind):
    """(start, end) pairs from ffmpeg freezedetect/silencedetect stderr."""
    s = [float(x) for x in re.findall(rf"{kind}_start: ([\d.]+)", log)]
    e = [float(x) for x in re.findall(rf"{kind}_end: ([\d.]+)", log)]
    return list(zip(s, e + [1e9] * (len(s) - len(e))))   # a span still open at EOF


def intersect(a, b):
    out, i, j = [], 0, 0
    while i < len(a) and j < len(b):
        lo, hi = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if lo < hi:
            out.append((lo, hi))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return out


def main():
    src, srt, outdir = sys.argv[1], sys.argv[2], sys.argv[3]
    voice = sys.argv[4] if len(sys.argv) > 4 else "am_michael"
    max_speed = float(sys.argv[5]) if len(sys.argv) > 5 else 1.85
    os.makedirs(outdir, exist_ok=True)

    rates = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate,avg_frame_rate", "-of", "csv=p=0", src], text=True).strip()
    r, avg = rates.split(",")
    if r != avg:   # frame index <-> time must be exact; remux first: ffmpeg -i in -fps_mode cfr ...
        sys.exit(f"variable frame rate ({r} vs avg {avg}): convert {src} to constant frame rate first")
    num, den = r.split("/")
    fps = int(num) / int(den)

    log = subprocess.run([FF, "-nostats", "-hide_banner", "-i", src,
        "-vf", f"crop=iw:ih*{1-BAND}:0:0,scale=480:-2,freezedetect=n={FREEZE_DB}dB:d={2*MARGIN}",
        "-af", f"silencedetect=n={SIL_DB}dB:d={SIL_MIN}", "-f", "null", "-"],
        capture_output=True, text=True).stderr
    pad = lambda sp, m: [(lo + m, hi - m) for lo, hi in sp if hi - lo > 2 * m]
    ok = intersect(pad(spans(log, "freeze"), MARGIN), pad(spans(log, "silence"), SIL_MIN / 4))

    # hold points: the middle frame of each static+silent spot, widest spots tried first
    spots = sorted({round((lo + hi) / 2 * fps): hi - lo for lo, hi in ok}.items(), key=lambda s: -s[1])
    cap, holds = round(MAX_HOLD * fps), {}   # frame index -> frames held there

    def shift(t):   # original time -> held time
        return t + sum(n for f, n in holds.items() if f / fps <= t) / fps

    segs = parse_srt(srt)
    # A hold widens a slot, so build_dub picks a slower speed and the synth gets longer.
    # Re-plan on the held timeline with build_dub's own fit until nothing changes.
    for _ in range(6):
        short, changed = 0.0, False
        chunks = chunk_segs([(shift(a), shift(b), txt) for a, b, txt in segs])
        # spot positions on THIS pass's timeline (holds added below move later spots next pass)
        pos = {f: f / fps + sum(n for g, n in holds.items() if g < f) / fps for f, _ in spots}
        for c, samples, window, _ in fit(chunks, voice, max_speed):
            need = len(samples) / SR - window
            for f, _ in spots:
                if need <= 0:
                    break
                if c["start"] < pos[f] < c["win_end"]:
                    add = min(cap - holds.get(f, 0), int(np.ceil((need + 0.05) * fps)))
                    if add > 0:
                        holds[f] = holds.get(f, 0) + add
                        need -= add / fps
                        changed = True
            short += max(0.0, need)
        if not changed:
            break
    else:
        print("WARNING: did not converge in 6 passes; the overrun figure below is approximate")
    plan = [{"t": round(f / fps, 4), "frames": n, "sec": n / fps} for f, n in sorted(holds.items())]
    tot = sum(h["sec"] for h in plan)
    print(f"{len(plan)} holds, {tot:.1f}s added (max {max((h['sec'] for h in plan), default=0):.2f}s); "
          f"{short:.1f}s of overrun had no static+silent spot (build_dub will hard-cap it)")
    print("holds at (source s):", " ".join(f"{h['t']:.1f}+{h['sec']:.2f}" for h in plan))
    if os.environ.get("PLAN"):
        return

    def ts(m):
        t = shift(int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) + int(m[4]) / 1000)
        ms = round(t * 1000)
        return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"
    txt = open(srt, encoding="utf-8").read()
    open(f"{outdir}/en.srt", "w", encoding="utf-8").write(re.sub(r"^.*-->.*$",   # cue lines only
        lambda line: re.sub(r"(\d+):(\d+):(\d+)[,.](\d+)", ts, line[0]), txt, flags=re.M))

    # original audio: insert silence of exactly the held frames' duration at each hold
    subprocess.run([FF, "-v", "error", "-y", "-i", src, "-vn", f"{outdir}/bed.wav"], check=True)
    bed, asr = sf.read(f"{outdir}/bed.wav", dtype="float32", always_2d=True)
    parts, prev = [], 0
    for h in plan:
        a = round(h["t"] * asr)
        parts += [bed[prev:a], np.zeros((round(h["frames"] / fps * asr), bed.shape[1]), np.float32)]
        prev = a
    sf.write(f"{outdir}/bed.wav", np.concatenate(parts + [bed[prev:]]), asr)

    # video: one `loop` per hold repeats a single frame; indexes count earlier holds' frames
    vf, added = [], 0
    for h in plan:
        vf.append(f"loop=loop={h['frames']}:size=1:start={round(h['t'] * fps) + added}")
        added += h["frames"]
    vf.append(f"setpts=N/({num}/{den})/TB")
    subprocess.run([FF, "-v", "error", "-y", "-i", src, "-i", f"{outdir}/bed.wav",
        "-filter_complex", f"[0:v]{','.join(vf)}[v]", "-map", "[v]", "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", f"{outdir}/source.mp4"], check=True)
    os.remove(f"{outdir}/bed.wav")

    json.dump({"fps": fps, "holds": plan}, open(f"{outdir}/holds.json", "w"), indent=1)


if __name__ == "__main__":
    main()
