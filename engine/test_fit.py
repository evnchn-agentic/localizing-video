#!/usr/bin/env python3
"""fit() must resynth faster (within the cap) instead of overflowing when its chars/sec
estimate undershoots. Fake TTS: 10 chars/sec at speed 1, slower than build_dub's 15.5 guess.
Run with the engine's venv: ./venv-tts/bin/python engine/test_fit.py"""
import os, tempfile, numpy as np
import build_dub


class FakeKokoro:
    def __init__(self, *a): pass
    def create(self, text, voice, speed, lang):
        return np.zeros(int(len(text) / 10 / speed * build_dub.SR), np.float32), build_dub.SR


build_dub.Kokoro = FakeKokoro
os.chdir(tempfile.mkdtemp())   # fresh synth_cache
chunks = [{"start": 0.0, "win_end": 3.0, "text": "x" * 40}]   # 4.0 s at speed 1, fits at ~1.4
(c, samples, window, speed), = build_dub.fit(chunks, "v", 1.9)
assert len(samples) / build_dub.SR <= window, f"overflows at speed {speed:.2f} with cap 1.9"
assert speed < 1.9
print(f"ok: speed {speed:.2f}, {len(samples)/build_dub.SR:.2f}s in a {window:.1f}s slot")
