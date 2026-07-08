#!/usr/bin/env python3
"""
build_dub.py — turn an English SRT into a time-fitted Kokoro dub track (dub.wav).

Voice-agnostic timing engine:
  - pool adjacent SRT segments into ~sentence CHUNKS (ASR over-splits every breath;
    a chunk lets a long-English line borrow time from a short neighbour)
  - synth each chunk with Kokoro (free, local neural TTS, 24kHz)
  - if natural speech is longer than its window, speed it up (native Kokoro `speed`,
    capped) so it stays intelligible
  - ANCHOR each chunk at its true start (= the subtitle/video timeline). Drift CANNOT
    accumulate — every chunk is placed at its own timestamp, never pushed forward by a
    running cursor. (The old cursor/drift-catch-up approach accumulated ~+5s of lag by
    mid-video on dense back-to-back speech — see the skill's Time-density note.)
  - a chunk that still overflows its slot (audio > gap to the next anchor, even at the
    speed cap) is hard-capped with a 30ms fade — the burned subtitle carries the full
    line, so a clipped tail syllable beats multi-second desync. The deeper fix for a
    persistently-overflowing video is retiming the VISUALS (freeze-extend static slides);
    this engine only compresses the dub.

Usage: build_dub.py EN.srt OUT.wav [voice] [max_speed] [orig_wav] [duck]
"""
import sys, re, os, numpy as np, soundfile as sf
# point espeak-ng at the brew install (bundled loader data is broken on this box)
os.environ["ESPEAK_DATA_PATH"] = "/opt/homebrew/share/espeak-ng-data"
import espeakng_loader
espeakng_loader.get_data_path = lambda: "/opt/homebrew/share/espeak-ng-data"
espeakng_loader.get_library_path = lambda: "/opt/homebrew/lib/libespeak-ng.dylib"
from kokoro_onnx import Kokoro

SR = 24000
MAX_CHUNK = 6.0          # seconds — cap on a pooled utterance
GAP_SPLIT = 0.5          # a silent gap > this always ends a chunk


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
        ti = next(i for i,l in enumerate(lines) if "-->" in l)
        text = " ".join(lines[ti+1:]).strip()
        if text:
            segs.append((start, end, text))
    return segs


def chunk_segs(segs):
    """Pool adjacent segments into ~sentence utterances. Each chunk carries its true
    start, and win_end = the NEXT chunk's start (so it may use any silent gap that
    follows it before the next line is due)."""
    chunks = []
    cur = None
    for i, (start, end, text) in enumerate(segs):
        gap_next = (segs[i+1][0] - end) if i+1 < len(segs) else 9.9
        if cur is None:
            cur = {"start": start, "end": end, "text": text}
        else:
            cur["end"] = end
            cur["text"] += " " + text
        ends_sentence = text.rstrip().endswith((".", "!", "?", "—", "…", "\""))
        too_long = (cur["end"] - cur["start"]) >= MAX_CHUNK
        if ends_sentence or too_long or gap_next > GAP_SPLIT:
            cur["win_end"] = segs[i+1][0] if i+1 < len(segs) else end + 2.0
            chunks.append(cur)
            cur = None
    if cur is not None:
        cur["win_end"] = segs[-1][1] + 2.0
        chunks.append(cur)
    return chunks


def main():
    srt, out = sys.argv[1], sys.argv[2]
    voice = sys.argv[3] if len(sys.argv) > 3 else "am_michael"
    max_speed = float(sys.argv[4]) if len(sys.argv) > 4 else 1.9
    orig_wav = sys.argv[5] if len(sys.argv) > 5 else None   # original audio for gap passthrough
    duck = float(sys.argv[6]) if len(sys.argv) > 6 else 0.10  # original gain UNDER narration

    segs = parse_srt(srt)
    chunks = chunk_segs(segs)
    print(f"{len(segs)} segments -> {len(chunks)} chunks, voice={voice}, "
          f"max_speed={max_speed}, duck={duck}")
    kok = Kokoro("kokoro-v1.0.onnx", "voices-v1.0.bin")

    import hashlib
    os.makedirs("synth_cache", exist_ok=True)
    def synth(text, speed):
        key = hashlib.md5(f"{voice}|{speed:.2f}|{text}".encode()).hexdigest()
        p = f"synth_cache/{key}.npy"
        if os.path.exists(p):
            return np.load(p)
        s,_ = kok.create(text, voice=voice, speed=speed, lang="en-us")
        s = s.astype(np.float32); np.save(p, s); return s

    total = max(c["win_end"] for c in chunks) + 8.0
    master = np.zeros(int(total*SR), dtype=np.float32)
    spoken = np.zeros(len(master), dtype=bool)   # where English dub actually plays

    FADE = int(0.03*SR)
    cps = 15.5            # chars/sec @ speed 1.0, adapted online
    n_clip = 0
    for i, c in enumerate(chunks):
        start, win_end, text = c["start"], c["win_end"], c["text"]
        window = max(0.4, win_end - start)
        est_base = max(0.3, len(text)/cps)            # est duration @ speed 1.0
        speed = min(max_speed, max(1.0, est_base/(window-0.05)))
        samples = synth(text, speed)
        dur = len(samples)/SR
        cps = 0.85*cps + 0.15*(len(text)/(dur*speed))  # EMA update of chars/sec
        # ANCHOR at true start — never a running cursor, so drift can't accumulate.
        cap = int(window*SR)                           # hard cap = this chunk's own slot
        if len(samples) > cap:
            samples = samples[:cap].copy()
            if len(samples) > FADE:
                samples[-FADE:] *= np.linspace(1.0, 0.0, FADE, dtype=np.float32)
            n_clip += 1
        a = int(start*SR); b = a+len(samples)
        if b > len(master):
            pad = b-len(master)
            master = np.concatenate([master, np.zeros(pad, dtype=np.float32)])
            spoken = np.concatenate([spoken, np.zeros(pad, dtype=bool)])
        master[a:b] += samples
        spoken[a:b] = True
        if i % 15 == 0:
            print(f"[{i+1:3}/{len(chunks)}] t={start:6.1f} win={window:4.1f} "
                  f"say={dur:4.1f} sp={speed:.2f} | {text[:42]}", flush=True)
    print(f"chunks placed={len(chunks)}  hard-capped={n_clip}  (subtitle carries full text)")

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
