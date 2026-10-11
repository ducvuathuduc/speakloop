"""Synthesise the SpeakLoop launch-film score from scratch (no samples, no third-party audio).

120 BPM, 4/4, A minor. One bar = 2.0 s = 60 frames at 30 fps, so every scene boundary in
src/timeline.ts (multiples of 60 frames) lands on a downbeat. Output: public/music.wav
Usage: python3 scripts/make_music.py [config.json] [out.wav]
"""
import json
import sys
from pathlib import Path

import numpy as np
from scipy.signal import butter, sosfilt

SR = 44100
BPM = 120
BEAT = 60 / BPM
BAR = 4 * BEAT
rng = np.random.default_rng(7)

HERE = Path(__file__).resolve().parent.parent
CFG = sys.argv[1] if len(sys.argv) > 1 else "src/music_sections.json"
OUTNAME = sys.argv[2] if len(sys.argv) > 2 else "music.wav"
cfg = json.loads((HERE / CFG).read_text())
TOTAL = cfg["total_seconds"]
N = int(SR * (TOTAL + 3))
t_all = np.arange(N) / SR


def lp(x, f, order=2):
    return sosfilt(butter(order, f, "low", fs=SR, output="sos"), x)


def hp(x, f, order=2):
    return sosfilt(butter(order, f, "high", fs=SR, output="sos"), x)


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], "band", fs=SR, output="sos"), x)


def place(buf, sig, t, gain=1.0):
    i = int(t * SR)
    if i >= len(buf):
        return
    j = min(len(buf), i + len(sig))
    buf[i:j] += sig[: j - i] * gain


def env(n, a, d):
    """attack seconds, exponential decay time-constant seconds"""
    tt = np.arange(n) / SR
    e = np.exp(-tt / d)
    ai = int(a * SR)
    if ai > 0:
        e[:ai] *= np.linspace(0, 1, ai)
    return e


def kick():
    n = int(0.5 * SR)
    tt = np.arange(n) / SR
    f = 45 + 85 * np.exp(-tt / 0.035)
    ph = 2 * np.pi * np.cumsum(f) / SR
    s = np.sin(ph) * env(n, 0.002, 0.16)
    click = hp(rng.standard_normal(n), 2000) * env(n, 0, 0.004) * 0.25
    return np.tanh(1.6 * (s + click))


def clap():
    n = int(0.35 * SR)
    noise = bp(rng.standard_normal(n), 900, 4000)
    e = np.zeros(n)
    for k, off in enumerate([0, 0.011, 0.022]):
        e += env(n, 0, 0.012 if k < 2 else 0.11) * (np.arange(n) >= off * SR)
    return noise * e * 0.6


def hat(open_=False):
    n = int((0.25 if open_ else 0.06) * SR)
    s = hp(rng.standard_normal(n), 7000)
    return s * env(n, 0, 0.08 if open_ else 0.014) * 0.35


def saw(freq, n, detune=0.0):
    tt = np.arange(n) / SR
    f = freq * (1 + detune)
    return 2 * ((tt * f) % 1.0) - 1


def note_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


# A minor progression, one chord per bar: Am F C G (MIDI roots)
PROG = [(57, [57, 60, 64]), (53, [53, 57, 60]), (48, [55, 60, 64]), (55, [55, 59, 62])]


def pad_bar(chord, bar_len, cutoff):
    n = int(bar_len * SR)
    s = np.zeros(n)
    for m in chord:
        for dt in (-0.006, 0.0, 0.007):
            s += saw(note_hz(m + 12), n, dt)
    s = lp(s, cutoff, 2) / 9
    e = np.minimum(1, np.arange(n) / (0.25 * SR)) * np.minimum(1, (n - np.arange(n)) / (0.25 * SR))
    return s * e


def bass_note(m, dur, cutoff=420):
    n = int(dur * SR)
    s = saw(note_hz(m - 12), n) * 0.7 + np.sin(2 * np.pi * note_hz(m - 24) * np.arange(n) / SR)
    return lp(s, cutoff, 2) * env(n, 0.004, dur * 0.9) * 0.5


def riser(dur):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    noise = rng.standard_normal(n)
    out = np.zeros(n)
    # sweep a band-pass by blocks
    blocks = 40
    bl = n // blocks
    for b in range(blocks):
        f = 300 * (40 ** (b / blocks))
        seg = bp(noise[b * bl:(b + 1) * bl + 512], f * 0.8, min(f * 1.25, SR / 2 - 100))[:bl]
        out[b * bl:b * bl + len(seg)] = seg
    return out * (tt / dur) ** 2 * 0.35


