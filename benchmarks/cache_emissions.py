"""Stage 1: run the phoneme model once per utterance and cache log-posteriors.

    python benchmarks/cache_emissions.py l2arctic
    python benchmarks/cache_emissions.py speechocean [--limit N]

Writes <CACHE>/<model-slug>/<dataset>/<key>.npy (float16 log-probs, T x V) and
<key>.json with timing. Resumable: existing files are skipped.
"""

from __future__ import annotations

import argparse
import io
import json
import resource
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import CACHE, load_l2arctic  # noqa: E402
from speakloop.phoneme.model import get_model, load_audio  # noqa: E402


def slug(name: str) -> str:
    return name.split("/")[-1]


def iter_speechocean(limit: int | None):
    import pyarrow.parquet as pq
    from huggingface_hub import snapshot_download

    root = Path(snapshot_download("mispeech/speechocean762", repo_type="dataset"))
    files = sorted(root.glob("**/test*.parquet"))
    n = 0
    for f in files:
        pf = pq.ParquetFile(f)
        for batch in pf.iter_batches(batch_size=32):
            for row in batch.to_pylist():
                a = row["audio"]
                key = Path(a.get("path") or f"so_{n}").stem
                yield key, a["bytes"]
                n += 1
                if limit and n >= limit:
                    return


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset", choices=["l2arctic", "speechocean"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--dtype", default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--speakers", default=None, help="comma list, e.g. THV,TLV (l2arctic)")
    ap.add_argument("--per-speaker", type=int, default=None, help="first N utts per speaker (l2arctic)")
    a = ap.parse_args()
    m = get_model(a.model, a.dtype)
    out = CACHE / slug(m.name) / a.dataset
    out.mkdir(parents=True, exist_ok=True)
    if a.dataset == "l2arctic":
        spk = a.speakers.split(",") if a.speakers else None
        utts = load_l2arctic(spk)
        if a.per_speaker:
            seen: dict[str, int] = {}
            sel = []
            for u in utts:
                seen[u.speaker] = seen.get(u.speaker, 0) + 1
                if seen[u.speaker] <= a.per_speaker:
                    sel.append(u)
            utts = sel
        items = ((u.key, u.wav) for u in utts)
    else:
        items = iter_speechocean(a.limit)
    done = 0
    for key, src in items:
        npy = out / f"{key}.npy"
        if npy.exists():
            continue
        wav = load_audio(src if isinstance(src, (bytes, bytearray)) else Path(src))
        t = time.perf_counter()
        em = m.emissions(wav)
        dt = time.perf_counter() - t
        np.save(npy, em.log_probs.astype(np.float16))
        (out / f"{key}.json").write_text(json.dumps({"audio_s": len(wav) / 16000, "acoustic_s": dt}))
        done += 1
        if done % 25 == 0:
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
            print(f"{done} done, last {len(wav)/16000:.1f}s audio in {dt:.2f}s, maxrss {rss:.0f} MB", flush=True)
    print("finished", done, flush=True)


if __name__ == "__main__":
    main()
