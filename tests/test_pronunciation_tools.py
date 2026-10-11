"""assess_pronunciation + start_pair_drill over real Streamable HTTP, plus the l1-vi skill wiring.

The scorer is swapped for a recorded result here (no weights, no torch); the real-model
path is covered by the slow test at the bottom (``pytest -m slow``).
"""
import base64
import io
import json
import os
import shutil
import wave
from pathlib import Path

import pytest
import yaml

from speakloop import pronunciation as pr
from speakloop.skillpacks import discover_packs, validate_pack_dir
from test_mcp_http import rpc

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_WAV = ROOT / "tests" / "fixtures" / "espeak_she_walked.wav"
needs_espeak = pytest.mark.skipif(not (shutil.which("espeak-ng") or shutil.which("espeak")),
                                  reason="espeak-ng not installed")


def call(url, name, args):
    return rpc(url, "tools/call", {"name": name, "arguments": args})["result"]


def _ph(ipa, expected, wi, score, err=None, start=0.0):
    return {"ipa": ipa, "expected": expected, "word_index": wi, "start": start, "end": start + 0.05,
            "score": score, "gop": 0.0, "error_type": err}


# What speakloop.phoneme.assess returns for "She walked." with the final /t/ dropped.
FAKE = {
    "phones": [_ph("ʃ", "ʃ", 0, 95.0), _ph("iː", "iː", 0, 92.0), _ph("w", "w", 1, 90.0), _ph("ɔː", "ɔː", 1, 88.0),
               _ph("k", "k", 1, 85.0), _ph(None, "t", 1, 6.0, "deletion")],
    "words": [{"word": "She", "expected_ipa": "ʃiː", "heard_ipa": "ʃiː", "phone_indices": [0, 1], "start": 0.0,
               "end": 0.1, "score": 93.5, "errors": 0},
              {"word": "walked", "expected_ipa": "wɔːkt", "heard_ipa": "wɔːk", "phone_indices": [2, 3, 4, 5],
               "start": 0.1, "end": 0.3, "score": 67.2, "errors": 1}],
    "l1_findings": [{"rule_id": "VN-ED-DROP", "category": "endings", "description_en": "The past-tense -ed ending was dropped.",
                     "description_vi": "Bạn bỏ mất đuôi -ed (thì quá khứ).", "tip_en": "Finish the word.", "tip_vi": "",
                     "word": "walked", "word_index": 1, "position": "word_final", "phone_index": 5, "expected": "t",
                     "heard": None, "start": 0.25, "end": 0.3, "experimental": False, "sound_id": "ed_t_after_voiceless"}],
    "overall": {"accuracy": 76.0, "phones": 6, "phones_flagged": 1, "phone_error_rate": 0.167, "words": 2,
                "words_with_errors": 1, "findings": 1, "threshold": 0.0, "model": "fake", "audio_seconds": 0.4,
                "latency_ms": {"total": 1}},
}


