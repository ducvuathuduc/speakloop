"""Fast unit tests for speakloop.phoneme (no model weights, no network).

espeak-ng tests are skipped when the binary is missing; the GOP test needs
torch (skipped otherwise). The real-model test lives in test_phoneme_model.py
and is marked ``slow``.
"""

from __future__ import annotations

import math
import shutil

import numpy as np
import pytest

from benchmarks.common import load_l2arctic, parse_phone_label, read_textgrid
from speakloop.phoneme.g2p import (
    WordPron, arpa_stress, arpa_to_ipa, arpa_words, g2p_words, tokenize_ipa, words_of,
)
from speakloop.phoneme.rules import Event, apply_rules, load_rules, phone_position

# A subset of the wav2vec2-espeak-cv-ft vocabulary (multi-char tokens matter).
VOCAB = {
    "<pad>": 0, "<s>": 1, "</s>": 2, "<unk>": 3,
    "ʃ": 4, "iː": 5, "w": 6, "ɔː": 7, "k": 8, "t": 9, "ə": 10, "ð": 11, "ɑː": 12,
    "p": 13, "s": 14, "aɪ": 15, "tʃ": 16, "ɪ": 17, "z": 18, "d": 19, "θ": 20, "ɹ": 21,
    "ɛ": 22, "æ": 23, "n": 24, "l": 25, "uː": 26, "h": 27, "ɑːɹ": 28, "ɚ": 29, "ɡ": 30,
    "m": 31, "f": 32, "v": 33, "b": 34, "eɪ": 35, "oʊ": 36, "ʌ": 37, "ŋ": 38, "j": 39,
    "ᵻ": 40, "i": 41, "ɾ": 42, "ʊ": 43, "ɜː": 44, "dʒ": 45, "aʊ": 46, "ɔɪ": 47, "ʒ": 48,
}
VSET = set(VOCAB)
needs_espeak = pytest.mark.skipif(not (shutil.which("espeak-ng") or shutil.which("espeak")),
                                  reason="espeak-ng not installed")


# ---------------------------------------------------------------- g2p
@pytest.mark.parametrize("arpa,ipa", [
    ("AH0", "ə"), ("AH1", "ʌ"), ("ER0", "ɚ"), ("ER1", "ɜː"), ("IH0", "ɪ"), ("T", "t"),
    ("CH", "tʃ"), ("DH", "ð"), ("G", "ɡ"), ("R", "ɹ"), ("iy1", "iː"), ("AY2", "aɪ"),
])
def test_arpa_to_ipa(arpa, ipa):
    assert arpa_to_ipa(arpa) == ipa


def test_arpa_to_ipa_unknown():
    with pytest.raises(KeyError):
        arpa_to_ipa("XX1")
    with pytest.raises(KeyError):
        arpa_to_ipa("ɪ")


def test_arpa_stress():
    assert arpa_stress("AO1") == 1 and arpa_stress("AH0") == 0 and arpa_stress("T") is None


def test_arpa_words_stress_only_on_vowels():
    (w,) = arpa_words([("walked", ["W", "AO1", "K", "T"])])
    assert w.phones == ["w", "ɔː", "k", "t"]
    assert w.stress == [None, 1, None, None]


def test_tokenize_ipa_longest_match_and_drops_unknown():
    assert tokenize_ipa("ʃˈɑːps", VSET) == ["ʃ", "ɑː", "p", "s"]
    assert tokenize_ipa("wˈɔːkt", VSET) == ["w", "ɔː", "k", "t"]
    assert tokenize_ipa("tʃˈiːz", VSET) == ["tʃ", "iː", "z"]
    assert tokenize_ipa("x☃t", VSET) == ["t"]


def test_words_of():
    assert words_of("God bless 'em, I’ll go!") == ["God", "bless", "em", "I'll", "go"]
    assert words_of("") == []


@needs_espeak
def test_g2p_words_espeak():
    prons = g2p_words("She walked to the shops.", VSET)
    assert [p.text for p in prons] == ["She", "walked", "to", "the", "shops"]
    walked = prons[1]
    assert walked.phones == ["w", "ɔː", "k", "t"]
    assert walked.stress[1] == 1
    assert prons[4].phones[0] == "ʃ" and prons[4].phones[-1] == "s"
    for p in prons:
        assert len(p.phones) == len(p.stress)
        assert all(t in VSET for t in p.phones)


@needs_espeak
def test_g2p_splits_rhotic_digraph():
    (car,) = g2p_words("car", VSET)
    assert car.phones[-2:] == ["ɑː", "ɹ"]


