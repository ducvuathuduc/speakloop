"""Public API: ``assess(audio, reference_text) -> dict``.

Pipeline: audio → wav2vec2 espeak phoneme CTC posteriors → espeak-ng G2P of the
reference → CTC forced alignment (timing) → GOP per phone (score + heard phone)
→ word aggregation → Vietnamese-L1 rule pack (YAML) → findings.
"""

from __future__ import annotations

import os
import time
from typing import Any

import numpy as np

from .g2p import WordPron, g2p_words, is_vowel, weak_form_variants
from .gop import GopResult, score_phones
from .model import Emissions, get_model, load_audio
from .rules import Event, apply_rules, load_rules, phone_position

# Decision thresholds, tuned on L2-ARCTIC dev speakers HQTV + PNV only
# (see benchmarks/RESULTS.md); THV + TLV are held out.
DEFAULT_THRESHOLD = float(os.environ.get("SPEAKLOOP_GOP_THRESHOLD", "0.0"))
DEFAULT_INSERTION_GAIN = float(os.environ.get("SPEAKLOOP_INSERTION_GAIN", "3.0"))
STRESS_RATIO = 1.35

# Per-phone GOP thresholds, tuned on L2-ARCTIC dev speakers HQTV + PNV only by
# coordinate ascent on dev F1 around the global default 0.0
# (benchmarks/eval_l2arctic.py; THV + TLV held out, see benchmarks/RESULTS.md).
# The wav2vec2 espeak model has a strong prior for the dictionary phone in
# frequent words ("the" is heard as ð even when a listener hears d), so ð, d,
# z and ɚ need a stricter (higher) bar; ɪ/iː confusions were mostly false
# alarms on dev, so ɪ is almost never flagged.
PHONE_THRESHOLDS: dict[str, float] = {
    "ð": 6.25, "d": 4.25, "z": 3.5, "l": 3.0, "ɜː": 4.75, "ɚ": 4.75,
    "ɹ": 0.25, "ʌ": 0.25, "ə": 0.25, "ɪ": -5.5,
}


def _stress_events(wav: np.ndarray | None, prons: list[WordPron], gop: GopResult,
                   offsets: list[int]) -> list[Event]:
    """Experimental: flag a word whose most prominent vowel is not the dictionary-stressed one.

    Prominence = duration x RMS energy of the aligned vowel segment. Untested on
    labelled stress data; reported with ``experimental: true``.
    """
    if wav is None:
        return []
    events = []
    sr = 16000
    for wi, wp in enumerate(prons):
        vowels = [k for k, p in enumerate(wp.phones) if is_vowel(p)]
        stressed = [k for k in vowels if (wp.stress[k] if k < len(wp.stress) else None) == 1]
        if len(vowels) < 2 or len(stressed) != 1:
            continue
        prom = {}
        for k in vowels:
            ps = gop.phones[offsets[wi] + k]
            if ps.start is None or ps.end is None or ps.end <= ps.start:
                break
            seg = wav[int(ps.start * sr):int(ps.end * sr)]
            if len(seg) == 0:
                break
            prom[k] = (ps.end - ps.start) * float(np.sqrt(np.mean(seg ** 2)) + 1e-8)
        else:
            s = stressed[0]
            top = max(prom, key=prom.get)
            if top != s and prom[top] > STRESS_RATIO * prom[s]:
                ps = gop.phones[offsets[wi] + top]
                events.append(Event("stress", wp.text, wi, offsets[wi] + top, wp.phones[s],
                                    wp.phones[top], "word_medial", False, ps.start, ps.end))
    return events


