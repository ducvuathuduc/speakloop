"""Pronunciation tools on the MCP server: ``assess_pronunciation`` and ``start_pair_drill``.

``assess_pronunciation`` runs the phoneme scorer (``speakloop.phoneme.assess``: wav2vec2
espeak-phoneme CTC + GOP + the Vietnamese-L1 rule pack in ``skills/l1-vi/rules.yaml``) on a
short WAV recording and returns the card's ``assessment`` shape. With a ``learner_id`` the
flagged sounds are written to the learner's Sound Graph (FSRS), the same store the memory
tools read.

``start_pair_drill`` turns a finding (``focus`` = a rule id), a Sound Graph node
(``node`` = a sound id) or, with neither, the FSRS-due sound into a minimal-pair card.

Heavy dependencies (numpy, torch, transformers, soundfile) load only on the first
``assess_pronunciation`` call; the server and these tools' listing need none of them.
Install them with ``pip install -r requirements-phoneme.txt`` (and ``apt install espeak-ng``).
"""

# No `from __future__ import annotations`: the SDK resolves tool signatures at runtime.

import base64
import binascii
import difflib
import io
import json
import os
import wave
from typing import Annotated, Any, Callable

from pydantic import Field

from mcp.types import CallToolResult, TextContent, ToolAnnotations

from .memory import SoundGraph

MAX_AUDIO_SECONDS = float(os.environ.get("SPEAKLOOP_MAX_AUDIO_SECONDS", "30"))
MAX_AUDIO_BYTES = int(MAX_AUDIO_SECONDS * 48000 * 2 * 2) + 1024  # 30 s of 48 kHz 16-bit stereo

# English espeak tokens used to show a word's sounds on the drill card (display only).
DISPLAY_TOKENS = {
    "ʃ", "iː", "w", "ɔː", "k", "t", "ə", "ð", "ɑː", "p", "s", "aɪ", "tʃ", "ɪ", "z", "d", "θ", "ɹ",
    "ɛ", "æ", "n", "l", "uː", "h", "ɑːɹ", "ɔːɹ", "ɪɹ", "ɛɹ", "ʊɹ", "ɚ", "ɡ", "m", "f", "v", "b",
    "eɪ", "oʊ", "ʌ", "ŋ", "j", "ᵻ", "i", "ɾ", "ʊ", "ɜː", "dʒ", "aʊ", "ɔɪ", "ʒ", "ɐ", "ɒ", "əl", "oːɹ",
}

_OP = {"deletion": "delete", "substitution": "substitute", "insertion": "insert"}

# Injection point: tests (and alternative engines) can swap the scorer.
_assess_impl: Callable[..., dict] | None = None


class PhonemeEngineUnavailable(RuntimeError):
    pass


def _scorer() -> Callable[..., dict]:
    if _assess_impl is not None:
        return _assess_impl
    try:
        from .phoneme import assess
        import torch  # noqa: F401  (fail fast with a clear message)
        import transformers  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise PhonemeEngineUnavailable(
            f"The phoneme engine is not installed on this server ({exc.name}). "
            "Install it with: pip install -r requirements-phoneme.txt && apt install espeak-ng") from exc
    return assess


