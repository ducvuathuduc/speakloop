"""L1 skill-pack validation, install, discovery and error classification."""
import copy
import json
import shutil

import pytest

from speakloop import skillpacks as sp

VI = sp.DEFAULT_SKILLS_DIR / "l1-vi"
TEMPLATE = sp.DEFAULT_SKILLS_DIR / "l1-template"


@pytest.fixture
def vi_data():
    return json.loads((VI / "pack.json").read_text(encoding="utf-8"))


def copy_pack(tmp_path, name="l1-vi", src=VI):
    dst = tmp_path / name
    shutil.copytree(src, dst)
    return dst


def test_shipped_vi_pack_is_valid():
    assert sp.validate_pack_dir(VI) == []
    pk = sp.load_pack(VI)
    assert pk.id == "l1-vi" and pk.l1 == "vi" and len(pk.sounds) >= 10
    assert pk.skill_meta["name"] == "l1-vi" and pk.skill_meta["description"]


def test_template_valid_only_as_template():
    assert sp.validate_pack_dir(TEMPLATE, allow_template=True) == []
    errs = sp.validate_pack_dir(TEMPLATE)
    assert any("placeholder" in e for e in errs)


@pytest.mark.parametrize("mutate,expect", [
    (lambda d: d.update(schema="v0"), "schema must be"),
    (lambda d: d.update(id="vi"), "id must look like"),
    (lambda d: d.update(l1="ja"), "does not match l1"),
    (lambda d: d.update(version="1.0"), "semver"),
    (lambda d: d.update(sources=[]), "cite at least one source"),
    (lambda d: d.update(sounds=[]), "at least one sound"),
    (lambda d: d["sounds"].append(copy.deepcopy(d["sounds"][0])), "duplicate id"),
    (lambda d: d["sounds"][0].update(id="Bad-Id"), "snake_case"),
    (lambda d: d["sounds"][0].update(tip_en="  "), "'tip_en' is empty"),
    (lambda d: d["sounds"][0].pop("tip_l1"), "missing 'tip_l1'"),
    (lambda d: d["sounds"][0].update(speech_hint="the /t/ sound"), "must not contain IPA"),
    (lambda d: d["sounds"][0].update(detect=[]), "at least one detect rule"),
    (lambda d: d["sounds"][0]["detect"][0].update(op="swap"), "op must be one of"),
    (lambda d: d["sounds"][0]["detect"][0].pop("target"), "needs a target phone"),
    (lambda d: d["sounds"][0]["detect"][0].update(op="substitute"), "needs a realized phone"),
    (lambda d: d["sounds"][0]["detect"][0].update(position="middle"), "position must be one of"),
    (lambda d: d["sounds"][0]["detect"][0].update(after_class="nasal"), "after_class must be one of"),
    (lambda d: d["sounds"][0]["drills"].update(minimal_pairs=[["a", "b"]]), "at least 2 pairs"),
    (lambda d: d["sounds"][0]["drills"].update(minimal_pairs=[["walk", "Walk"], ["a", "b"]]), "identical words"),
    (lambda d: d["sounds"][0]["drills"].update(minimal_pairs=[["walk"], ["a", "b"]]), "[target, mishearing]"),
    (lambda d: d["sounds"][0]["drills"].update(words=[]), "drills.words"),
])
def test_validation_catches(vi_data, mutate, expect):
    assert sp.validate_pack_data(vi_data) == []
    mutate(vi_data)
    errs = sp.validate_pack_data(vi_data)
    assert any(expect in e for e in errs), errs


def test_non_object_pack():
    assert sp.validate_pack_data([]) == ["pack.json must be a JSON object"]


def test_dir_level_checks(tmp_path):
    empty = tmp_path / "l1-zz"; empty.mkdir()
    assert sp.validate_pack_dir(empty) == ["missing SKILL.md", "missing pack.json"]
    p = copy_pack(tmp_path, "l1-ja")
    errs = sp.validate_pack_dir(p)
    assert any("must match folder name" in e for e in errs)
    p = copy_pack(tmp_path, "l1-vi")
    (p / "pack.json").write_text("{not json", encoding="utf-8")
    assert any("invalid JSON" in e for e in sp.validate_pack_dir(p))
    (p / "SKILL.md").write_text("no front matter", encoding="utf-8")
    assert sp.validate_pack_dir(p) == ["SKILL.md must start with a '---' front-matter block"]


