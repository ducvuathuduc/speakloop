"""Grapheme-to-phoneme for reference text, in the phone inventory of the
wav2vec2 espeak models.

The phoneme recogniser (facebook/wav2vec2-*-espeak-cv-ft) was trained on
espeak-ng IPA, so the reference must be phonemised with espeak-ng too, then
split into the model's own tokens (``aɪ`` and ``tʃ`` are single tokens, ``ɔː``
is one token, and so on).

ARPAbet input (L2-ARCTIC, speechocean762, CMUdict) is mapped onto the same
tokens so benchmarks can score against the corpus' own canonical phones.
"""

from __future__ import annotations

import functools
import re
import shutil
import subprocess
from dataclasses import dataclass, field

# Phones a learner of English is assessed on. Order matters only for display.
ARPA_TO_IPA: dict[str, str] = {
    "AA": "ɑː", "AE": "æ", "AH": "ʌ", "AO": "ɔː", "AW": "aʊ", "AY": "aɪ",
    "EH": "ɛ", "ER": "ɜː", "EY": "eɪ", "IH": "ɪ", "IY": "iː", "OW": "oʊ",
    "OY": "ɔɪ", "UH": "ʊ", "UW": "uː",
    "B": "b", "CH": "tʃ", "D": "d", "DH": "ð", "F": "f", "G": "ɡ", "HH": "h",
    "JH": "dʒ", "K": "k", "L": "l", "M": "m", "N": "n", "NG": "ŋ", "P": "p",
    "R": "ɹ", "S": "s", "SH": "ʃ", "T": "t", "TH": "θ", "V": "v", "W": "w",
    "Y": "j", "Z": "z", "ZH": "ʒ",
}
# Unstressed variants as espeak writes them.
ARPA_UNSTRESSED: dict[str, str] = {"AH": "ə", "ER": "ɚ", "IH": "ɪ"}

# Realisations that a native en-US speaker produces and that must NOT be
# counted as errors (flapping, vowel reduction, rhotic variants...).
# Key: canonical token; value: tokens accepted as the same phone.
ACCEPTED_VARIANTS: dict[str, tuple[str, ...]] = {
    "t": ("ɾ", "ʔ"),
    "d": ("ɾ",),
    "ə": ("ʌ", "ɐ", "ᵻ", "ɪ"),
    "ʌ": ("ə", "ɐ"),
    "ɪ": ("ᵻ", "ə", "i"),
    "ᵻ": ("ɪ", "ə"),
    "ɚ": ("ɜː", "ə", "ɹ"),
    "ɜː": ("ɚ", "ɝ"),
    "ɑː": ("ɑ", "ɔː", "a"),
    "ɔː": ("ɑː", "ɔ"),
    "iː": ("i",),
    "uː": ("u",),
    "oʊ": ("o",),
    "eɪ": ("e",),
    "ɹ": ("r",),
    "l": ("əl", "ɫ"),
    "əl": ("l",),
    "ɡ": ("g",),
    "i": ("iː", "ɪ"),
}

# Weak (reduced) forms of high-frequency function words. Native speakers say
# "to" as /tə/, "and" as /ən/, "for" as /fɚ/; per-word espeak and dictionary
# (ARPAbet) pronunciations give the strong form, so without this the reduced
# form would be flagged as a mispronunciation. Key: word; value: canonical
# token -> extra tokens accepted at that position (None = may be dropped).
WEAK_FORMS: dict[str, dict[str, tuple[str | None, ...]]] = {
    "to": {"uː": ("ə", "ʊ", "u", "ɪ")},
    "the": {"ə": ("iː", "ɪ", "i", "ʌ"), "ʌ": ("ə", "iː", "ɪ", "i"), "iː": ("ɪ", "i", "ə")},
    "a": {"eɪ": ("ə", "ʌ", "ɐ"), "ə": ("eɪ", "ʌ", "ɐ"), "ʌ": ("ə", "eɪ", "ɐ")},
    "an": {"æ": ("ə", "ʌ", "ɐ", "ɪ")},
    "of": {"ʌ": ("ə", "ɐ"), "ɑː": ("ə", "ʌ")},
    "and": {"æ": ("ə", "ɛ", "ɪ", "ɐ"), "d": (None,)},
    "for": {"ɔː": ("ə", "ɚ", "ɜː", None)},   # /fɚ/, /fɹ/
}


def weak_form_variants(prons: "list[WordPron]") -> dict[int, tuple[str | None, ...]]:
    """Flat phone index -> extra accepted realisations, for ``score_phones``."""
    out: dict[int, tuple[str | None, ...]] = {}
    i = 0
    for wp in prons:
        rules = WEAK_FORMS.get(wp.text.lower())
        if rules:
            for k, p in enumerate(wp.phones):
                if p in rules:
                    out[i + k] = rules[p]
        i += len(wp.phones)
    return out


