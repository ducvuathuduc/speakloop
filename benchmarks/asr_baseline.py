"""Baseline: what an ordinary (autocorrecting) ASR can tell a learner.

Stage A (model, run once, resumable):
    python benchmarks/asr_baseline.py transcribe --model openai/whisper-small --speakers THV,TLV

Writes <CACHE>/<model-slug>/l2arctic/<key>.txt.

Stage B (no model) is ``baseline_predictions()``, used by eval_l2arctic.py:
the ASR transcript is diffed against the reference words; a reference word the
ASR dropped flags all of its phones as deleted, a word it replaced flags the
phones that differ between the reference pronunciation and the espeak-ng
pronunciation of the replacement word (Levenshtein alignment). A word the ASR
"heard" correctly flags nothing. This is how a transcript-diff pronunciation
checker works: it can only see errors that change the recognised word, and a
strong language model autocorrects most accented phones back to the intended
word.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import CACHE, load_l2arctic  # noqa: E402

_ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen".split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
_ORD = {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth",
        "nine": "ninth", "twelve": "twelfth"}


def _num_words(n: int) -> list[str]:
    if n < 20:
        return [_ONES[n]]
    if n < 100:
        return [_TENS[n // 10]] + ([_ONES[n % 10]] if n % 10 else [])
    if n < 1000:
        return [_ONES[n // 100], "hundred"] + (_num_words(n % 100) if n % 100 else [])
    if 1100 <= n < 2000 and n % 100:          # years: 1908 -> nineteen eight
        return _num_words(n // 100) + _num_words(n % 100)
    return _num_words(n // 1000) + ["thousand"] + (_num_words(n % 1000) if n % 1000 else [])


def _ordinal(words: list[str]) -> list[str]:
    last = words[-1]
    if last in _ORD:
        last = _ORD[last]
    elif last.endswith("y"):
        last = last[:-1] + "ieth"
    else:
        last = last + "th"
    return words[:-1] + [last]


def norm_words(text: str) -> list[str]:
    """Lowercase words with digits spelled out ("20th" -> "twentieth"), punctuation dropped."""
    text = text.lower().replace("’", "'").replace(",", "")
    text = re.sub(r"[^a-z0-9' ]+", " ", text.replace("-", " "))
    out: list[str] = []
    for w in text.split():
        if not w.strip("'"):
            continue
        m = re.fullmatch(r"(\d+)(st|nd|rd|th)?", w)
        if m and len(m.group(1)) <= 4:
            ws = _num_words(int(m.group(1)))
            out += _ordinal(ws) if m.group(2) else ws
        else:
            out.append(w)
    return out


def align_words(ref: list[str], hyp: list[str]) -> list[tuple[str, int | None, int | None]]:
    """Levenshtein alignment -> list of (op, ref_idx, hyp_idx), op in ok|sub|del|ins."""
    n, m = len(ref), len(hyp)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1,
                          d[i - 1][j - 1] + (0 if ref[i - 1] == hyp[j - 1] else 1))
    ops = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0 and d[i][j] == d[i - 1][j - 1] + (0 if ref[i - 1] == hyp[j - 1] else 1):
            ops.append(("ok" if ref[i - 1] == hyp[j - 1] else "sub", i - 1, j - 1))
            i, j = i - 1, j - 1
        elif i > 0 and d[i][j] == d[i - 1][j] + 1:
            ops.append(("del", i - 1, None))
            i -= 1
        else:
            ops.append(("ins", None, j - 1))
            j -= 1
    return ops[::-1]


def align_phones(ref: list[str], hyp: list[str], same) -> list[bool]:
    """Per reference phone: True if it is matched by an equivalent hyp phone."""
    n, m = len(ref), len(hyp)
    d = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1,
                          d[i - 1][j - 1] + (0 if same(ref[i - 1], hyp[j - 1]) else 1))
    ok = [False] * n
    i, j = n, m
    while i > 0 and j > 0:
        c = 0 if same(ref[i - 1], hyp[j - 1]) else 1
        if d[i][j] == d[i - 1][j - 1] + c:
            ok[i - 1] = c == 0
            i, j = i - 1, j - 1
        elif d[i][j] == d[i - 1][j] + 1:
            i -= 1
        else:
            j -= 1
    return ok


def transcribe(model: str, speakers: list[str], per_speaker: int | None) -> None:
    import os

    import torch
    from transformers import pipeline

    from speakloop.phoneme.model import load_audio

    torch.set_num_threads(int(os.environ.get("SPEAKLOOP_PHONEME_THREADS", "2")))
    asr = pipeline("automatic-speech-recognition", model=model, device="cpu", dtype=torch.float32)
    out = CACHE / model.split("/")[-1] / "l2arctic"
    out.mkdir(parents=True, exist_ok=True)
    seen: dict[str, int] = {}
    done = 0
    for u in load_l2arctic(speakers):
        seen[u.speaker] = seen.get(u.speaker, 0) + 1
        if per_speaker and seen[u.speaker] > per_speaker:
            continue
        f = out / f"{u.key}.txt"
        if f.exists():
            continue
        wav = load_audio(u.wav)
        t = time.perf_counter()
        r = asr({"raw": wav, "sampling_rate": 16000},
                generate_kwargs={"language": "en", "task": "transcribe"})
        f.write_text(r["text"].strip())
        done += 1
        if done % 25 == 0:
            print(f"{done} done, last {time.perf_counter()-t:.1f}s: {r['text'][:60]}", flush=True)
    print("finished", done, flush=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["transcribe"])
    ap.add_argument("--model", default="openai/whisper-small")
    ap.add_argument("--speakers", default="THV,TLV")
    ap.add_argument("--per-speaker", type=int, default=None)
    a = ap.parse_args()
    transcribe(a.model, a.speakers.split(","), a.per_speaker)


if __name__ == "__main__":
    main()
