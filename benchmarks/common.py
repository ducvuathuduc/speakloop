"""Shared loaders for the SpeakLoop phoneme benchmarks.

Data locations (override with env vars):
  SPEAKLOOP_BENCH_DATA   root holding L2-ARCTIC speaker folders (HQTV/, PNV/, THV/, TLV/)
  SPEAKLOOP_BENCH_CACHE  where emissions / transcripts are cached
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

DATA = Path(os.environ.get("SPEAKLOOP_BENCH_DATA", "bench_data"))
CACHE = Path(os.environ.get("SPEAKLOOP_BENCH_CACHE", "bench_cache"))
VN_SPEAKERS = ["HQTV", "PNV", "THV", "TLV"]
DEV_SPEAKERS = ["HQTV", "PNV"]   # thresholds tuned here
TEST_SPEAKERS = ["THV", "TLV"]   # held out

_INTERVAL = re.compile(r'xmin = ([\d.]+)\s*\n\s*xmax = ([\d.]+)\s*\n\s*text = "(.*)"')


def read_textgrid(path: Path) -> dict[str, list[tuple[float, float, str]]]:
    txt = path.read_text(encoding="utf-8", errors="replace")
    tiers: dict[str, list[tuple[float, float, str]]] = {}
    for block in re.split(r'item \[\d+\]:', txt)[1:]:
        name = re.search(r'name = "(.*)"', block).group(1)
        tiers[name] = [(float(a), float(b), t) for a, b, t in _INTERVAL.findall(block)]
    return tiers


@dataclass
class AnnPhone:
    canonical: str          # ARPAbet with stress digit, e.g. 'AO1'
    perceived: str | None   # ARPAbet without stress, None for deletion
    kind: str               # correct | substitution | deletion
    start: float
    end: float


@dataclass
class AnnWord:
    text: str
    start: float
    end: float
    phones: list[AnnPhone] = field(default_factory=list)


@dataclass
class Utterance:
    speaker: str
    utt_id: str
    wav: Path
    transcript: str
    words: list[AnnWord]
    additions: int = 0

    @property
    def key(self) -> str:
        return f"{self.speaker}_{self.utt_id}"


def _base(p: str) -> str:
    return re.sub(r"\d", "", p.strip().upper())


def parse_phone_label(label: str) -> tuple[str | None, str | None, str]:
    """L2-ARCTIC label -> (canonical, perceived, kind).

    'AO1' correct; 'CPL,PPL,s' substitution; 'CPL,sil,d' deletion; 'sil,PPL,a' addition.
    """
    lab = label.strip().replace(" ", "")
    if not lab or lab.lower() in {"sil", "sp", "spn", ""}:
        return None, None, "silence"
    parts = lab.split(",")
    if len(parts) == 1:
        return parts[0].upper(), _base(parts[0]), "correct"
    cpl, ppl = parts[0].upper(), parts[1].upper()
    tag = parts[2].lower() if len(parts) > 2 else "s"
    if tag.startswith("a") or cpl in {"SIL", "SP", ""}:
        return None, ppl, "addition"
    if tag.startswith("d") or ppl in {"SIL", "SP", ""}:
        return cpl, None, "deletion"
    ppl = ppl.rstrip("*")
    return cpl, (None if ppl in {"ERR"} else _base(ppl)), "substitution"


def load_l2arctic(speakers: list[str] | None = None, root: Path | None = None) -> list[Utterance]:
    root = root or DATA
    utts = []
    for spk in speakers or VN_SPEAKERS:
        for tg in sorted((root / spk / "annotation").glob("*.TextGrid")):
            uid = tg.stem
            tiers = read_textgrid(tg)
            words = [AnnWord(t.lower(), a, b) for a, b, t in tiers.get("words", []) if t.strip() and t.strip().lower() not in {"sil", "sp"}]
            adds = 0
            for a, b, lab in tiers.get("phones", []):
                c, p, kind = parse_phone_label(lab)
                if kind == "silence":
                    continue
                if kind == "addition":
                    adds += 1
                    continue
                mid = (a + b) / 2
                owner = next((w for w in words if w.start - 1e-6 <= mid <= w.end + 1e-6), None)
                if owner is None:
                    continue
                if not re.match(r"^[A-Z]+[0-2]?$", c or ""):
                    continue
                owner.phones.append(AnnPhone(c, p, kind, a, b))
            words = [w for w in words if w.phones]
            tr = (root / spk / "transcript" / f"{uid}.txt")
            utts.append(Utterance(spk, uid, root / spk / "wav" / f"{uid}.wav",
                                  tr.read_text().strip() if tr.exists() else " ".join(w.text for w in words),
                                  words, adds))
    return utts