def assess_emissions(
    em: Emissions,
    prons: list[WordPron],
    vocab: dict[str, int],
    *,
    wav: np.ndarray | None = None,
    threshold: float | None = None,
    insertion_gain: float | None = None,
    rules_path: str | None = None,
    check_stress: bool = True,
    weak_forms: bool = True,
) -> dict[str, Any]:
    # per-phone thresholds apply unless the caller (or env) pins one global threshold
    use_phone_thresholds = threshold is None and "SPEAKLOOP_GOP_THRESHOLD" not in os.environ
    threshold = DEFAULT_THRESHOLD if threshold is None else threshold
    insertion_gain = DEFAULT_INSERTION_GAIN if insertion_gain is None else insertion_gain

    flat: list[str] = []
    offsets: list[int] = []
    owner: list[tuple[int, int]] = []
    word_final: set[int] = set()
    for wi, wp in enumerate(prons):
        offsets.append(len(flat))
        for k, p in enumerate(wp.phones):
            owner.append((wi, k))
            flat.append(p)
        word_final.add(len(flat) - 1)

    gop = score_phones(em.log_probs, flat, vocab, word_final=word_final,
                       threshold=threshold, frame_seconds=em.frame_seconds,
                       extra_variants=weak_form_variants(prons) if weak_forms else None,
                       phone_thresholds=PHONE_THRESHOLDS if use_phone_thresholds else None)

    phones_out = []
    events: list[Event] = []
    for i, ps in enumerate(gop.phones):
        wi, k = owner[i]
        pos, cluster = phone_position(prons[wi].phones, k)
        phones_out.append({
            "ipa": ps.heard if ps.flagged else ps.expected,
            "expected": ps.expected,
            "word_index": wi,
            "start": None if ps.start is None else round(ps.start, 3),
            "end": None if ps.end is None else round(ps.end, 3),
            "score": None if ps.score is None else round(ps.score, 1),
            "gop": None if ps.gop is None else round(ps.gop, 3),
            "error_type": ps.error_type,
        })
        if ps.flagged:
            events.append(Event(ps.error_type, prons[wi].text, wi, i, ps.expected,
                                ps.heard, pos, cluster, ps.start, ps.end))

    for ins in gop.insertions:
        if ins.gain > insertion_gain:
            wi, k = owner[ins.after_index]
            events.append(Event("insertion", prons[wi].text, wi, ins.after_index, None,
                                ins.token, "word_final", False, ins.start, ins.end))
            phones_out[ins.after_index]["inserted_after"] = ins.token

    if check_stress:
        events.extend(_stress_events(wav, prons, gop, offsets))

    words_out = []
    for wi, wp in enumerate(prons):
        idx = list(range(offsets[wi], offsets[wi] + len(wp.phones)))
        scores = [phones_out[i]["score"] for i in idx if phones_out[i]["score"] is not None]
        starts = [phones_out[i]["start"] for i in idx if phones_out[i]["start"] is not None]
        ends = [phones_out[i]["end"] for i in idx if phones_out[i]["end"] is not None]
        words_out.append({
            "word": wp.text,
            "expected_ipa": "".join(wp.phones),
            "heard_ipa": "".join(phones_out[i]["ipa"] or "" for i in idx
                                 if phones_out[i]["error_type"] != "deletion"),
            "phone_indices": idx,
            "start": min(starts) if starts else None,
            "end": max(ends) if ends else None,
            "score": round(float(np.mean(scores)), 1) if scores else None,
            "errors": sum(1 for i in idx if phones_out[i]["error_type"]),
        })

    findings = apply_rules(events, load_rules(rules_path))
    scored = [p["score"] for p in phones_out if p["score"] is not None]
    n_err = sum(1 for p in phones_out if p["error_type"])
    overall = {
        "accuracy": round(float(np.mean(scored)), 1) if scored else None,
        "phones": len(phones_out),
        "phones_flagged": n_err,
        "phone_error_rate": round(n_err / len(phones_out), 3) if phones_out else None,
        "words": len(words_out),
        "words_with_errors": sum(1 for w in words_out if w["errors"]),
        "findings": len(findings),
        "threshold": threshold,
    }
    return {"phones": phones_out, "words": words_out, "l1_findings": findings, "overall": overall}


def assess(
    audio: bytes | str | os.PathLike | np.ndarray,
    reference_text: str,
    *,
    model: str | None = None,
    threshold: float | None = None,
    rules_path: str | None = None,
    check_stress: bool = True,
    sample_rate: int | None = None,
) -> dict[str, Any]:
    """Assess how ``audio`` realises ``reference_text``, phone by phone.

    ``audio`` may be WAV/FLAC bytes, a file path, or a float array
    (``sample_rate`` defaults to 16 kHz for arrays).

    Returns ``{phones, words, l1_findings, overall}``; see speakloop/phoneme/README.md.
    """
    t0 = time.perf_counter()
    wav = load_audio(audio, sample_rate)
    m = get_model(model)
    vocab = m.vocab
    prons = g2p_words(reference_text, set(vocab))
    if not prons:
        raise ValueError("reference_text has no words")
    t1 = time.perf_counter()
    em = m.emissions(wav)
    t2 = time.perf_counter()
    out = assess_emissions(em, prons, vocab, wav=wav, threshold=threshold,
                           rules_path=rules_path, check_stress=check_stress)
    t3 = time.perf_counter()
    out["overall"].update({
        "model": m.name,
        "audio_seconds": round(len(wav) / 16000, 2),
        "recognised_ipa": " ".join(m.greedy_tokens(em)),
        "latency_ms": {"g2p_and_load": round((t1 - t0) * 1000), "acoustic": round((t2 - t1) * 1000),
                       "scoring": round((t3 - t2) * 1000), "total": round((t3 - t0) * 1000)},
    })
    return out