# ---------------------------------------------------------------- rules
def _ev(**kw):
    base = dict(error_type="deletion", word="walked", word_index=0, phone_index=3,
                expected="t", heard=None, position="word_final", in_cluster=True)
    base.update(kw)
    return Event(**base)


def test_rules_load():
    rules = load_rules()
    ids = [r.id for r in rules]
    assert len(ids) == len(set(ids)) and "VN-ED-DROP" in ids and "VN-TH-STOP" in ids
    for r in rules:
        assert r.description_vi and r.description_en
        assert "word_regex" not in r.when and "not_word_regex" not in r.when


@pytest.mark.parametrize("ev,rule_id", [
    (_ev(), "VN-ED-DROP"),                                                     # walked -> walk
    (_ev(word="shops", expected="s"), "VN-S-DROP"),                           # shops -> shop
    (_ev(word="bus", expected="s", in_cluster=False), "VN-FINAL-CONSONANT-DROP"),
    (_ev(word="hand", expected="d", position="word_final", in_cluster=True), "VN-CLUSTER-REDUCTION"),
    (_ev(word="think", error_type="substitution", expected="θ", heard="t", position="word_initial",
         in_cluster=False), "VN-TH-STOP"),
    (_ev(word="the", error_type="substitution", expected="ð", heard="d", position="word_initial",
         in_cluster=False), "VN-DH-STOP"),
    (_ev(word="she", error_type="substitution", expected="ʃ", heard="s", position="word_initial",
         in_cluster=False), "VN-SH-S"),
    (_ev(word="night", error_type="substitution", expected="n", heard="l", position="word_initial",
         in_cluster=False), "VN-N-L"),
    (_ev(word="bus", error_type="insertion", expected=None, heard="ə"), "VN-EPENTHESIS"),
])
def test_rule_matching(ev, rule_id):
    (f,) = apply_rules([ev], load_rules())
    assert f["rule_id"] == rule_id
    assert f["word"] == ev.word and f["expected"] == ev.expected


def test_rule_not_word_regex_and_no_match():
    # "bus" ends in s but is excluded from VN-S-DROP; a correct-heard sub matches nothing.
    (f,) = apply_rules([_ev(word="bus", expected="s", in_cluster=False)], load_rules())
    assert f["rule_id"] != "VN-S-DROP"
    assert apply_rules([_ev(error_type="substitution", expected="t", heard="ɾ",
                            position="word_medial", word="water")], load_rules()) == []


def test_one_finding_per_event():
    evs = [_ev(), _ev(word="shops", expected="s")]
    assert len(apply_rules(evs, load_rules())) == 2


def test_phone_position():
    w = ["w", "ɔː", "k", "t"]
    assert phone_position(w, 0) == ("word_initial", False)
    assert phone_position(w, 1) == ("word_medial", False)
    assert phone_position(w, 2) == ("word_medial", True)
    assert phone_position(w, 3) == ("word_final", True)
    assert phone_position(["ə"], 0) == ("word_final", False)


# ---------------------------------------------------------------- TextGrid / L2-ARCTIC
TEXTGRID = '''File type = "ooTextFile"
Object class = "TextGrid"

xmin = 0 
xmax = 1.0 
tiers? <exists> 
size = 2 
item []: 
    item [1]:
        class = "IntervalTier" 
        name = "words" 
        xmin = 0 
        xmax = 1.0 
        intervals: size = 3 
        intervals [1]:
            xmin = 0 
            xmax = 0.1 
            text = "" 
        intervals [2]:
            xmin = 0.1 
            xmax = 0.6 
            text = "will" 
        intervals [3]:
            xmin = 0.6 
            xmax = 1.0 
            text = "it" 
    item [2]:
        class = "IntervalTier" 
        name = "phones" 
        xmin = 0 
        xmax = 1.0 
        intervals: size = 7 
        intervals [1]:
            xmin = 0 
            xmax = 0.1 
            text = "sil" 
        intervals [2]:
            xmin = 0.1 
            xmax = 0.3 
            text = "W" 
        intervals [3]:
            xmin = 0.3 
            xmax = 0.5 
            text = "IH1,IY1,S" 
        intervals [4]:
            xmin = 0.5 
            xmax = 0.6 
            text = "L,sil,d " 
        intervals [5]:
            xmin = 0.6 
            xmax = 0.8 
            text = "IH1" 
        intervals [6]:
            xmin = 0.8 
            xmax = 0.9 
            text = "T" 
        intervals [7]:
            xmin = 0.9 
            xmax = 1.0 
            text = "sil,AH0,a" 
'''