VOWELS = {
    "ɑː", "æ", "ʌ", "ɔː", "aʊ", "aɪ", "ɛ", "ɜː", "eɪ", "ɪ", "iː", "oʊ", "ɔɪ",
    "ʊ", "uː", "ə", "ɚ", "ᵻ", "i", "u", "ɐ", "ɑ", "ɔ", "o", "e", "a", "əl",
    "ɑːɹ", "ɔːɹ", "ɪɹ", "ɛɹ", "ʊɹ", "oːɹ", "aɪɚ", "aɪə",
}

_STRESS_RE = re.compile(r"[ˈˌ]")
_ESPEAK_SPLIT = re.compile(r"\s+")
_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’-]*")

# espeak rhotic vowel digraphs are single tokens in the model vocab; for
# scoring we split them into vowel + ɹ so they line up with ARPAbet.
SPLIT_RHOTIC = {"ɑːɹ": ("ɑː", "ɹ"), "ɔːɹ": ("ɔː", "ɹ"), "ɪɹ": ("ɪ", "ɹ"),
                "ɛɹ": ("ɛ", "ɹ"), "ʊɹ": ("ʊ", "ɹ"), "oːɹ": ("oː", "ɹ"),
                "aɪɚ": ("aɪ", "ɚ"), "aɪə": ("aɪ", "ə"), "əl": ("ə", "l")}


def is_vowel(tok: str) -> bool:
    return tok in VOWELS


def arpa_to_ipa(ph: str) -> str:
    """'AH0' -> 'ə', 'AH1' -> 'ʌ', 'T' -> 't'. Unknown symbols raise KeyError."""
    m = re.match(r"^([A-Z]+)([0-2])?$", ph.strip().upper())
    if not m:
        raise KeyError(ph)
    base, stress = m.group(1), m.group(2)
    if stress == "0" and base in ARPA_UNSTRESSED:
        return ARPA_UNSTRESSED[base]
    return ARPA_TO_IPA[base]


def arpa_stress(ph: str) -> int | None:
    m = re.match(r"^[A-Z]+([0-2])$", ph.strip().upper())
    return int(m.group(1)) if m else None


@dataclass
class WordPron:
    text: str
    phones: list[str]
    stress: list[int | None] = field(default_factory=list)  # per phone, vowels only


def tokenize_ipa(ipa: str, vocab: set[str]) -> list[str]:
    """Greedy longest-match split of an IPA string into model tokens."""
    s = _STRESS_RE.sub("", ipa).replace("ː", "ː")
    out: list[str] = []
    i = 0
    maxlen = max((len(v) for v in vocab), default=1)
    while i < len(s):
        if s[i].isspace() or s[i] in "-_.'":
            i += 1
            continue
        for n in range(min(maxlen, len(s) - i), 0, -1):
            piece = s[i:i + n]
            if piece in vocab:
                out.append(piece)
                i += n
                break
        else:
            i += 1  # symbol the model does not know: drop it
    return out


def _espeak_available() -> bool:
    return shutil.which("espeak-ng") is not None or shutil.which("espeak") is not None


@functools.lru_cache(maxsize=4096)
def _espeak_word(word: str, voice: str = "en-us") -> str:
    exe = shutil.which("espeak-ng") or shutil.which("espeak")
    if not exe:
        raise RuntimeError("espeak-ng is not installed (apt-get install espeak-ng)")
    out = subprocess.run([exe, "-q", "--ipa", "-v", voice, word],
                         capture_output=True, text=True, check=True).stdout
    return out.strip()


def words_of(text: str) -> list[str]:
    return [w.replace("’", "'") for w in _WORD_RE.findall(text or "")]


def g2p_words(text: str, vocab: set[str], voice: str = "en-us") -> list[WordPron]:
    """Phonemise each word of ``text`` with espeak-ng and split into model tokens.

    Stress marks from espeak (placed right before the vowel) are kept per
    vowel: 1 primary, 2 secondary, 0 none.
    """
    prons: list[WordPron] = []
    maxlen = max((len(v) for v in vocab), default=1)
    for w in words_of(text):
        raw = _espeak_word(w.lower(), voice).replace("_", "")
        phones: list[str] = []
        stress: list[int | None] = []
        pending = 0
        i = 0
        while i < len(raw):
            ch = raw[i]
            if ch in "ˈˌ":
                pending = 1 if ch == "ˈ" else 2
                i += 1
                continue
            for n in range(min(maxlen, len(raw) - i), 0, -1):
                piece = raw[i:i + n]
                if piece in vocab and not any(c in "ˈˌ" for c in piece):
                    break
            else:
                i += 1
                continue
            i += n
            for t in SPLIT_RHOTIC.get(piece, (piece,)):
                phones.append(t)
                if is_vowel(t):
                    stress.append(pending)
                    pending = 0
                else:
                    stress.append(None)
        if phones:
            prons.append(WordPron(w, phones, stress))
    return prons


def arpa_words(words: list[tuple[str, list[str]]]) -> list[WordPron]:
    """Build WordPron objects from (word, [ARPAbet phones]) pairs."""
    out = []
    for w, phs in words:
        phones = [arpa_to_ipa(p) for p in phs]
        stress = [arpa_stress(p) if is_vowel(arpa_to_ipa(p)) else None for p in phs]
        out.append(WordPron(w, phones, stress))
    return out