def impact():
    n = int(2.5 * SR)
    tt = np.arange(n) / SR
    boom = np.sin(2 * np.pi * (38 + 40 * np.exp(-tt / 0.08)) * tt) * env(n, 0.001, 0.6)
    air = lp(rng.standard_normal(n), 2500) * env(n, 0.001, 0.4) * 0.25
    return np.tanh(1.3 * (boom + air)) * 0.9


def whoosh(dur=0.5):
    n = int(dur * SR)
    tt = np.arange(n) / SR
    w = np.sin(np.pi * tt / dur) ** 2
    return bp(rng.standard_normal(n), 600, 6000) * w * 0.22


def tick():
    n = int(0.03 * SR)
    return np.sin(2 * np.pi * 2400 * np.arange(n) / SR) * env(n, 0, 0.006) * 0.25


drums = np.zeros(N)
bassb = np.zeros(N)
padb = np.zeros(N)
fx = np.zeros(N)
K, C, H, HO = kick(), clap(), hat(), hat(True)

for sec in cfg["sections"]:
    start, end, mode = sec["start"], sec["end"], sec["mode"]
    nbars = int(round((end - start) / BAR))
    for b in range(nbars):
        t0 = start + b * BAR
        root, chord = PROG[b % 4] if mode != "intro" else PROG[0 if b % 2 == 0 else 1]
        cutoff = {"intro": 900, "light": 1400, "full": 2600, "break": 1100, "outro": 1200}[mode]
        place(padb, pad_bar(chord, BAR, cutoff), t0, 0.55 if mode in ("intro", "break", "outro") else 0.35)
        for q in range(4):
            tb = t0 + q * BEAT
            if mode == "full":
                place(drums, K, tb, 0.9)
                if q in (1, 3):
                    place(drums, C, tb, 0.55)
                for e8 in range(4):
                    place(drums, H, tb + e8 * BEAT / 4, 0.5 if e8 % 2 else 0.25)
                place(drums, HO, tb + BEAT / 2, 0.35)
                place(bassb, bass_note(root, BEAT / 2 * 0.95), tb + BEAT / 2, 0.9)
                place(bassb, bass_note(root, BEAT / 2 * 0.9), tb, 0.55)
            elif mode == "light":
                if q in (0, 2):
                    place(drums, K, tb, 0.7)
                place(drums, H, tb + BEAT / 2, 0.3)
                if q == 0:
                    place(bassb, bass_note(root, BAR * 0.9, 260), tb, 0.6)
            elif mode == "break":
                if q == 0:
                    place(drums, K, tb, 0.55)
                    place(bassb, bass_note(root, BAR * 0.95, 200), tb, 0.6)
                if q == 2:
                    place(drums, C, tb, 0.25)
            elif mode == "outro":
                if b == 0 and q == 0:
                    place(bassb, bass_note(root, BAR * 2, 200), tb, 0.6)

for t in cfg.get("impacts", []):
    place(fx, impact(), t, 0.8)
for t in cfg.get("risers", []):  # riser ENDS at t
    d = 1.9
    place(fx, riser(d), max(0, t - d), 1.0)
for t in cfg.get("whooshes", []):
    place(fx, whoosh(), max(0, t - 0.25), 1.0)
for t in cfg.get("ticks", []):
    place(fx, tick(), t, 1.0)

# sidechain-ish duck of pad and bass on kicks in full sections
duck = np.ones(N)
for sec in cfg["sections"]:
    if sec["mode"] == "full":
        nb = int(round((sec["end"] - sec["start"]) / BEAT))
        for k in range(nb):
            i = int((sec["start"] + k * BEAT) * SR)
            L = int(0.22 * SR)
            if i + L < N:
                duck[i:i + L] = np.minimum(duck[i:i + L], 0.45 + 0.55 * (np.arange(L) / L) ** 0.6)

mix = drums * 0.8 + (bassb * 0.8 + padb * 0.9) * duck + fx
# gentle stereo: pad widened by a short delay on R
L = mix.copy()
R = mix.copy()
dly = int(0.012 * SR)
R[dly:] = (mix - padb * duck * 0.9)[dly:] * 1.0 + (padb * duck * 0.9)[:-dly]
# fade the tail
fade_from = int((TOTAL - 0.4) * SR)
f = np.ones(N)
f[fade_from:] = np.linspace(1, 0, N - fade_from) ** 2
st = np.stack([L * f, R * f], axis=1)[: int(TOTAL * SR)]
st = np.tanh(st * 1.2)
st /= np.max(np.abs(st)) / 0.89
out = HERE / "public" / OUTNAME
import wave

with wave.open(str(out), "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes((st * 32767).astype("<i2").tobytes())
print("wrote", out, TOTAL, "s")
