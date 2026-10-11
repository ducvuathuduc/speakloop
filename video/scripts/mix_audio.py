"""Mix the synthesised score with the Kokoro voice lines: each line at -16 LUFS, music ducked under it.

Usage: python3 scripts/mix_audio.py launch|teaser   -> public/mix_launch.wav | public/mix_teaser.wav
Line timings live in src/vo.json. Needs numpy, scipy, soundfile, pyloudnorm.
"""
import json
import sys
from math import gcd
from pathlib import Path

import numpy as np
import pyloudnorm as pyln
import soundfile as sf
from scipy.ndimage import maximum_filter1d, uniform_filter1d
from scipy.signal import lfilter, resample_poly

HERE = Path(__file__).resolve().parent.parent
SR = 44100
VO_LUFS, MUSIC_LUFS, DUCK_DB = -16.0, -18.0, -9.0


def limit(x, ceiling_db=-2.0, sr=SR):
    """Look-ahead peak limiter: ~2 ms look-ahead, instant attack, 40 ms release. No hard clipping."""
    c = 10 ** (ceiling_db / 20)
    need = np.minimum(1.0, c / np.maximum(np.abs(x), 1e-9))
    if x.ndim > 1:
        need = need.min(axis=1)
    g = -maximum_filter1d(-need, size=int(0.004 * sr) + 1)
    g = uniform_filter1d(g, size=int(0.002 * sr) + 1)
    # release: one-pole smoothing that only lets gain rise slowly (min with the requirement keeps attack instant)
    a = np.exp(-1 / (0.04 * sr))
    rel = lfilter([1 - a], [1, -a], g, zi=[g[0] * a])[0]
    g = np.minimum(g, rel)
    y = x * (g[:, None] if x.ndim > 1 else g)
    return np.clip(y, -c, c)


def lufs(meter, a):
    return meter.integrated_loudness(np.pad(a, [(0, max(0, int(0.45 * SR) - len(a)))] + [(0, 0)] * (a.ndim - 1)))


def main(which):
    total = {"launch": 138.0, "teaser": 32.0}[which]
    music, msr = sf.read(HERE / "public" / ("music.wav" if which == "launch" else "music_teaser.wav"), dtype="float64")
    assert msr == SR
    if music.ndim == 1:
        music = np.stack([music, music], 1)
    N = int(total * SR)
    music = np.pad(music, ((0, max(0, N - len(music))), (0, 0)))[:N]
    meter = pyln.Meter(SR)
    music *= 10 ** ((MUSIC_LUFS - meter.integrated_loudness(music)) / 20)

    voice = np.zeros(N)
    duck = np.zeros(N)
    for ev in json.loads((HERE / "src" / "vo.json").read_text())[which]:
        a, sr = sf.read(HERE / "public" / "vo" / f"{ev['clip']}.wav", dtype="float64")
        g = gcd(sr, SR)
        a = resample_poly(a, SR // g, sr // g)
        target = VO_LUFS + ev.get("gain_db", 0)
        for _ in range(3):  # normalise, limit the peaks, re-normalise
            a = limit(a * 10 ** ((target - lufs(meter, a)) / 20))
        print(f"  {ev['clip']:8s} @ {ev['at']:7.3f}s  {lufs(meter, a):6.1f} LUFS  peak {20 * np.log10(np.abs(a).max()):5.1f} dBFS")
        i = int(ev["at"] * SR)
        j = min(N, i + len(a))
        voice[i:j] += a[: j - i]
        duck[i:j] = 1
    # duck envelope: 120 ms ramp down before each line, 450 ms release after it
    att, rel = int(0.12 * SR), int(0.45 * SR)
    d = duck.copy()
    for s in np.flatnonzero(np.diff(np.r_[0, duck]) == 1):
        s0 = max(0, s - att)
        d[s0:s] = np.maximum(d[s0:s], np.linspace(0, 1, s - s0))
    for e in np.flatnonzero(np.diff(np.r_[duck, 0]) == -1):
        k = min(N, e + rel) - e
        d[e : e + k] = np.maximum(d[e : e + k], np.linspace(1, 0, k))
    mix = music * (10 ** (DUCK_DB * d / 20))[:, None] + voice[:, None]
    pre = 20 * np.log10(np.abs(mix).max())
    mix = limit(mix, -1.0)
    sf.write(HERE / "public" / f"mix_{which}.wav", mix.astype(np.float32), SR, subtype="PCM_16")
    print(f"{which}: music {MUSIC_LUFS} LUFS, voice {VO_LUFS} LUFS, duck {DUCK_DB} dB -> mix {meter.integrated_loudness(mix):.1f} LUFS, "
          f"peak {20 * np.log10(np.abs(mix).max()):.2f} dBFS (before limiter {pre:.2f})")


if __name__ == "__main__":
    main(sys.argv[1])
