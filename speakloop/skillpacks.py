"""L1 sound packs as installable Agent Skills.

A pack is a folder ``skills/l1-<code>/`` holding an Agent Skill ``SKILL.md`` (YAML front
matter with ``name`` and ``description``) plus a machine-readable ``pack.json``
(schema ``speakloop.l1-pack/v1``). Each sound in the pack is a node of the learner's
Sound Graph and carries phone-level ``detect`` rules, so a phoneme-alignment error such
as "deleted /t/ in the coda after a voiceless consonant, -ed morpheme" can be mapped onto
a teachable sound id ("ed_t_after_voiceless").

CLI:
    python -m speakloop.skillpacks validate skills/l1-vi
    python -m speakloop.skillpacks install skills/l1-vi [--dest DIR]
    python -m speakloop.skillpacks list [DIR]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SKILLS_DIR = ROOT / "skills"
SCHEMA = "speakloop.l1-pack/v1"

OPS = {"delete", "substitute", "insert"}
POSITIONS = {"onset", "coda", "nucleus", "any"}
CLASSES = {"voiceless", "voiced", "consonant", "vowel"}
ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,47}$")
PACK_ID_RE = re.compile(r"^l1-[a-z]{2,3}$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
IPA_IN_SPEECH = re.compile(r"[θðʃʒŋɹəɪʊæɑɔɛʌː/]")

VOICELESS = set("ptkfsθʃh") | {"tʃ"}
VOICED_CONS = set("bdgvzðʒmnlrɹwjŋ") | {"dʒ"}
VOWELS = set("aeiouæɑɒɔəɛɜɪʊʌ")


class PackError(ValueError):
    pass


@dataclass
class SoundPack:
    id: str
    l1: str
    version: str
    path: Path
    data: dict
    skill_meta: dict = field(default_factory=dict)

    @property
    def sounds(self) -> list[dict]:
        return self.data["sounds"]

    def sound(self, sound_id: str) -> dict | None:
        return next((s for s in self.sounds if s["id"] == sound_id), None)

    def sound_ids(self) -> list[str]:
        return [s["id"] for s in self.sounds]


# ---------------------------------------------------------------- SKILL.md front matter
def parse_front_matter(text: str) -> dict:
    """Minimal YAML front-matter reader (flat keys plus one nested ``metadata`` map).

    Kept dependency-free on purpose: packs must validate on a bare Python install.
    """
    if not text.startswith("---"):
        raise PackError("SKILL.md must start with a '---' front-matter block")
    try:
        _, block, _ = text.split("---", 2)
    except ValueError as exc:
        raise PackError("SKILL.md front matter is not closed with '---'") from exc
    out: dict[str, Any] = {}
    current: dict | None = None
    for raw in block.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indented = raw.startswith((" ", "\t"))
        key, sep, val = raw.strip().partition(":")
        if not sep:
            raise PackError(f"bad front-matter line: {raw!r}")
        val = val.strip().strip('"').strip("'")
        if indented and current is not None:
            current[key] = val
        elif val == "":
            current = out.setdefault(key, {})
        else:
            current = None
            out[key] = val
    return out


# ---------------------------------------------------------------- validation
def _phone_class(phone: str) -> str:
    if phone in VOICELESS:
        return "voiceless"
    if phone in VOICED_CONS:
        return "voiced"
    if phone and phone[0] in VOWELS:
        return "vowel"
    return "other"


def validate_pack_data(data: dict, *, allow_template: bool = False) -> list[str]:
    errs: list[str] = []

    def need(obj: dict, key: str, typ: type, where: str) -> Any:
        if key not in obj:
            errs.append(f"{where}: missing '{key}'")
            return None
        if not isinstance(obj[key], typ):
            errs.append(f"{where}: '{key}' must be {typ.__name__}")
            return None
        return obj[key]

    if not isinstance(data, dict):
        return ["pack.json must be a JSON object"]
    if data.get("schema") != SCHEMA:
        errs.append(f"schema must be '{SCHEMA}'")
    pid = need(data, "id", str, "pack")
    l1 = need(data, "l1", str, "pack")
    if pid and not PACK_ID_RE.match(pid):
        errs.append("pack: id must look like 'l1-<iso639 code>'")
    if pid and l1 and pid != f"l1-{l1}":
        errs.append(f"pack: id '{pid}' does not match l1 '{l1}'")
    if not allow_template and l1 in ("xx", "xxx"):
        errs.append("pack: l1 is still the template placeholder 'xx'")
    ver = need(data, "version", str, "pack")
    if ver and not SEMVER_RE.match(ver):
        errs.append("pack: version must be semver X.Y.Z")
    need(data, "l1_name", str, "pack")
    srcs = need(data, "sources", list, "pack")
    if srcs is not None and not srcs:
        errs.append("pack: cite at least one source")
    sounds = need(data, "sounds", list, "pack") or []
    if not sounds:
        errs.append("pack: needs at least one sound")
    seen: set[str] = set()
    for i, s in enumerate(sounds):
        where = f"sounds[{i}]"
        if not isinstance(s, dict):
            errs.append(f"{where}: must be an object")
            continue
        sid = need(s, "id", str, where)
        if sid:
            where = f"sound '{sid}'"
            if not ID_RE.match(sid):
                errs.append(f"{where}: id must be snake_case, 2-48 chars")
            if sid in seen:
                errs.append(f"{where}: duplicate id")
            seen.add(sid)
        for k in ("label", "ipa", "category", "why_l1", "tip_en", "tip_l1", "speech_hint"):
            v = need(s, k, str, where)
            if v is not None and not v.strip():
                errs.append(f"{where}: '{k}' is empty")
        hint = s.get("speech_hint") or ""
        if IPA_IN_SPEECH.search(hint):
            errs.append(f"{where}: speech_hint is read aloud and must not contain IPA symbols or slashes")
        rules = need(s, "detect", list, where) or []
        if not rules:
            errs.append(f"{where}: needs at least one detect rule")
        for j, r in enumerate(rules):
            rw = f"{where} detect[{j}]"
            if not isinstance(r, dict):
                errs.append(f"{rw}: must be an object")
                continue
            op = r.get("op")
            if op not in OPS:
                errs.append(f"{rw}: op must be one of {sorted(OPS)}")
            if op in ("delete", "substitute") and not r.get("target"):
                errs.append(f"{rw}: '{op}' needs a target phone")
            if op in ("substitute", "insert") and not r.get("realized"):
                errs.append(f"{rw}: '{op}' needs a realized phone")
            if r.get("position", "any") not in POSITIONS:
                errs.append(f"{rw}: position must be one of {sorted(POSITIONS)}")
            for ck in ("after_class", "before_class"):
                if ck in r and r[ck] not in CLASSES:
                    errs.append(f"{rw}: {ck} must be one of {sorted(CLASSES)}")
        drills = need(s, "drills", dict, where) or {}
        pairs = drills.get("minimal_pairs")
        if not isinstance(pairs, list) or len(pairs) < 2:
            errs.append(f"{where}: drills.minimal_pairs needs at least 2 pairs")
        else:
            for p in pairs:
                if not (isinstance(p, list) and len(p) == 2 and all(isinstance(w, str) and w for w in p)):
                    errs.append(f"{where}: each minimal pair must be [target, mishearing]")
                elif p[0].lower() == p[1].lower():
                    errs.append(f"{where}: minimal pair {p} has identical words")
        if not isinstance(drills.get("words"), list) or not drills.get("words"):
            errs.append(f"{where}: drills.words must be a non-empty list")
    return errs


def validate_pack_dir(path: str | Path, *, allow_template: bool = False) -> list[str]:
    p = Path(path)
    errs: list[str] = []
    skill_md, pack_json = p / "SKILL.md", p / "pack.json"
    if not skill_md.is_file():
        errs.append("missing SKILL.md")
    if not pack_json.is_file():
        errs.append("missing pack.json")
    if errs:
        return errs
    try:
        meta = parse_front_matter(skill_md.read_text(encoding="utf-8"))
    except PackError as exc:
        return [str(exc)]
    for k in ("name", "description"):
        if not meta.get(k):
            errs.append(f"SKILL.md: front matter needs '{k}'")
    if meta.get("name") and meta["name"] != p.name and not allow_template:
        errs.append(f"SKILL.md: name '{meta['name']}' must match folder name '{p.name}'")
    if len(meta.get("description", "")) > 1024:
        errs.append("SKILL.md: description must be at most 1024 characters")
    try:
        data = json.loads(pack_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return errs + [f"pack.json: invalid JSON ({exc})"]
    errs += validate_pack_data(data, allow_template=allow_template)
    if not allow_template and isinstance(data, dict) and data.get("id") and data["id"] != p.name:
        errs.append(f"pack.json: id '{data['id']}' must match folder name '{p.name}'")
    return errs


def load_pack(path: str | Path) -> SoundPack:
    p = Path(path)
    errs = validate_pack_dir(p)
    if errs:
        raise PackError(f"{p}: " + "; ".join(errs))
    data = json.loads((p / "pack.json").read_text(encoding="utf-8"))
    meta = parse_front_matter((p / "SKILL.md").read_text(encoding="utf-8"))
    return SoundPack(id=data["id"], l1=data["l1"], version=data["version"], path=p, data=data, skill_meta=meta)


def install_pack(src: str | Path, dest_dir: str | Path = DEFAULT_SKILLS_DIR, *, overwrite: bool = False) -> SoundPack:
    """Validate, then copy a pack folder into ``dest_dir/<pack id>``. Invalid packs are never installed."""
    pack = load_pack(src)
    target = Path(dest_dir) / pack.id
    if target.resolve() == Path(src).resolve():
        return pack
    if target.exists():
        if not overwrite:
            raise PackError(f"{target} already exists (use overwrite=True)")
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return load_pack(target)


def discover_packs(skills_dir: str | Path = DEFAULT_SKILLS_DIR) -> dict[str, SoundPack]:
    out: dict[str, SoundPack] = {}
    for d in sorted(Path(skills_dir).glob("l1-*")):
        if d.name == "l1-template" or not d.is_dir():
            continue
        try:
            pk = load_pack(d)
        except PackError:
            continue
        out[pk.l1] = pk
    return out


# ---------------------------------------------------------------- classification
def _rule_matches(rule: dict, err: dict) -> bool:
    if rule["op"] != err.get("op"):
        return False
    if rule.get("target") and rule["target"] != err.get("target"):
        return False
    if rule.get("realized") and rule["realized"] != err.get("realized"):
        return False
    pos = rule.get("position", "any")
    if pos != "any" and err.get("position") and pos != err["position"]:
        return False
    if pos != "any" and not err.get("position"):
        return False
    if rule.get("morpheme") and err.get("morpheme") and rule["morpheme"] != err["morpheme"]:
        return False
    if rule.get("morpheme") and not err.get("morpheme"):
        return False
    for ck, ek in (("after_class", "prev"), ("before_class", "next")):
        if ck in rule:
            ph = err.get(ek)
            if not ph:
                return False
            cls = _phone_class(ph)
            want = rule[ck]
            if want == "consonant":
                if cls not in ("voiceless", "voiced"):
                    return False
            elif cls != want:
                return False
    return True


def _specificity(rule: dict) -> int:
    return sum(1 for k in ("target", "realized", "morpheme", "after_class", "before_class") if rule.get(k)) + (
        rule.get("position", "any") != "any")


def classify_error(pack: SoundPack, err: dict) -> str | None:
    """Map one phone-level error to the most specific matching sound id.

    ``err`` keys: op (delete|substitute|insert), target, realized, position (onset|coda|nucleus),
    prev / next (neighbouring canonical phones), morpheme ("-ed" | "-s"), word.
    """
    best: tuple[int, str] | None = None
    for s in pack.sounds:
        for r in s["detect"]:
            if _rule_matches(r, err):
                sc = _specificity(r)
                if best is None or sc > best[0]:
                    best = (sc, s["id"])
    return best[1] if best else None


def classify_errors(pack: SoundPack, errors: list[dict]) -> list[dict]:
    return [{**e, "sound_id": classify_error(pack, e)} for e in errors]


# ---------------------------------------------------------------- CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m speakloop.skillpacks")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate"); v.add_argument("path"); v.add_argument("--template", action="store_true")
    i = sub.add_parser("install"); i.add_argument("path"); i.add_argument("--dest", default=str(DEFAULT_SKILLS_DIR))
    i.add_argument("--overwrite", action="store_true")
    ls = sub.add_parser("list"); ls.add_argument("dir", nargs="?", default=str(DEFAULT_SKILLS_DIR))
    a = ap.parse_args(argv)
    if a.cmd == "validate":
        errs = validate_pack_dir(a.path, allow_template=a.template)
        if errs:
            print(f"INVALID {a.path}"); [print("  -", e) for e in errs]
            return 1
        data = json.loads((Path(a.path) / "pack.json").read_text(encoding="utf-8"))
        print(f"OK {data['id']} v{data['version']}: {len(data['sounds'])} sounds")
        return 0
    if a.cmd == "install":
        try:
            pk = install_pack(a.path, a.dest, overwrite=a.overwrite)
        except PackError as exc:
            print(f"NOT INSTALLED: {exc}"); return 1
        print(f"installed {pk.id} v{pk.version} -> {pk.path}")
        return 0
    for l1, pk in discover_packs(a.dir).items():
        print(f"{pk.id}\tv{pk.version}\t{len(pk.sounds)} sounds\t{pk.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