def test_front_matter_parser():
    meta = sp.parse_front_matter('---\nname: l1-vi\ndescription: "Hi: there"\nmetadata:\n  version: 1.2.0\n  author: x\n---\nbody')
    assert meta == {"name": "l1-vi", "description": "Hi: there", "metadata": {"version": "1.2.0", "author": "x"}}
    with pytest.raises(sp.PackError):
        sp.parse_front_matter("---\nname l1-vi\n---\n")
    with pytest.raises(sp.PackError):
        sp.parse_front_matter("---\nname: x\n")
    long = "---\nname: l1-vi\ndescription: " + "x" * 1100 + "\n---\n"
    assert sp.parse_front_matter(long)["description"]


def test_install_refuses_invalid_and_existing(tmp_path, vi_data):
    dest = tmp_path / "installed"
    pk = sp.install_pack(VI, dest)
    assert pk.path == dest / "l1-vi" and sp.validate_pack_dir(pk.path) == []
    with pytest.raises(sp.PackError, match="already exists"):
        sp.install_pack(VI, dest)
    assert sp.install_pack(VI, dest, overwrite=True).id == "l1-vi"
    bad = copy_pack(tmp_path / "src", "l1-vi")
    vi_data["sounds"][0]["speech_hint"] = "θ"
    (bad / "pack.json").write_text(json.dumps(vi_data), encoding="utf-8")
    with pytest.raises(sp.PackError):
        sp.install_pack(bad, tmp_path / "other")
    assert not (tmp_path / "other" / "l1-vi").exists()


def test_discover_skips_template_and_invalid(tmp_path, vi_data):
    copy_pack(tmp_path, "l1-vi")
    copy_pack(tmp_path, "l1-template", TEMPLATE)
    bad = copy_pack(tmp_path, "l1-ja")  # folder/id mismatch -> invalid
    (bad / "pack.json").write_text(json.dumps(vi_data), encoding="utf-8")
    assert list(sp.discover_packs(tmp_path)) == ["vi"]
    assert sp.discover_packs(tmp_path / "nothing") == {}


@pytest.mark.parametrize("err,sid", [
    ({"op": "delete", "target": "t", "position": "coda", "prev": "k", "morpheme": "-ed"}, "ed_t_after_voiceless"),
    ({"op": "delete", "target": "d", "position": "coda", "prev": "v", "morpheme": "-ed"}, "ed_d_after_voiced"),
    ({"op": "substitute", "target": "d", "realized": "t", "position": "coda", "morpheme": "-ed"}, "ed_d_after_voiced"),
    ({"op": "delete", "target": "s", "position": "coda", "morpheme": "-s"}, "plural_s"),
    ({"op": "substitute", "target": "θ", "realized": "t", "position": "onset"}, "th_voiceless"),
    ({"op": "substitute", "target": "ð", "realized": "d"}, "th_voiced"),
    ({"op": "delete", "target": "t", "position": "coda", "prev": "k"}, None),  # no -ed morpheme -> not the -ed rule
    ({"op": "substitute", "target": "q", "realized": "x"}, None),
])
def test_classify_error(err, sid):
    pk = sp.load_pack(VI)
    got = sp.classify_error(pk, err)
    if sid is None:
        assert got != "ed_t_after_voiceless" if err.get("target") == "t" else got is None
    else:
        assert got == sid
    assert sp.classify_errors(pk, [err])[0]["sound_id"] == got


def test_phone_classes():
    assert sp._phone_class("k") == "voiceless" and sp._phone_class("v") == "voiced"
    assert sp._phone_class("æ") == "vowel" and sp._phone_class("?") == "other"


def test_cli(tmp_path, capsys):
    assert sp.main(["validate", str(VI)]) == 0 and "OK l1-vi" in capsys.readouterr().out
    assert sp.main(["validate", str(TEMPLATE)]) == 1 and "INVALID" in capsys.readouterr().out
    assert sp.main(["validate", "--template", str(TEMPLATE)]) == 0
    capsys.readouterr()
    assert sp.main(["install", str(VI), "--dest", str(tmp_path)]) == 0
    assert sp.main(["install", str(VI), "--dest", str(tmp_path)]) == 1 and "NOT INSTALLED" in capsys.readouterr().out
    assert sp.main(["list", str(tmp_path)]) == 0 and "l1-vi" in capsys.readouterr().out
