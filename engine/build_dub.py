#!/usr/bin/env python3
"""
build_dub.py — turn an English SRT into a time-fitted Kokoro dub track (dub.wav).

Voice-agnostic timing engine:
  - synth each segment with Kokoro (free, local neural TTS, 24kHz)
  - if natural speech is longer than its SRT window, speed it up (native Kokoro
    `speed`, capped) so it stays intelligible; mild overflow allowed into gaps
  - lay segments on a silent master track at their start offsets, pushing a
    start forward only if the previous segment overran (no overlap, re-syncs at gaps)

Usage: build_dub.py EN.srt OUT.wav [voice] [max_speed]
"""
import sys, re, os, numpy as np, soundfile as sf
# point espeak-ng at the brew install (bundled loader data is broken on this box)
os.environ["ESPEAK_DATA_PATH"] = "/opt/homebrew/share/espeak-ng-data"
import espeakng_loader
espeakng_loader.get_data_path = lambda: "/opt/homebrew/share/espeak-ng-data"
espeakng_loader.get_library_path = lambda: "/opt/homebrew/lib/libespeak-ng.dylib"
from kokoro_onnx import Kokoro

SR = 24000

def parse_srt(path):
    txt = open(path, encoding="utf-8").read()
    blocks = re.split(r"\n\s*\n", txt.strip())
    segs = []
    for b in blocks:
        lines = [l for l in b.splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        m = re.search(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)", b)
        if not m:
            continue
        h1,m1,s1,ms1,h2,m2,s2,ms2 = map(int, m.groups())
        start = h1*3600+m1*60+s1+ms1/1000
        end   = h2*3600+m2*60+s2+ms2/1000
        # text = lines after the timestamp line
        ti = next(i for i,l in enumerate(lines) if "-->" in l)
        text = " ".join(lines[ti+1:]).strip()
        if text:
            segs.append((start, end, text))
    return segs

def main():
    srt, out = sys.argv[1], sys.argv[2]
    voice = sys.argv[3] if len(sys.argv) > 3 else "am_michael"
    max_speed = float(sys.argv[4]) if len(sys.argv) > 4 else 1.6
    orig_wav = sys.argv[5] if len(sys.argv) > 5 else None   # original audio for gap passthrough
    duck = float(sys.argv[6]) if len(sys.argv) > 6 else 0.10  # original gain UNDER narration

    segs = parse_srt(srt)
    print(f"{len(segs)} segments, voice={voice}, max_speed={max_speed}, duck={duck}")
    kok = Kokoro("kokoro-v1.0.onnx", "voices-v1.0.bin")

    import hashlib, os
    os.makedirs("synth_cache", exist_ok=True)
    def synth(text, speed):
        key = hashlib.md5(f"{voice}|{speed:.2f}|{text}".encode()).hexdigest()
        p = f"synth_cache/{key}.npy"
        if os.path.exists(p):
            return np.load(p)
        s,_ = kok.create(text, voice=voice, speed=speed, lang="en-us")
        s = s.astype(np.float32); np.save(p, s); return s

    total = max(e for _,e,_ in segs) + 8.0
    master = np.zeros(int(total*SR), dtype=np.float32)
    spoken = np.zeros(len(master), dtype=bool)   # where English dub actually plays

    cps = 15.5            # chars/sec @ speed 1.0, adapted online
    cursor = 0.0
    for i,(start,end,text) in enumerate(segs):
        window = max(0.3, end - start)
        drift = cursor - start                       # how far behind original we are
        target = window
        if drift > 0.4:                              # claw back: shorten target to recover
            target = max(window*0.55, window - drift)
        est_base = max(0.3, len(text)/cps)           # est duration @ speed 1.0
        speed = min(max_speed, max(1.0, est_base/target))
        samples = synth(text, speed)
        dur = len(samples)/SR
        cps = 0.85*cps + 0.15*(len(text)/(dur*speed))  # EMA update of chars/sec
        place = max(start, cursor)                    # never before its cue; no overlap
        a = int(place*SR); b = a+len(samples)
        if b > len(master):
            pad = b-len(master)
            master = np.concatenate([master, np.zeros(pad, dtype=np.float32)])
            spoken = np.concatenate([spoken, np.zeros(pad, dtype=bool)])
        master[a:b] += samples
        spoken[a:b] = True
        cursor = place + dur
        print(f"[{i+1:3}/{len(segs)}] win={window:4.1f} say={dur:4.1f} sp={speed:.2f} "
              f"drift={place-start:+5.1f} | {text[:42]}", flush=True)

    # normalize the dub
    peak = np.max(np.abs(master)) or 1.0
    master = master/peak*0.97

    if orig_wav:
        orig, osr = sf.read(orig_wav, dtype="float32")
        if orig.ndim > 1: orig = orig.mean(axis=1)
        if len(orig) < len(master):
            orig = np.concatenate([orig, np.zeros(len(master)-len(orig), dtype=np.float32)])
        else:
            orig = orig[:len(master)]
        # gain envelope for ORIGINAL: full (1.0) in gaps, ducked under narration.
        # smooth the spoken mask edges (~120ms) so the duck ramps, no clicks.
        env = np.where(spoken, duck, 1.0).astype(np.float32)
        win = int(0.12*SR)
        kern = np.ones(win, dtype=np.float32)/win
        env = np.convolve(env, kern, mode="same")
        final = orig*env + master
        peak = np.max(np.abs(final)) or 1.0
        if peak > 0.99:
            final = final/peak*0.97
        sf.write(out, final.astype(np.float32), SR)
        gapsec = (len(spoken)-spoken.sum())/SR
        print(f"wrote {out}  ({len(final)/SR:.1f}s)  | gap/clip passthrough ~{gapsec:.0f}s at full vol")
    else:
        sf.write(out, master.astype(np.float32), SR)
        print(f"wrote {out}  ({len(master)/SR:.1f}s)  | dub only")

if __name__ == "__main__":
    main()
