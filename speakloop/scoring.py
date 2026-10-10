"""Deterministic, explainable scoring of a spoken attempt from its transcript.

The device (or browser) does speech-to-text; this module compares the
transcript with the reference and produces:

* content   - share of reference words (or key points) the learner produced
* fluency   - pace in words per minute, fillers, restarts
* pronunciation proxy - reference words that came back as a *systematically*
  different word (books -> book, think -> tink, asked -> ask), which is how an
  ASR engine "hears" a dropped or substituted sound.

Scores are mapped onto an unofficial 10-90 scale that mirrors the familiar
PTE-style range. They are practice estimates, not official test scores.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import asdict, dataclass, field

from .content import TASK_TIME_LIMIT, Drill

FILLERS = {"um", "uh", "er", "erm", "ah", "hmm", "uhm", "ờ", "à", "ừ", "ơ"}

_WORD_RE = re.compile(r"[a-zA-Z0-9À-ỹ']+")

_NUMBER_WORDS = {
    "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five",
    "6": "six", "7": "seven", "8": "eight", "9": "nine", "10": "ten", "11": "eleven",
    "12": "twelve", "20": "twenty", "30": "thirty", "70": "seventy", "90": "ninety",
}


def tokenize(text: str) -> list[str]:
    words = [w.lower().strip("'") for w in _WORD_RE.findall(text or "")]
    return [_NUMBER_WORDS.get(w, w) for w in words if w]


def _same_word(a: str, b: str) -> bool:
    if a == b:
        return True
    # British/American spelling and trivial ASR variants.
    pairs = (("ise", "ize"), ("our", "or"), ("tre", "ter"))
    for x, y in pairs:
        if a.replace(x, y) == b.replace(x, y):
            return True
    return False


def classify_error(ref: str, hyp: str) -> str | None:
    """Return the pronunciation feature a substitution points to, if any."""
    if not hyp or ref == hyp:
        return None
    if ref.startswith("th"):
        rest = ref[2:]
        if any(hyp == sub + rest for sub in ("t", "d", "s", "f", "z")):
            return "th"
    if ref.endswith("ed") and hyp in (ref[:-2], ref[:-1]):
        return "final_ed"
    if ref.endswith("es") and hyp == ref[:-2]:
        return "final_s"
    if ref.endswith("s") and hyp == ref[:-1]:
        return "final_s"
    # Cluster reduction: one consonant missing from a cluster (most -> mos, tests -> tess).
    if len(ref) - len(hyp) == 1 and difflib.SequenceMatcher(None, ref, hyp).ratio() >= 0.8:
        missing = [c for c in ref if ref.count(c) > hyp.count(c)]
        if missing and missing[0] not in "aeiou":
            idx = ref.rfind(missing[0])
            if idx >= len(ref) - 2:
                return "final_consonant"
            return "clusters"
    if hyp == ref[:-1] and ref[-1] not in "aeiou":
        return "final_consonant"
    return None


@dataclass
class WordIssue:
    expected: str
    heard: str | None
    feature: str | None


@dataclass
class AttemptScore:
    task_type: str
    content: int
    fluency: int
    pronunciation: int
    overall: int
    words_per_minute: float | None
    fillers: int
    restarts: int
    matched_words: int
    reference_words: int
    issues: list[WordIssue] = field(default_factory=list)
    weak_features: list[str] = field(default_factory=list)
    correct: bool | None = None
    covered_keywords: list[str] = field(default_factory=list)
    missed_keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _scale(x: float) -> int:
    """Map 0..1 to the 10..90 practice scale."""
    x = max(0.0, min(1.0, x))
    return int(round(10 + 80 * x))


def _fluency(hyp_tokens: list[str], duration: float | None, task_type: str) -> tuple[float, float | None, int, int]:
    fillers = sum(1 for w in hyp_tokens if w in FILLERS)
    restarts = sum(1 for a, b in zip(hyp_tokens, hyp_tokens[1:]) if a == b and a not in FILLERS)
    spoken = [w for w in hyp_tokens if w not in FILLERS]
    wpm = None
    pace = 0.8
    if duration and duration > 0.5 and spoken:
        wpm = round(len(spoken) / (duration / 60.0), 1)
        # Comfortable exam pace for these tasks is ~120-170 wpm.
        if 120 <= wpm <= 170:
            pace = 1.0
        elif wpm < 120:
            pace = max(0.2, wpm / 120)
        else:
            pace = max(0.4, 1 - (wpm - 170) / 150)
        limit = TASK_TIME_LIMIT.get(task_type)
        if limit and duration > limit:
            pace *= 0.8
    penalty = min(0.6, 0.08 * fillers + 0.06 * restarts)
    return max(0.0, pace - penalty), wpm, fillers, restarts


def score_attempt(drill: Drill, transcript: str, duration_seconds: float | None = None) -> AttemptScore:
    hyp = tokenize(transcript)
    hyp_clean = [w for w in hyp if w not in FILLERS]
    fluency_x, wpm, fillers, restarts = _fluency(hyp, duration_seconds, drill.task_type)

    if drill.task_type == "answer_short_question":
        answers = {drill.reference.lower(), *[a.lower() for a in drill.accepted]}
        answers |= {_NUMBER_WORDS.get(a, a) for a in answers}
        joined = " ".join(hyp_clean)
        correct = any(re.search(rf"\b{re.escape(a)}\b", joined) for a in answers)
        near = None
        if not correct:
            for w in hyp_clean:
                for a in answers:
                    feat = classify_error(a, w)
                    if feat:
                        near = WordIssue(a, w, feat)
        content = 1.0 if correct else 0.0
        pron = 0.6 if near else (1.0 if correct else 0.5)
        issues = [near] if near else ([] if correct else [WordIssue(drill.reference, joined or None, None)])
        overall = 0.7 * content + 0.15 * fluency_x + 0.15 * pron
        return AttemptScore(
            drill.task_type, _scale(content), _scale(fluency_x), _scale(pron), _scale(overall),
            wpm, fillers, restarts, int(correct), 1, issues,
            [near.feature] if near and near.feature else ([] if correct else ["content"]),
            correct=correct,
        )

    ref = tokenize(drill.reference)
    sm = difflib.SequenceMatcher(None, ref, hyp_clean, autojunk=False)
    matched = 0
    issues: list[WordIssue] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            matched += i2 - i1
        elif tag == "replace":
            r_words, h_words = ref[i1:i2], hyp_clean[j1:j2]
            for k, r in enumerate(r_words):
                h = h_words[k] if k < len(h_words) else None
                if h is not None and _same_word(r, h):
                    matched += 1
                    continue
                issues.append(WordIssue(r, h, classify_error(r, h) if h else None))
        elif tag == "delete":
            for r in ref[i1:i2]:
                issues.append(WordIssue(r, None, None))

    pron_errors = [i for i in issues if i.feature]
    content_x = matched / len(ref) if ref else 0.0
    covered: list[str] = []
    missed: list[str] = []
    if drill.task_type == "describe_image":
        hs = set(hyp_clean)
        for kw in drill.keywords:
            (covered if kw in hs or kw.rstrip("s") in hs else missed).append(kw)
        content_x = len(covered) / len(drill.keywords) if drill.keywords else content_x
        # Describe Image is free speech: only flag pronunciation slips on keywords.
        pron_errors = [WordIssue(k, h, classify_error(k, h)) for k in missed for h in hs if classify_error(k, h)]
        issues = pron_errors + [WordIssue(k, None, None) for k in missed if k not in {p.expected for p in pron_errors}]
        matched = len(covered)

    attempted = max(1, matched + len(pron_errors))
    pron_x = max(0.0, 1 - len(pron_errors) / attempted * 2.5) if hyp_clean else 0.0

    weights = {"read_aloud": (0.4, 0.3, 0.3), "repeat_sentence": (0.5, 0.25, 0.25), "describe_image": (0.45, 0.3, 0.25)}
    wc, wf, wp = weights.get(drill.task_type, (0.4, 0.3, 0.3))
    overall = wc * content_x + wf * fluency_x + wp * pron_x

    weak: list[str] = []
    for f in sorted({i.feature for i in pron_errors if i.feature}):
        weak.append(f)
    if fluency_x < 0.7:
        weak.append("fluency")
    if content_x < 0.75:
        weak.append("content")

    return AttemptScore(
        drill.task_type, _scale(content_x), _scale(fluency_x), _scale(pron_x), _scale(overall),
        wpm, fillers, restarts, matched, len(drill.keywords) if drill.task_type == "describe_image" else len(ref),
        issues[:12], weak, None, covered, missed,
    )
