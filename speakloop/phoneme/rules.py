"""Data-driven L1 error rules (YAML), matched against phone-level events."""

from __future__ import annotations

import functools
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .g2p import is_vowel

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RULES = REPO_ROOT / "skills" / "speakloop-l1-vietnamese" / "rules.yaml"


@dataclass
class Event:
    """A phone-level event the scorer produced (error or stress mismatch)."""

    error_type: str  # deletion | substitution | insertion | stress
    word: str
    word_index: int
    phone_index: int | None  # index into the utterance phone list
    expected: str | None
    heard: str | None
    position: str  # word_final | word_initial | word_medial
    in_cluster: bool = False
    start: float | None = None
    end: float | None = None


@dataclass
class Rule:
    id: str
    category: str
    when: dict[str, Any]
    description_en: str
    description_vi: str
    tip_en: str = ""
    tip_vi: str = ""
    experimental: bool = False
    _re: Any = field(default=None, repr=False)
    _not_re: Any = field(default=None, repr=False)

    def matches(self, ev: Event) -> bool:
        w = self.when

        def inlist(key: str, value: Any) -> bool:
            if key not in w:
                return True
            allowed = w[key]
            if not isinstance(allowed, list):
                allowed = [allowed]
            return value in allowed

        if not inlist("error_type", ev.error_type):
            return False
        if not inlist("expected", ev.expected):
            return False
        if "heard" in w and not inlist("heard", ev.heard):
            return False
        if "position" in w and not inlist("position", ev.position):
            return False
        if "in_cluster" in w and bool(w["in_cluster"]) != ev.in_cluster:
            return False
        word = ev.word.lower()
        if self._re is not None and not self._re.search(word):
            return False
        if self._not_re is not None and self._not_re.search(word):
            return False
        return True


@functools.lru_cache(maxsize=8)
def load_rules(path: str | os.PathLike | None = None) -> tuple[Rule, ...]:
    p = Path(path or os.environ.get("SPEAKLOOP_L1_RULES", DEFAULT_RULES))
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    rules = []
    for r in data.get("rules", []):
        when = dict(r.get("when", {}))
        rule = Rule(
            id=r["id"], category=r.get("category", ""), when=when,
            description_en=r.get("description_en", ""), description_vi=r.get("description_vi", ""),
            tip_en=r.get("tip_en", ""), tip_vi=r.get("tip_vi", ""),
            experimental=bool(r.get("experimental", False)),
        )
        if "word_regex" in when:
            rule._re = re.compile(when.pop("word_regex"))
        if "not_word_regex" in when:
            rule._not_re = re.compile(when.pop("not_word_regex"))
        rules.append(rule)
    return tuple(rules)


def phone_position(word_phones: list[str], k: int) -> tuple[str, bool]:
    """Position label and cluster membership of phone k inside a word."""
    n = len(word_phones)
    if k == n - 1:
        pos = "word_final"
    elif k == 0:
        pos = "word_initial"
    else:
        pos = "word_medial"
    if is_vowel(word_phones[k]):
        return pos, False
    left = k > 0 and not is_vowel(word_phones[k - 1])
    right = k < n - 1 and not is_vowel(word_phones[k + 1])
    return pos, bool(left or right)


def apply_rules(events: list[Event], rules: tuple[Rule, ...]) -> list[dict]:
    findings = []
    for ev in events:
        for rule in rules:
            if rule.matches(ev):
                findings.append({
                    "rule_id": rule.id,
                    "category": rule.category,
                    "description_vi": rule.description_vi,
                    "description_en": rule.description_en,
                    "tip_vi": rule.tip_vi,
                    "tip_en": rule.tip_en,
                    "word": ev.word,
                    "word_index": ev.word_index,
                    "position": ev.position,
                    "phone_index": ev.phone_index,
                    "expected": ev.expected,
                    "heard": ev.heard,
                    "start": ev.start,
                    "end": ev.end,
                    "experimental": rule.experimental,
                })
                break
    return findings
