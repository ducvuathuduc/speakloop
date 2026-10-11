"""Smoke run + latency/RSS measurement for ``speakloop.phoneme.assess``.

Runs a handful of clips (never the full dataset): a few L2-ARCTIC Vietnamese
utterances plus the espeak fixture. One model, loaded once.

    SPEAKLOOP_BENCH_DATA=/path/to/l2arctic python -m benchmarks.latency \
        --clips HQTV/arctic_a0003 HQTV/arctic_a0005 HQTV/arctic_a0006 --repeats 3 --out out.json
"""

from __future__ import annotations

import argparse
import json
import resource
import time
from pathlib import Path

import numpy as np

from benchmarks.common import DATA, load_l2arctic
from speakloop.phoneme import assess
from speakloop.phoneme.model import get_model

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "espeak_she_walked.wav"
FIXTURE_TEXT = "She walked to the shops."


def rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0  # Linux: KiB


def expected_errors(utt) -> list[dict]:
    out = []
    for w in utt.words:
        for p in w.phones:
            if p.kind != "correct":
                out.append({"word": w.text, "canonical": p.canonical, "perceived": p.perceived, "kind": p.kind})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clips", nargs="+", default=["HQTV/arctic_a0003", "HQTV/arctic_a0005", "HQTV/arctic_a0006"])
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--out", default="bench_cache/latency.json")
    a = ap.parse_args()

    log: dict = {"rss_mb_start": rss_mb()}
    t0 = time.perf_counter()
    m = get_model()
    log["model"] = m.name
    log["load_seconds"] = round(time.perf_counter() - t0, 1)
    log["rss_mb_after_load"] = rss_mb()
    print("loaded", m.name, log["load_seconds"], "s", log["rss_mb_after_load"], "MB", flush=True)

    jobs = []
    for c in a.clips:
        spk, uid = c.split("/")
        utt = next(u for u in load_l2arctic([spk], DATA) if u.utt_id == uid)
        jobs.append((utt.key, str(utt.wav), utt.transcript, expected_errors(utt)))
    jobs.append(("espeak_fixture", str(FIXTURE), FIXTURE_TEXT, []))

    results, lat = [], []
    for key, wav, text, exp in jobs:
        for r in range(a.repeats):
            out = assess(wav, text)
            ms = out["overall"]["latency_ms"]
            lat.append({"clip": key, "repeat": r, "audio_seconds": out["overall"]["audio_seconds"], **ms})
            print(key, r, ms, flush=True)
        results.append({
            "clip": key, "text": text, "expected_errors": exp,
            "overall": out["overall"],
            "flagged_phones": [
                {"word": out["words"][p["word_index"]]["word"], "expected": p["expected"], "heard": p["ipa"],
                 "type": p["error_type"], "score": p["score"]}
                for p in out["phones"] if p["error_type"]],
            "l1_findings": [{k: f[k] for k in ("rule_id", "word", "expected", "heard")} for f in out["l1_findings"]],
            "words": [{k: w[k] for k in ("word", "expected_ipa", "heard_ipa", "score")} for w in out["words"]],
        })
    tot = np.array([x["total"] for x in lat if x["repeat"] > 0] or [x["total"] for x in lat])
    log.update({
        "latency_runs": lat,
        "warm_total_ms_p50": float(np.percentile(tot, 50)),
        "warm_total_ms_p95": float(np.percentile(tot, 95)),
        "peak_rss_mb": rss_mb(),
        "results": results,
    })
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(log, indent=1, ensure_ascii=False))
    print("p50", log["warm_total_ms_p50"], "p95", log["warm_total_ms_p95"], "peak", log["peak_rss_mb"], flush=True)


if __name__ == "__main__":
    main()