def _wav_b64(seconds=0.2, sr=16000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(b"\x00\x00" * int(seconds * sr))
    return base64.b64encode(buf.getvalue()).decode()


@pytest.fixture
def fake_scorer():
    seen = {}

    def fake(audio, text):
        seen["audio"], seen["text"] = audio, text
        return json.loads(json.dumps(FAKE))

    pr._assess_impl = fake
    yield seen
    pr._assess_impl = None


# ---------------------------------------------------------------- skill reconciliation
def test_one_canonical_vietnamese_pack():
    skills = ROOT / "skills"
    assert not (skills / "speakloop-l1-vietnamese").exists()
    assert validate_pack_dir(skills / "l1-vi") == []
    assert (skills / "l1-vi" / "rules.yaml").is_file()
    assert "vi" in discover_packs()


def test_every_rule_sound_is_a_pack_node():
    pack = discover_packs()["vi"]
    rules = yaml.safe_load((ROOT / "skills" / "l1-vi" / "rules.yaml").read_text(encoding="utf-8"))["rules"]
    linked = 0
    for r in rules:
        s = r.get("sound")
        for sid in (s.values() if isinstance(s, dict) else [s] if s else []):
            assert pack.sound(sid), f"{r['id']} links unknown sound {sid}"
            linked += 1
    assert linked >= 8


def test_rules_default_path_is_l1_vi():
    from speakloop.phoneme.rules import DEFAULT_RULES, load_rules

    assert DEFAULT_RULES.parent.name == "l1-vi"
    ed = next(r for r in load_rules() if r.id == "VN-ED-DROP")
    assert ed.sound_for("t") == "ed_t_after_voiceless" and ed.sound_for("d") == "ed_d_after_voiced"


# ---------------------------------------------------------------- unit: audio + shaping
def test_decode_audio_wav_passthrough_and_raw_pcm():
    wav = pr.decode_audio(_wav_b64())
    assert wav[:4] == b"RIFF"
    raw = base64.b64encode(b"\x01\x00" * 1600).decode()
    out = pr.decode_audio(raw, 16000)
    with wave.open(io.BytesIO(out)) as w:
        assert w.getframerate() == 16000 and w.getnframes() == 1600
    assert pr.decode_audio("data:audio/wav;base64," + _wav_b64())[:4] == b"RIFF"


@pytest.mark.parametrize("bad,sr,msg", [("", None, "empty"), (base64.b64encode(b"xx").decode(), None, "sample_rate")])
def test_decode_audio_rejects(bad, sr, msg):
    with pytest.raises(ValueError, match=msg):
        pr.decode_audio(bad, sr)


def test_decode_audio_too_long():
    with pytest.raises(ValueError, match="max"):
        pr.decode_audio(_wav_b64(seconds=31))


def test_to_card_matches_ui_shape():
    card = pr.to_card(FAKE, "She walked.")
    assert card["words"][1]["phone_range"] == [2, 6]
    assert card["phones"][5] == {"ipa": None, "expected": "t", "start": 0.0, "end": 0.05, "score": 0.06, "error_type": "deletion"}
    assert card["l1_findings"][0]["position"] == 5
    assert card["overall"]["score"] == 0.76 and card["overall"]["phones_correct"] == 5


def test_phone_errors_classify_into_sound_graph():
    (e,) = pr.phone_errors(FAKE)
    assert e["op"] == "delete" and e["target"] == "t" and e["position"] == "coda"
    assert e["prev"] == "k" and e["morpheme"] == "-ed" and e["sound_id"] == "ed_t_after_voiceless"


# ---------------------------------------------------------------- MCP over HTTP
def test_tools_listed_with_schema(server_url):
    tools = {t["name"]: t for t in rpc(server_url, "tools/list")["result"]["tools"]}
    a = tools["assess_pronunciation"]["inputSchema"]
    assert set(a["required"]) == {"reference_text", "audio_wav_base64"}
    assert {"sample_rate", "learner_id", "l1"} <= set(a["properties"])
    d = tools["start_pair_drill"]["inputSchema"]["properties"]
    assert {"focus", "node", "learner_id"} <= set(d)
    assert tools["start_pair_drill"]["annotations"]["readOnlyHint"] is True
    assert tools["assess_pronunciation"]["_meta"]["ui"]["resourceUri"] == "ui://speakloop/card.html"


def test_assess_pronunciation_end_to_end(server_url, fake_scorer):
    res = call(server_url, "assess_pronunciation", {"reference_text": "She walked.", "audio_wav_base64": _wav_b64(),
                                                    "sample_rate": 16000, "learner_id": "pr1"})
    assert not res.get("isError"), res
    sc = res["structuredContent"]
    assert sc["kind"] == "assessment" and fake_scorer["text"] == "She walked." and fake_scorer["audio"][:4] == b"RIFF"
    assert sc["l1_findings"][0]["rule_id"] == "VN-ED-DROP"
    assert sc["sound_graph_update"]["recorded"][0]["sound_id"] == "ed_t_after_voiceless"
    assert res["content"][0]["text"].startswith("The past-tense -ed ending was dropped.")
    weak = call(server_url, "get_weak_sounds", {"learner_id": "pr1"})["structuredContent"]
    assert weak["weak_sounds"][0]["sound_id"] == "ed_t_after_voiceless"


def test_assess_pronunciation_bad_audio_is_tool_error(server_url, fake_scorer):
    res = call(server_url, "assess_pronunciation", {"reference_text": "Hi", "audio_wav_base64": base64.b64encode(b"nope").decode()})
    assert res["isError"] is True and "sample_rate" in res["content"][0]["text"]


def test_assess_pronunciation_engine_missing_is_tool_error(server_url, monkeypatch):
    def boom(*a, **k):
        raise pr.PhonemeEngineUnavailable("The phoneme engine is not installed on this server (torch).")

    monkeypatch.setattr(pr, "_scorer", lambda: boom)
    res = call(server_url, "assess_pronunciation", {"reference_text": "Hi", "audio_wav_base64": _wav_b64()})
    assert res["isError"] is True and "not installed" in res["content"][0]["text"]


@needs_espeak
def test_start_pair_drill_from_finding(server_url):
    sc = call(server_url, "start_pair_drill", {"learner_id": "pd1", "focus": "VN-ED-DROP"})["structuredContent"]
    assert sc["kind"] == "pair_drill" and sc["sound_id"] == "ed_t_after_voiceless" and sc["reason"] == "finding"
    a, b = sc["pair"]["a"], sc["pair"]["b"]
    assert (b["word"], a["word"]) == ("walked", "walk") and sc["pair"]["say"] == "b"
    assert b["ipa"][-1] == "t" and b["diff"] == [len(b["ipa"]) - 1] and a["diff"] == []
    assert sc["speech"].startswith("Let's practise")


@needs_espeak
def test_start_pair_drill_th_substitution_diff():
    from speakloop.memory import SoundGraph

    d = pr.build_pair_drill(SoundGraph(":memory:"), "x", node="th_voiceless")
    assert (d["pair"]["b"]["word"], d["pair"]["a"]["word"]) == ("think", "tink")
    assert d["pair"]["b"]["diff"] == [0] and d["pair"]["a"]["diff"] == [0]


def test_start_pair_drill_defaults_to_due_sound_and_errors(server_url):
    sc = call(server_url, "start_pair_drill", {"learner_id": "pd2"})["structuredContent"]
    assert sc["kind"] == "pair_drill" and sc["reason"] == "new" and len(sc["pairs"]) >= 2
    assert call(server_url, "start_pair_drill", {"learner_id": "pd2", "node": "nope"})["isError"] is True
    assert call(server_url, "start_pair_drill", {"learner_id": "pd2", "focus": "VN-N-L"})["isError"] is True


# ---------------------------------------------------------------- real model (slow)
@pytest.mark.slow
@needs_espeak
def test_assess_pronunciation_real_model():
    pytest.importorskip("torch")
    pytest.importorskip("transformers")
    from speakloop.memory import SoundGraph
    from mcp.server.mcpserver import MCPServer

    srv = MCPServer(name="t")
    pr.register(srv, SoundGraph(":memory:"))
    b64 = base64.b64encode(FIXTURE_WAV.read_bytes()).decode()
    wav = pr.decode_audio(b64)
    card = pr.to_card(pr._scorer()(wav, "She walked to the shops."), "She walked to the shops.")
    assert [w["word"] for w in card["words"]][:2] == ["She", "walked"]
    assert card["overall"]["phones_total"] > 10 and 0 <= card["overall"]["score"] <= 1