def test_read_textgrid():
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "x.TextGrid"
        p.write_text(TEXTGRID, encoding="utf-8")
        tiers = read_textgrid(p)
    assert set(tiers) == {"words", "phones"}
    assert tiers["words"][1] == (0.1, 0.6, "will")
    assert tiers["phones"][3] == (0.5, 0.6, "L,sil,d ")
    assert len(tiers["phones"]) == 7


@pytest.mark.parametrize("label,expected", [
    ("AO1", ("AO1", "AO", "correct")),
    ("IH1,IY1,S", ("IH1", "IY", "substitution")),
    ("L,sil,d ", ("L", None, "deletion")),
    ("sil,AH0,a", (None, "AH0", "addition")),
    ("Z,S*,s", ("Z", "S", "substitution")),
    ("T,err,s", ("T", None, "substitution")),
    ("sil", (None, None, "silence")),
    ("", (None, None, "silence")),
])
def test_parse_phone_label(label, expected):
    assert parse_phone_label(label) == expected


def test_load_l2arctic_layout(tmp_path):
    spk = tmp_path / "HQTV"
    for sub in ("annotation", "transcript", "wav"):
        (spk / sub).mkdir(parents=True)
    (spk / "annotation" / "arctic_a0001.TextGrid").write_text(TEXTGRID, encoding="utf-8")
    (spk / "transcript" / "arctic_a0001.txt").write_text("Will it\n")
    (u,) = load_l2arctic(["HQTV"], tmp_path)
    assert u.key == "HQTV_arctic_a0001" and u.transcript == "Will it" and u.additions == 1
    assert [w.text for w in u.words] == ["will", "it"]
    kinds = [p.kind for p in u.words[0].phones]
    assert kinds == ["correct", "substitution", "deletion"]


# ---------------------------------------------------------------- GOP on synthetic posteriors
def _posteriors(path: list[str], frames_per: int = 4) -> np.ndarray:
    """Log-posteriors that strongly favour ``path`` (one token per segment, blank between)."""
    V = max(VOCAB.values()) + 1
    rows = []
    for tok in path:
        for _ in range(frames_per):
            r = np.full(V, 1e-4)
            r[VOCAB[tok]] = 1.0
            rows.append(r)
        r = np.full(V, 1e-4)
        r[0] = 1.0
        rows.append(r)
    lp = np.log(np.array(rows, dtype=np.float64))
    lp -= np.log(np.exp(lp).sum(1, keepdims=True))
    return lp.astype(np.float32)


def test_gop_flags_substitution_and_deletion():
    pytest.importorskip("torch")
    from speakloop.phoneme.gop import score_phones

    canon = ["θ", "ɪ", "ŋ", "k"]                    # "think"
    lp = _posteriors(["t", "ɪ", "ŋ"])                # heard "tin(g)", final k dropped
    res = score_phones(lp, canon, VOCAB, word_final={3})
    by = {p.expected: p for p in res.phones}
    assert by["θ"].flagged and by["θ"].error_type == "substitution" and by["θ"].heard == "t"
    assert by["k"].flagged and by["k"].error_type == "deletion"
    assert not by["ɪ"].flagged and not by["ŋ"].flagged
    assert all(0 <= p.score <= 100 for p in res.phones)
    assert by["ɪ"].start is not None and by["ɪ"].end > by["ɪ"].start


def test_gop_clean_utterance_and_accepted_variant():
    pytest.importorskip("torch")
    from speakloop.phoneme.gop import score_phones

    canon = ["w", "ɔː", "t", "ɚ"]                    # "water"
    lp = _posteriors(["w", "ɔː", "ɾ", "ɚ"])          # flapped t is native-like
    res = score_phones(lp, canon, VOCAB, word_final={3})
    assert not any(p.flagged for p in res.phones)
    assert all(math.isfinite(p.gop) for p in res.phones)


def test_assess_emissions_shape():
    pytest.importorskip("torch")
    from speakloop.phoneme import assess_emissions
    from speakloop.phoneme.model import Emissions

    prons = [WordPron("walked", ["w", "ɔː", "k", "t"], [None, 1, None, None])]
    out = assess_emissions(Emissions(_posteriors(["w", "ɔː", "k"])), prons, VOCAB, check_stress=False)
    assert set(out) == {"phones", "words", "l1_findings", "overall"}
    assert out["overall"]["phones"] == 4 and out["overall"]["phones_flagged"] >= 1
    assert out["l1_findings"][0]["rule_id"] == "VN-ED-DROP"
    assert out["words"][0]["heard_ipa"] == "wɔːk"