# ------------------------------------------------------------------ audio
def decode_audio(audio_b64: str, sample_rate: int | None = None) -> bytes:
    """Base64 audio -> WAV/FLAC bytes the scorer can read.

    Accepts a WAV (RIFF) or FLAC file, or raw little-endian 16-bit mono PCM when
    ``sample_rate`` is given. Data URLs (``data:audio/wav;base64,...``) are accepted.
    """
    if not audio_b64:
        raise ValueError("audio_wav_base64 is empty")
    if audio_b64.startswith("data:") and "," in audio_b64:
        audio_b64 = audio_b64.split(",", 1)[1]
    if len(audio_b64) > MAX_AUDIO_BYTES * 4 // 3 + 8:
        raise ValueError(f"audio is too long (max {MAX_AUDIO_SECONDS:g} s)")
    try:
        raw = base64.b64decode(audio_b64, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("audio_wav_base64 is not valid base64") from exc
    if raw[:4] == b"RIFF" and raw[8:12] == b"WAVE":
        try:
            with wave.open(io.BytesIO(raw)) as w:
                secs = w.getnframes() / float(w.getframerate() or 1)
        except (wave.Error, EOFError):
            secs = 0.0  # non-PCM WAV (e.g. float): let the scorer's reader decide
        if secs > MAX_AUDIO_SECONDS:
            raise ValueError(f"audio is {secs:.1f} s; max {MAX_AUDIO_SECONDS:g} s")
        return raw
    if raw[:4] == b"fLaC":
        return raw
    if not sample_rate:
        raise ValueError("audio is not a WAV/FLAC file; send WAV, or raw 16-bit PCM with sample_rate")
    if len(raw) % 2:
        raw = raw[:-1]
    if len(raw) / 2 / sample_rate > MAX_AUDIO_SECONDS:
        raise ValueError(f"audio is longer than {MAX_AUDIO_SECONDS:g} s")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sample_rate))
        w.writeframes(raw)
    return buf.getvalue()


# ------------------------------------------------------------------ result shaping
def _vowelish(p: str | None) -> bool:
    from .phoneme.g2p import is_vowel

    return bool(p) and is_vowel(p)


def phone_errors(result: dict) -> list[dict]:
    """The scorer's flagged phones as Sound Graph ``PhoneError`` dicts (op/target/realized/position...)."""
    phones, words = result.get("phones", []), result.get("words", [])
    sound_by_phone = {f.get("phone_index"): f.get("sound_id") for f in result.get("l1_findings", [])}
    out = []
    for w in words:
        idx = list(w.get("phone_indices") or [])
        exp = [phones[i]["expected"] for i in idx]
        vowels = [k for k, p in enumerate(exp) if _vowelish(p)]
        text = (w.get("word") or "").lower().strip(".,!?;:\"")
        for k, i in enumerate(idx):
            ph = phones[i]
            et = ph.get("error_type")
            if et in _OP:
                if _vowelish(ph["expected"]):
                    pos = "nucleus"
                elif vowels and k < vowels[0]:
                    pos = "onset"
                else:
                    pos = "coda"
                err = {"op": _OP[et], "target": ph["expected"], "position": pos, "word": text,
                       "prev": exp[k - 1] if k else None, "next": exp[k + 1] if k + 1 < len(exp) else None}
                if et == "substitution":
                    err["realized"] = ph.get("ipa")
                if k == len(idx) - 1 and ph["expected"] in ("t", "d") and text.endswith("ed"):
                    err["morpheme"] = "-ed"
                elif k == len(idx) - 1 and ph["expected"] in ("s", "z") and text.endswith("s"):
                    err["morpheme"] = "-s"
                if sound_by_phone.get(i):
                    err["sound_id"] = sound_by_phone[i]
                out.append({k2: v for k2, v in err.items() if v is not None})
            if ph.get("inserted_after"):
                out.append({"op": "insert", "realized": ph["inserted_after"], "position": "coda", "word": text,
                            "prev": ph["expected"]})
    return out


def to_card(result: dict, reference_text: str) -> dict:
    """Scorer output -> the MCP App ``assessment`` card shape (scores 0..1, word phone ranges)."""
    phones = []
    for p in result.get("phones", []):
        sc = p.get("score")
        phones.append({"ipa": p.get("ipa"), "expected": p.get("expected"), "start": p.get("start"),
                       "end": p.get("end"), "score": None if sc is None else round(sc / 100.0, 3),
                       "error_type": p.get("error_type")})
    words = []
    for w in result.get("words", []):
        idx = w.get("phone_indices") or []
        sc = w.get("score")
        words.append({"word": w.get("word"), "start": w.get("start"), "end": w.get("end"),
                      "score": None if sc is None else round(sc / 100.0, 3),
                      "phone_range": [idx[0], idx[-1] + 1] if idx else [0, 0],
                      "expected_ipa": w.get("expected_ipa"), "heard_ipa": w.get("heard_ipa")})
    findings = [{**f, "position": f.get("phone_index")} for f in result.get("l1_findings", [])]
    ov = result.get("overall", {})
    n = ov.get("phones") or len(phones)
    acc = ov.get("accuracy")
    return {
        "engine": ov.get("model", "speakloop.phoneme"),
        "reference_text": reference_text,
        "phones": phones, "words": words, "l1_findings": findings,
        "overall": {"score": None if acc is None else round(acc / 100.0, 3),
                    "phones_correct": n - (ov.get("phones_flagged") or 0), "phones_total": n,
                    "phone_error_rate": ov.get("phone_error_rate"),
                    "audio_seconds": ov.get("audio_seconds"), "latency_ms": ov.get("latency_ms")},
    }


