"""Stage 2: phone-level mispronunciation detection on L2-ARCTIC (Vietnamese L1).

    python benchmarks/eval_l2arctic.py score      # GOP for every annotated phone (needs cached emissions)
    python benchmarks/eval_l2arctic.py report     # tune threshold on dev, report test, write JSON + chart

Ground truth: the L2-ARCTIC manual phone annotation. Each canonical phone the
annotators kept is "correct", a substitution, or a deletion; a phone is a
positive (mispronounced) if it is not correct. Additions are not scored (they
have no canonical phone).

SpeakLoop: score_phones() on the canonical (annotation) phone sequence; phone
flagged if GOP < threshold. The threshold is picked to maximise F1 on dev
speakers (HQTV, PNV) and then applied unchanged to the held-out test speakers
(THV, TLV).

Baseline: Whisper transcript diff projected to phones (see asr_baseline.py).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from asr_baseline import align_phones, align_words, norm_words  # noqa: E402
from common import CACHE, DEV_SPEAKERS, TEST_SPEAKERS, load_l2arctic  # noqa: E402
from speakloop.phoneme.g2p import (ACCEPTED_VARIANTS, WordPron, arpa_to_ipa, g2p_words,  # noqa: E402
                                   weak_form_variants)
from speakloop.phoneme.gop import score_phones  # noqa: E402

MODEL_SLUG = os.environ.get("SPEAKLOOP_BENCH_MODEL_SLUG", "lv60-bf16")
ASR_SLUG = os.environ.get("SPEAKLOOP_BENCH_ASR_SLUG", "whisper-small")
OUT = Path(__file__).resolve().parent
SCORES = CACHE / "l2arctic_phone_scores.jsonl"


def _vocab() -> dict[str, int]:
    p = os.environ.get("SPEAKLOOP_PHONEME_MODEL")
    if p and (Path(p) / "vocab.json").exists():
        return json.loads((Path(p) / "vocab.json").read_text())
    from speakloop.phoneme.model import _load_vocab
    return _load_vocab(p or "facebook/wav2vec2-lv-60-espeak-cv-ft")


def _base(arpa: str) -> str:
    return "".join(c for c in arpa if not c.isdigit())


def _same(a: str, b: str) -> bool:
    return a == b or b in ACCEPTED_VARIANTS.get(a, ()) or a in ACCEPTED_VARIANTS.get(b, ())


def score(speakers: list[str]) -> None:
    vocab = _vocab()
    vset = set(vocab)
    em_dir = CACHE / MODEL_SLUG / "l2arctic"
    asr_dir = CACHE / ASR_SLUG / "l2arctic"
    n_utt = 0
    with SCORES.open("w") as fh:
        for u in load_l2arctic(speakers):
            npy = em_dir / f"{u.key}.npy"
            if not npy.exists():
                continue
            lp = np.load(npy).astype(np.float32)
            prons, meta = [], []
            for wi, w in enumerate(u.words):
                ph = []
                for k, p in enumerate(w.phones):
                    try:
                        ipa = arpa_to_ipa(p.canonical)
                    except KeyError:
                        continue
                    ph.append(ipa)
                    meta.append((wi, k, len(w.phones), p))
                prons.append(WordPron(w.text, ph, []))
            flat = [p for wp in prons for p in wp.phones]
            r_orig = score_phones(lp, flat, vocab, threshold=1e9, test_insertions=False, context_pass=False)
            r_plain = score_phones(lp, flat, vocab, threshold=1e9, test_insertions=False)
            r_weak = score_phones(lp, flat, vocab, threshold=1e9, test_insertions=False,
                                  extra_variants=weak_form_variants(prons))
            base_flag = [None] * len(flat)
            for i, (wi, k, nw, p) in enumerate(meta):
                a, b, o = r_plain.phones[i], r_weak.phones[i], r_orig.phones[i]
                fh.write(json.dumps({
                    "spk": u.speaker, "utt": u.utt_id, "word": u.words[wi].text, "wi": wi,
                    "k": k, "final": k == nw - 1, "canon": _base(p.canonical), "ipa": flat[i],
                    "kind": p.kind, "perceived": p.perceived,
                    "gop_orig": o.gop, "gop": a.gop, "heard": a.heard, "del": a.best_alt_is_deletion,
                    "gop_weak": b.gop, "heard_weak": b.heard, "del_weak": b.best_alt_is_deletion,
                    "base": base_flag[i],
                }) + "\n")
            n_utt += 1
    print("scored", n_utt, "utterances ->", SCORES)


def _baseline_flags(u, prons, vset, asr_dir) -> list | None:
    flat = [p for wp in prons for p in wp.phones]
    txt = asr_dir / f"{u.key}.txt"
    if not txt.exists():
        return None
    ref_tok = [(norm_words(wp.text) or [""])[0] for wp in prons]
    hyp = norm_words(txt.read_text())
    offs, o = [], 0
    for wp in prons:
        offs.append(o)
        o += len(wp.phones)
    flags = [False] * len(flat)
    for op, ri, hi in align_words(ref_tok, hyp):
        if ri is None or op == "ok":
            continue
        ref_ph = prons[ri].phones
        if op == "del":
            ok = [False] * len(ref_ph)
        else:
            hp = g2p_words(hyp[hi], vset)
            ok = align_phones(ref_ph, hp[0].phones if hp else [], _same)
        for k, good in enumerate(ok):
            flags[offs[ri] + k] = not good
    return flags


def _prons(u):
    prons, meta = [], []
    for wi, w in enumerate(u.words):
        ph = []
        for k, p in enumerate(w.phones):
            try:
                ipa = arpa_to_ipa(p.canonical)
            except KeyError:
                continue
            ph.append(ipa)
            meta.append((wi, k, len(w.phones), p))
        prons.append(WordPron(w.text, ph, []))
    return prons, meta


def baseline() -> None:
    """Add/refresh the transcript-diff baseline flag ("base") on every scored phone."""
    vset = set(_vocab())
    asr_dir = CACHE / ASR_SLUG / "l2arctic"
    rows = [json.loads(l) for l in SCORES.read_text().splitlines()]
    by_utt = defaultdict(list)
    for r in rows:
        by_utt[(r["spk"], r["utt"])].append(r)
    n = 0
    for u in load_l2arctic(sorted({r["spk"] for r in rows})):
        rs = by_utt.get((u.speaker, u.utt_id))
        if not rs:
            continue
        prons, meta = _prons(u)
        flags = _baseline_flags(u, prons, vset, asr_dir)
        assert len(meta) == len(rs)
        for r, f in zip(rs, flags or [None] * len(rs)):
            r["base"] = f
        n += flags is not None
    SCORES.write_text("".join(json.dumps(r) + "\n" for r in rows))
    print("baseline flags for", n, "utterances")


# ---------------------------------------------------------------- report

CATEGORIES = [
    # name, phone-group filter, specific-error filter
    ("DH→D", lambda r: r["canon"] == "DH", lambda r: r["kind"] == "substitution" and r["perceived"] == "D"),
    ("final T/D deleted", lambda r: r["canon"] in ("T", "D") and r["final"],
     lambda r: r["kind"] == "deletion"),
    ("final Z/S deleted", lambda r: r["canon"] in ("Z", "S") and r["final"],
     lambda r: r["kind"] == "deletion"),
    ("Z→S", lambda r: r["canon"] == "Z", lambda r: r["kind"] == "substitution" and r["perceived"] == "S"),
    ("ER→AH", lambda r: r["canon"] == "ER", lambda r: r["kind"] == "substitution" and r["perceived"] == "AH"),
    ("IH→IY", lambda r: r["canon"] == "IH", lambda r: r["kind"] == "substitution" and r["perceived"] == "IY"),
    ("R deleted", lambda r: r["canon"] == "R", lambda r: r["kind"] == "deletion"),
    ("L deleted / L→W", lambda r: r["canon"] == "L", lambda r: r["kind"] != "correct"),
]
MAX_FA = 0.15
MAIN = "SpeakLoop default (0.0 + per-phone, FA<=15% on dev)"
FUNCTION_WORDS = {"to", "the", "a", "an", "of", "and", "for"}


def prf(y: np.ndarray, p: np.ndarray) -> dict:
    tp = int((y & p).sum()); fp = int((~y & p).sum()); fn = int((y & ~p).sum())
    P = tp / (tp + fp) if tp + fp else 0.0
    R = tp / (tp + fn) if tp + fn else 0.0
    F = 2 * P * R / (P + R) if P + R else 0.0
    return {"precision": round(P, 3), "recall": round(R, 3), "f1": round(F, 3),
            "tp": tp, "fp": fp, "fn": fn, "n": int(len(y)), "positives": int(y.sum())}


def tune(rows: list[dict], key: str) -> tuple[float, dict]:
    y = np.array([r["kind"] != "correct" for r in rows])
    g = np.array([r[key] if r[key] is not None else 50.0 for r in rows])
    best = (-1.0, 0.0, None)
    for th in np.arange(-10, 10.01, 0.25):
        m = prf(y, g < th)
        if m["f1"] > best[0]:
            best = (m["f1"], float(th), m)
    return best[1], best[2]


def tune_per_phone(rows: list[dict], key: str, global_th: float, min_pos: int = 15,
                   max_fa: float | None = None) -> dict[str, float]:
    """Coordinate ascent on dev F1: one threshold per canonical phone that has
    >= min_pos dev errors; every other phone keeps the global threshold.

    ``max_fa`` caps the false-alarm rate on that phone's *correct* dev tokens.
    Without it, phones that Vietnamese speakers get wrong most of the time
    (ð 73%, ɚ 66% on dev) are tuned to "always flag", which scores well on F1
    but tells a speaker who says the phone right that it is wrong."""
    y = np.array([r["kind"] != "correct" for r in rows])
    g = np.array([r[key] if r[key] is not None else 50.0 for r in rows])
    ph = np.array([r["canon"] for r in rows])
    th = {p: global_th for p in set(ph)}
    cur = np.array([th[p] for p in ph])
    for p in sorted(set(ph)):
        m = ph == p
        if (y & m).sum() < min_pos:
            continue
        best = (prf(y, g < cur)["f1"], th[p])
        okm = m & ~y
        for t in np.arange(-6, 8.01, 0.25):
            if max_fa is not None and okm.any() and (g[okm] < t).mean() > max_fa:
                continue
            c = cur.copy(); c[m] = t
            f = prf(y, g < c)["f1"]
            if f > best[0] + 1e-9:
                best = (f, float(t))
        th[p] = best[1]; cur[m] = best[1]
    return {p: t for p, t in th.items() if t != global_th}


def tune_precision(rows: list[dict], key: str, target: float = 0.70) -> tuple[float, dict]:
    """Largest threshold whose dev precision is >= target (learner-facing operating point)."""
    y = np.array([r["kind"] != "correct" for r in rows])
    g = np.array([r[key] if r[key] is not None else 50.0 for r in rows])
    best = (-10.0, prf(y, g < -10.0))
    for th in np.arange(-10, 10.01, 0.25):
        m = prf(y, g < th)
        if m["precision"] >= target and m["tp"] > 0:
            best = (float(th), m)
    return best


def pr_curve(rows: list[dict], key: str) -> tuple[list[float], list[float], float]:
    y = np.array([r["kind"] != "correct" for r in rows])
    g = np.array([r[key] if r[key] is not None else 50.0 for r in rows])
    order = np.argsort(g)
    ys = y[order]
    tp = np.cumsum(ys); fp = np.cumsum(~ys)
    prec = tp / (tp + fp); rec = tp / y.sum()
    # average precision (step interpolation)
    ap = float(np.sum(np.diff(np.concatenate([[0], rec])) * prec))
    return rec.tolist(), prec.tolist(), ap


def report() -> None:
    rows = [json.loads(l) for l in SCORES.read_text().splitlines()]
    dev = [r for r in rows if r["spk"] in DEV_SPEAKERS]
    test = [r for r in rows if r["spk"] in TEST_SPEAKERS]
    res: dict = {"n_dev_phones": len(dev), "n_test_phones": len(test),
                 "dev_utts": len({(r["spk"], r["utt"]) for r in dev}),
                 "test_utts": len({(r["spk"], r["utt"]) for r in test}),
                 "systems": {}}
    y = np.array([r["kind"] != "correct" for r in test])
    preds = {}
    for name, key in [("GOP, single pass (ac378c6)", "gop_orig"), ("GOP + context pass", "gop"),
                      ("SpeakLoop (context pass + weak forms)", "gop_weak")]:
        th, dm = tune(dev, key)
        g = np.array([r[key] if r[key] is not None else 50.0 for r in test])
        p = g < th
        preds[name] = p
        rec, prec, ap = pr_curve(test, key)
        thp, dmp = tune_precision(dev, key)
        gp = g < thp
        res["systems"][name] = {"threshold": th, "dev": dm, "test": prf(y, p), "test_ap": round(ap, 3),
                                "high_precision": {"threshold": thp, "dev": dmp, "test": prf(y, gp)},
                                "_curve": (rec, prec, th, key)}
    # per-phone thresholds: tuned on dev (coordinate ascent on dev F1), applied to test.
    # (a) around the dev-F1 global threshold; (b) around the product's pre-existing
    # global default 0.0 (fixed in ac378c6, before this benchmark) -> shipped default.
    key = "gop_weak"
    g = np.array([r[key] for r in test])
    dg = np.array([r[key] for r in dev])
    dy = np.array([r["kind"] != "correct" for r in dev])
    for name, base, cap in [("+ per-phone thr., unconstrained (around dev-F1 global)",
                             res["systems"]["SpeakLoop (context pass + weak forms)"]["threshold"], None),
                            ("0.0 + per-phone thr., unconstrained (L1 prior)", 0.0, None),
                            (MAIN, 0.0, MAX_FA)]:
        pth = tune_per_phone(dev, key, base, max_fa=cap)
        cut = np.array([pth.get(r["canon"], base) for r in test])
        dcut = np.array([pth.get(r["canon"], base) for r in dev])
        preds[name] = g < cut
        res["systems"][name] = {"threshold": {"global": base, **{str(k): v for k, v in pth.items()}},
                                "dev": prf(dy, dg < dcut), "test": prf(y, g < cut)}
        res["systems"][name]["test_false_alarm_on_correct_by_phone"] = {
            str(ph): round(float((g[np.array([r["canon"] == ph and r["kind"] == "correct" for r in test])] <
                                 pth[ph]).mean()), 3) for ph in pth}
    res["systems"]["SpeakLoop weak forms, global 0.0 only"] = {"threshold": 0.0, "test": prf(y, g < 0.0)}
    preds["SpeakLoop weak forms, global 0.0 only"] = g < 0.0

    tb = [r for r in test if r.get("base") is not None]
    if not tb:
        print("no baseline transcripts yet; run asr_baseline.py transcribe + eval_l2arctic.py baseline")
        return
    # Head-to-head on the utterances that have a baseline transcript (same phones for all systems).
    sub_keys = {(r["spk"], r["utt"]) for r in tb}
    sub_mask = np.array([(r["spk"], r["utt"]) in sub_keys for r in test])
    yb = y[sub_mask]
    res["subset_utts"] = len(sub_keys)
    res["subset_phones"] = int(sub_mask.sum())
    for name in list(preds):
        res["systems"][name]["test_subset"] = prf(yb, preds[name][sub_mask])
    pb = np.array([bool(r["base"]) for r in tb])
    res["systems"]["Whisper-small transcript diff"] = {"threshold": None, "test_subset": prf(yb, pb)}
    preds["Whisper-small transcript diff"] = np.array([bool(r["base"]) if r.get("base") is not None else False for r in test])
    full_test, test, y = test, tb, yb
    sub_rows = tb
    preds = {k: v[sub_mask] for k, v in preds.items()}

    # per kind + per category
    cat: dict = {}
    kinds = {"all deletions": lambda r: r["kind"] == "deletion",
             "all substitutions": lambda r: r["kind"] == "substitution"}
    for name, p in preds.items():
        c = {}
        for kn, kf in kinds.items():
            idx = np.array([kf(r) for r in test])
            c[kn] = {"recall": round(float(p[idx].mean()), 3), "n": int(idx.sum())}
        for cn, gf, ef in CATEGORIES:
            gi = np.array([gf(r) for r in test])
            ei = np.array([gf(r) and ef(r) for r in test])
            m = prf(y[gi], p[gi])
            c[cn] = {"recall_specific": round(float(p[ei].mean()), 3) if ei.any() else None,
                     "n_specific": int(ei.sum()), "group_precision": m["precision"],
                     "group_recall": m["recall"], "group_f1": m["f1"], "group_n": m["n"]}
        fw = np.array([r["word"] in FUNCTION_WORDS and r["kind"] == "correct" for r in test])
        c["function-word false-positive rate"] = {"rate": round(float(p[fw].mean()), 3), "n": int(fw.sum())}
        cfw = np.array([r["kind"] == "correct" for r in test])
        c["overall false-positive rate"] = {"rate": round(float(p[cfw].mean()), 3), "n": int(cfw.sum())}
        cat[name] = c
    res["categories"] = cat

    # diagnosis: of detected errors, did we say the right thing?
    key = "gop_weak"
    ths = res["systems"][MAIN]["threshold"]
    test = full_test

    def flagged(r):
        return r[key] < ths.get(r["canon"], ths["global"])
    det_sub = [r for r in test if r["kind"] == "substitution" and flagged(r) and r["perceived"]]
    det_del = [r for r in test if r["kind"] == "deletion" and flagged(r)]

    def ipa_of(a):
        try:
            return arpa_to_ipa(a)
        except KeyError:
            return None
    sub_ok = sum(1 for r in det_sub if not r["del_weak"] and r["heard_weak"] is not None and _same(ipa_of(r["perceived"]) or "?", r["heard_weak"]))
    del_ok = sum(1 for r in det_del if r["del_weak"])
    res["diagnosis"] = {"substitution_heard_correct": round(sub_ok / len(det_sub), 3) if det_sub else None,
                        "n_detected_substitutions": len(det_sub),
                        "deletion_called_deletion": round(del_ok / len(det_del), 3) if det_del else None,
                        "n_detected_deletions": len(det_del)}

    curves = {k: v.pop("_curve") for k, v in res["systems"].items() if "_curve" in v}
    (OUT / "results_l2arctic.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
    print(json.dumps(res, indent=2, ensure_ascii=False))
    chart(res, curves, sub_rows)


def chart(res: dict, curves: dict, test: list[dict]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 5.2), gridspec_kw={"width_ratios": [1, 1.5]})
    colors = {"GOP, single pass (ac378c6)": "#d1d5db", "GOP + context pass": "#9aa5b1", "SpeakLoop (context pass + weak forms)": "#2563eb",
              "Whisper-small transcript diff": "#ea580c"}
    for name, (_r, _p, th, key) in curves.items():
        rec, prec, ap = pr_curve(test, key)
        a1.plot(rec, prec, color=colors[name], lw=2.2 if "weak" in name else 1.2,
                label=f"{name} (AP {ap:.2f})")
        t = res["systems"][name]["test_subset"]
        a1.scatter([t["recall"]], [t["precision"]], color=colors[name], zorder=5, s=40)
    m = res["systems"][MAIN]["test_subset"]
    a1.scatter([m["recall"]], [m["precision"]], color="#1d4ed8", marker="*", s=180, zorder=7,
               label=f"SpeakLoop default: 0.0 + per-phone thr. (F1 {m['f1']:.2f})")
    b = res["systems"]["Whisper-small transcript diff"]["test_subset"]
    a1.scatter([b["recall"]], [b["precision"]], color=colors["Whisper-small transcript diff"], marker="D", s=70,
               zorder=6, label=f"Whisper-small transcript diff (F1 {b['f1']:.2f})")
    a1.set_xlim(0, 1); a1.set_ylim(0, 1)
    a1.set_xlabel("Recall (mispronounced phones found)"); a1.set_ylabel("Precision")
    nutt = len({(r["spk"], r["utt"]) for r in test})
    a1.set_title(f"Held-out test speakers THV + TLV ({nutt} utts, {len(test)} phones)\n"
                 "dots = operating point, threshold tuned on dev HQTV + PNV", fontsize=10)
    a1.legend(fontsize=8, loc="upper right"); a1.grid(alpha=.3)

    names = ["all deletions", "all substitutions"] + [c[0] for c in CATEGORIES]
    sl = res["categories"][MAIN]
    wb = res["categories"]["Whisper-small transcript diff"]

    def val(c, n):
        v = c[n]
        return v.get("recall") if "recall" in v else v.get("recall_specific") or 0.0
    x = np.arange(len(names)); w = 0.38
    b1 = a2.bar(x - w / 2, [val(sl, n) for n in names], w, color="#2563eb", label="SpeakLoop default")
    b2 = a2.bar(x + w / 2, [val(wb, n) for n in names], w, color=colors["Whisper-small transcript diff"], label="Whisper-small diff")
    for bars in (b1, b2):
        a2.bar_label(bars, fmt="%.2f", fontsize=6.5, padding=1)
    a2.set_xticks(x)
    lab = []
    for n in names:
        v = sl[n]
        lab.append(f"{n}\n(n={v.get('n', v.get('n_specific'))})")
    a2.set_xticklabels(lab, rotation=40, ha="right", fontsize=8)
    a2.set_ylim(0, 1.08); a2.set_ylabel("Recall of annotated errors")
    a2.set_title(f"Which Vietnamese-L1 errors each system catches (same {nutt} test utts)", fontsize=10)
    a2.legend(fontsize=8); a2.grid(axis="y", alpha=.3)
    fig.suptitle("SpeakLoop phoneme scorer vs. transcript-diff baseline — L2-ARCTIC Vietnamese speakers", fontsize=12)
    fig.tight_layout()
    fig.savefig(OUT / "l2arctic_results.png", dpi=130)
    print("chart ->", OUT / "l2arctic_results.png")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["score", "baseline", "report"])
    ap.add_argument("--speakers", default="HQTV,PNV,THV,TLV")
    a = ap.parse_args()
    if a.cmd == "score":
        score(a.speakers.split(","))
    elif a.cmd == "baseline":
        baseline()
    else:
        report()


if __name__ == "__main__":
    main()
