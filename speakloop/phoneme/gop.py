"""CTC forced alignment + alignment-free GOP (goodness of pronunciation).

For a canonical phone sequence ``c_1..c_N`` and CTC log-posteriors ``X``:

* timing: Viterbi forced alignment of the canonical tokens
  (``torchaudio.functional.forced_align``; a NumPy Viterbi is used if that
  API is missing).
* score: for every phone ``i`` we compare the CTC likelihood of the whole
  utterance under the canonical sequence against the same sequence with phone
  ``i`` replaced by a competitor (top posterior tokens near the phone, plus
  the L1 confusions such as θ→t, ʃ→s, iː→ɪ) or deleted:

      GOP_i = log P(X | c with best accepted variant at i)
              - max_{alt} log P(X | c with alt at i)

  ``GOP_i < threshold`` flags the phone; the winning ``alt`` says what the
  model heard (a token, or nothing for a deletion). The phone score shown to
  learners is ``100 * sigmoid(GOP_i)``, i.e. how strongly the target beats the
  best alternative. This is the "GOP-CTC / substitution-aware" family of
  scores (Cao et al., Interspeech 2024; Parikh et al. 2025), not a trained
  scorer.

An optional insertion test checks for an epenthetic schwa after word-final
consonants (a common Vietnamese-L1 repair: "bus" -> /bʌsə/).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .g2p import ACCEPTED_VARIANTS, is_vowel

# Confusions always tested, whatever the posterior says (L1 priors).
L1_CONFUSIONS: dict[str, tuple[str, ...]] = {
    "θ": ("t", "s", "f", "d"), "ð": ("d", "z", "t", "v"),
    "ʃ": ("s", "tʃ"), "ʒ": ("z", "ʃ", "dʒ"), "tʃ": ("ʃ", "t", "s"), "dʒ": ("z", "d", "tʃ"),
    "z": ("s",), "v": ("f", "b", "w"), "d": ("t",), "b": ("p",), "ɡ": ("k",),
    "iː": ("ɪ",), "ɪ": ("iː",), "uː": ("ʊ",), "ʊ": ("uː",), "ɔː": ("ɑː", "oʊ"),
    "æ": ("ɛ", "eɪ"), "ɛ": ("æ", "eɪ"), "eɪ": ("ɛ",), "oʊ": ("ɔː",),
    "n": ("l",), "l": ("n",), "ɹ": ("l", "z"), "p": ("b", "f"), "t": ("d",), "k": ("ɡ",),
    "ŋ": ("n",), "s": ("ʃ", "z"), "w": ("v",), "h": ("x",),
}

SPECIAL = {"<pad>", "<s>", "</s>", "<unk>"}


@dataclass
class PhoneScore:
    index: int
    expected: str
    gop: float | None
    score: float | None  # 0..100
    heard: str | None  # winning competitor token; None = deleted (if flagged) / same
    best_alt_is_deletion: bool
    start: float | None
    end: float | None
    flagged: bool = False
    error_type: str | None = None  # deletion | substitution | None


@dataclass
class InsertionScore:
    after_index: int
    token: str
    gain: float  # log P(with insertion) - log P(canonical)
    start: float | None = None
    end: float | None = None


@dataclass
class GopResult:
    phones: list[PhoneScore]
    insertions: list[InsertionScore] = field(default_factory=list)
    frame_seconds: float = 0.02
    canonical_ll: float | None = None


def _forced_align(log_probs: np.ndarray, targets: list[int], blank: int) -> list[tuple[int, int]] | None:
    """Return (first_frame, last_frame) per target token, or None if impossible."""
    T = log_probs.shape[0]
    if not targets:
        return []
    need = len(targets) + sum(1 for a, b in zip(targets, targets[1:]) if a == b)
    if T < need:
        return None
    try:
        import torch
        import torchaudio.functional as AF

        lp = torch.from_numpy(np.ascontiguousarray(log_probs))[None]
        tg = torch.tensor([targets], dtype=torch.int32)
        ali, _ = AF.forced_align(lp, tg, blank=blank)
        path = ali[0].tolist()
    except Exception:  # pragma: no cover - torchaudio API missing
        path = _viterbi_numpy(log_probs, targets, blank)
    spans: list[list[int]] = []
    ti = -1
    prev = blank
    for t, tok in enumerate(path):
        if tok != blank and (tok != prev or prev == blank):
            ti += 1
            spans.append([t, t])
        elif tok != blank and ti >= 0:
            spans[ti][1] = t
        prev = tok
    if len(spans) != len(targets):
        return None
    return [(a, b) for a, b in spans]


def _viterbi_numpy(lp: np.ndarray, targets: list[int], blank: int) -> list[int]:
    ext = [blank]
    for t in targets:
        ext += [t, blank]
    S, T = len(ext), lp.shape[0]
    NEG = -1e30
    dp = np.full((T, S), NEG)
    bp = np.zeros((T, S), dtype=np.int32)
    dp[0, 0] = lp[0, ext[0]]
    if S > 1:
        dp[0, 1] = lp[0, ext[1]]
    for t in range(1, T):
        for s in range(S):
            cands = [(dp[t - 1, s], s)]
            if s >= 1:
                cands.append((dp[t - 1, s - 1], s - 1))
            if s >= 2 and ext[s] != blank and ext[s] != ext[s - 2]:
                cands.append((dp[t - 1, s - 2], s - 2))
            v, b = max(cands)
            dp[t, s] = v + lp[t, ext[s]]
            bp[t, s] = b
    s = S - 1 if dp[T - 1, S - 1] >= dp[T - 1, S - 2] else S - 2
    path = []
    for t in range(T - 1, -1, -1):
        path.append(ext[s])
        s = bp[t, s]
    return path[::-1]


def _batch_ll(log_probs: np.ndarray, seqs: list[list[int]], blank: int, chunk: int = 256) -> np.ndarray:
    """log P(X | seq) for many sequences via CTC (on a gathered sub-vocabulary)."""
    import torch
    import torch.nn.functional as F

    used = sorted({blank} | {t for s in seqs for t in s})
    remap = {t: i for i, t in enumerate(used)}
    sub = torch.from_numpy(np.ascontiguousarray(log_probs[:, used]))  # (T, U)
    T = sub.shape[0]
    out = np.empty(len(seqs), dtype=np.float64)
    for c0 in range(0, len(seqs), chunk):
        part = seqs[c0:c0 + chunk]
        B = len(part)
        lens = torch.tensor([len(s) for s in part], dtype=torch.long)
        maxlen = max(1, int(lens.max()))
        tg = torch.zeros((B, maxlen), dtype=torch.long)
        for j, s in enumerate(part):
            if s:
                tg[j, :len(s)] = torch.tensor([remap[t] for t in s])
        lp = sub[:, None, :].expand(T, B, sub.shape[1]).contiguous()
        loss = F.ctc_loss(lp, tg, torch.full((B,), T, dtype=torch.long), lens,
                          blank=remap[blank], reduction="none", zero_infinity=False)
        out[c0:c0 + B] = -loss.double().numpy()
    return out


def score_phones(
    log_probs: np.ndarray,
    phones: list[str],
    vocab: dict[str, int],
    word_final: set[int] | None = None,
    threshold: float = 0.0,
    top_k: int = 6,
    frame_seconds: float = 0.02,
    test_insertions: bool = True,
    blank: str = "<pad>",
) -> GopResult:
    """Score each canonical phone against competitors. ``phones`` are model tokens."""
    blank_id = vocab.get(blank, 0)
    id2tok = {i: t for t, i in vocab.items()}
    keep = [i for i, p in enumerate(phones) if p in vocab]
    toks = [vocab[phones[i]] for i in keep]
    N = len(toks)
    if N == 0:
        return GopResult([PhoneScore(i, p, None, None, None, False, None, None) for i, p in enumerate(phones)])

    spans = _forced_align(log_probs, toks, blank_id)
    T = log_probs.shape[0]
    post = np.exp(log_probs)
    special_ids = {vocab[s] for s in SPECIAL if s in vocab}

    seqs: list[list[int]] = [toks]
    plan: list[tuple[list[int], list[tuple[int | None, int]]]] = []  # (variant seq idx, [(alt tok|None, seq idx)])
    for j in range(N):
        canon = phones[keep[j]]
        variants = [toks[j]] + [vocab[v] for v in ACCEPTED_VARIANTS.get(canon, ()) if v in vocab]
        vidx = []
        for v in variants:
            if v == toks[j]:
                vidx.append(0)
            else:
                seqs.append(toks[:j] + [v] + toks[j + 1:])
                vidx.append(len(seqs) - 1)
        # competitors: top-k posterior tokens around the aligned span + L1 confusions
        if spans:
            a, b = spans[j]
            lo, hi = max(0, a - 2), min(T, b + 3)
        else:
            lo, hi = int(j / N * T), int((j + 1) / N * T) + 1
        mass = post[lo:hi].sum(0)
        order = np.argsort(-mass)
        alts: list[int] = []
        vset = set(variants)
        for t in order:
            t = int(t)
            if t == blank_id or t in special_ids or t in vset:
                continue
            alts.append(t)
            if len(alts) >= top_k:
                break
        for c in L1_CONFUSIONS.get(canon, ()):
            if c in vocab and vocab[c] not in vset and vocab[c] not in alts:
                alts.append(vocab[c])
        aidx: list[tuple[int | None, int]] = []
        for t in alts:
            seqs.append(toks[:j] + [t] + toks[j + 1:])
            aidx.append((t, len(seqs) - 1))
        seqs.append(toks[:j] + toks[j + 1:])
        aidx.append((None, len(seqs) - 1))
        plan.append((vidx, aidx))

    ins_plan: list[tuple[int, int]] = []
    if test_insertions and word_final and "ə" in vocab:
        schwa = vocab["ə"]
        for j in range(N):
            if keep[j] in word_final and not is_vowel(phones[keep[j]]):
                seqs.append(toks[:j + 1] + [schwa] + toks[j + 1:])
                ins_plan.append((j, len(seqs) - 1))

    ll = _batch_ll(log_probs, seqs, blank_id)
    base = ll[0]

    out: list[PhoneScore] = [PhoneScore(i, p, None, None, None, False, None, None) for i, p in enumerate(phones)]
    for j, (vidx, aidx) in enumerate(plan):
        canon_ll = max(ll[k] for k in vidx)
        best_alt_tok, best_alt_ll = max(aidx, key=lambda x: ll[x[1]])
        best_alt_ll = ll[best_alt_ll]
        if not math.isfinite(canon_ll):
            gop = -50.0
        elif not math.isfinite(best_alt_ll):
            gop = 50.0
        else:
            gop = float(canon_ll - best_alt_ll)
        gop = max(-50.0, min(50.0, gop))
        score = 100.0 / (1.0 + math.exp(-gop))
        i = keep[j]
        ps = out[i]
        ps.gop, ps.score = gop, score
        ps.best_alt_is_deletion = best_alt_tok is None
        ps.heard = id2tok.get(best_alt_tok) if best_alt_tok is not None else None
        if spans:
            a, b = spans[j]
            ps.start = a * frame_seconds
            ps.end = (b + 1) * frame_seconds
        ps.flagged = gop < threshold
        if ps.flagged:
            ps.error_type = "deletion" if best_alt_tok is None else "substitution"
        else:
            ps.heard = phones[i]

    # boundary-based phone ends: stretch to the next phone start when close
    timed = [p for p in out if p.start is not None]
    for p, q in zip(timed, timed[1:]):
        if q.start - p.end < 0.15:
            p.end = q.start

    insertions = [InsertionScore(keep[j], "ə", float(ll[k] - base)) for j, k in ins_plan]
    for ins in insertions:
        p = out[ins.after_index]
        ins.start = p.end
        ins.end = p.end
    return GopResult(out, insertions, frame_seconds, float(base))