def _speech_for(card: dict) -> str:
    f = (card.get("l1_findings") or [None])[0]
    if f:
        return f"{f['description_en']} {f.get('tip_en') or ''}".strip()
    flagged = [p for p in card["phones"] if p.get("error_type")]
    if not flagged:
        return "Every sound came through clearly. Nice."
    p = flagged[0]
    return f"One sound to check: /{p['expected']}/ did not come through as expected."


# ------------------------------------------------------------------ pair drill
def word_phones(word: str) -> list[str]:
    """Display IPA tokens of one word via espeak-ng ([] when espeak is not installed)."""
    try:
        from .phoneme.g2p import g2p_words

        prons = g2p_words(word, DISPLAY_TOKENS)
    except Exception:  # espeak missing, or a word it cannot say
        return []
    return [p for wp in prons for p in wp.phones]


def _diff(a: list[str], b: list[str]) -> tuple[list[int], list[int]]:
    """Indices in a and in b that are not part of the longest common phone alignment."""
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    keep_a, keep_b = set(), set()
    for blk in sm.get_matching_blocks():
        keep_a.update(range(blk.a, blk.a + blk.size))
        keep_b.update(range(blk.b, blk.b + blk.size))
    return [i for i in range(len(a)) if i not in keep_a], [i for i in range(len(b)) if i not in keep_b]


def rule_sound(rule_id: str, expected: str | None = None) -> str | None:
    from .phoneme.rules import load_rules

    for r in load_rules():
        if r.id == rule_id:
            return r.sound_for(expected) or (next(iter(r.sound.values())) if isinstance(r.sound, dict) else None)
    return None


def build_pair_drill(graph: SoundGraph, learner_id: str, *, focus: str | None = None, node: str | None = None,
                     l1: str = "vi", step: int = 1, minutes: int = 2) -> dict:
    pack = graph.pack(l1)
    reason = None
    sound_id = node
    if not sound_id and focus:
        sound_id = rule_sound(focus) if not pack.sound(focus) else focus
        if not sound_id:
            raise ValueError(f"no drillable sound for '{focus}' in pack {pack.id}")
        reason = "finding"
    if sound_id:
        s = pack.sound(sound_id)
        if s is None:
            raise ValueError(f"unknown sound '{sound_id}' for pack {pack.id}")
        reason = reason or "requested"
        pairs = s["drills"]["minimal_pairs"]
    else:
        nd = graph.next_drill(learner_id, l1)
        s, reason, pairs = pack.sound(nd["sound_id"]), nd["reason"], nd["minimal_pairs"]
    pairs = pairs[: max(1, min(8, len(pairs)))]
    target, miss = pairs[(step - 1) % len(pairs)]
    t_ph, m_ph = word_phones(target), word_phones(miss)
    d_miss, d_target = _diff(m_ph, t_ph)
    secs = minutes * 60
    return {
        "kind": "pair_drill", "learner_id": learner_id, "sound_id": s["id"], "reason": reason,
        "title": f"{minutes}-minute warm-up", "focus_label": s["label"],
        "instruction": "Say the highlighted word",
        "step": step, "total": len(pairs), "seconds_left": secs, "seconds_total": secs,
        "pair": {"a": {"word": miss, "ipa": m_ph, "diff": d_miss},
                 "b": {"word": target, "ipa": t_ph, "diff": d_target}, "say": "b"},
        "pairs": pairs, "reference_text": target,
        "tip_en": s["tip_en"], "tip_l1": s["tip_l1"], "why_l1": s["why_l1"],
        "pack": f"{pack.id}@{pack.version}",
        "speech": f"Let's practise {s['speech_hint']}. Listen: {target}. Not {miss}. Now you say: {target}.",
    }


# ------------------------------------------------------------------ MCP registration
def _result(payload: dict[str, Any]) -> CallToolResult:
    speech = payload.get("speech", "")
    data = {k: v for k, v in payload.items() if k != "speech"}
    return CallToolResult(content=[TextContent(type="text", text=speech + "\n\n" + json.dumps(data, ensure_ascii=False, default=str))],
                          structured_content=payload)


def _err(msg: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=msg)], is_error=True)


def register(mcp, graph: SoundGraph, meta: dict | None = None) -> None:
    kw = {"meta": meta} if meta else {}
    from .memory_tools import l1_type

    L1, L1_DEFAULT = l1_type(list(graph.packs))

    @mcp.tool(title="Assess pronunciation",
              description=("Score a short recording phone by phone against the sentence the learner meant to say "
                           "(wav2vec2 phoneme recogniser + goodness-of-pronunciation, open weights, runs on the server). "
                           "Returns every expected sound with what was heard, word scores, and first-language findings "
                           "such as a dropped -ed. With learner_id, flagged sounds are recorded in the Sound Graph."),
              annotations=ToolAnnotations(read_only_hint=False, idempotent_hint=False, open_world_hint=False), **kw)
    def assess_pronunciation(
        reference_text: Annotated[str, Field(min_length=1, max_length=400, description="The sentence the learner was asked to say")],
        audio_wav_base64: Annotated[str, Field(description="Base64 WAV (or FLAC) of the attempt, up to 30 s; raw 16-bit mono PCM if sample_rate is set")],
        sample_rate: Annotated[int | None, Field(ge=8000, le=96000, description="Sample rate in Hz; required only for raw PCM (WAV carries its own)")] = None,
        learner_id: Annotated[str | None, Field(description="Learner id; when set, flagged sounds update the Sound Graph")] = None,
        l1: L1 = L1_DEFAULT,
    ) -> CallToolResult:
        try:
            wav = decode_audio(audio_wav_base64, sample_rate)
            res = _scorer()(wav, reference_text)
        except PhonemeEngineUnavailable as exc:
            return _err(str(exc))
        except (ValueError, RuntimeError) as exc:
            return _err(f"Could not assess that recording: {exc}")
        card = to_card(res, reference_text)
        payload = {"kind": "assessment", **card}
        if learner_id:
            try:
                errs = phone_errors(res)
                practised = []
                rec = graph.record_attempt(learner_id, errors=errs, practised=practised,
                                           word=reference_text, l1=l1)
                payload["learner_id"] = learner_id
                payload["sound_graph_update"] = {"recorded": rec["recorded"], "unclassified": len(rec["unclassified"])}
            except KeyError as exc:
                return _err(str(exc))
        payload["speech"] = _speech_for(card)
        return _result(payload)

    @mcp.tool(title="Start a minimal-pair drill",
              description=("Start a short minimal-pair drill (walk / walked, think / tink). Give focus = a finding's "
                           "rule_id from assess_pronunciation, or node = a Sound Graph sound id; with neither, the sound "
                           "the learner's FSRS schedule says is due. Returns both words with their sounds and the "
                           "differing sound highlighted."),
              annotations=ToolAnnotations(read_only_hint=True), **kw)
    def start_pair_drill(
        learner_id: Annotated[str, Field(description="Stable id of the learner.")] = "guest",
        focus: Annotated[str | None, Field(description="rule_id of a finding, e.g. VN-ED-DROP")] = None,
        node: Annotated[str | None, Field(description="Sound Graph sound id, e.g. ed_t_after_voiceless")] = None,
        step: Annotated[int, Field(ge=1, le=20, description="Which pair of the drill to show (1-based)")] = 1,
        l1: L1 = L1_DEFAULT,
    ) -> CallToolResult:
        try:
            return _result(build_pair_drill(graph, learner_id, focus=focus, node=node, l1=l1, step=step))
        except (KeyError, ValueError) as exc:
            return _err(str(exc))
