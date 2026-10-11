"""Sound Graph MCP tools over real Streamable HTTP (the same harness as test_mcp_http)."""
import json

from speakloop.skillpacks import discover_packs
from test_mcp_http import rpc

MEMORY_TOOLS = ("get_weak_sounds", "next_drill", "record_attempt", "progress_summary")


def call(url, name, args):
    return rpc(url, "tools/call", {"name": name, "arguments": args})["result"]


def test_memory_tools_listed_with_l1_enum(server_url):
    tools = {t["name"]: t for t in rpc(server_url, "tools/list")["result"]["tools"]}
    installed = sorted(discover_packs())
    for name in MEMORY_TOOLS:
        assert name in tools
        l1 = tools[name]["inputSchema"]["properties"]["l1"]
        assert l1["enum"] == installed, f"{name}.l1 must be an enum of installed packs"
        assert l1["default"] == "vi"
    assert tools["get_weak_sounds"]["annotations"]["readOnlyHint"] is True
    assert "\"maximum\": 1" in json.dumps(tools["record_attempt"]["inputSchema"]["properties"]["score"])


def test_unknown_l1_is_rejected_as_tool_error(server_url):
    res = call(server_url, "next_drill", {"learner_id": "m1", "l1": "vietnamese"})
    assert res["isError"] is True


def test_record_then_drill_weak_and_summary(server_url):
    lid = "mem-http"
    d0 = call(server_url, "next_drill", {"learner_id": lid})["structuredContent"]
    assert d0["kind"] == "sound_drill" and d0["reason"] == "new"
    rec = call(server_url, "record_attempt", {"learner_id": lid, "word": "walked", "errors": [
        {"op": "delete", "target": "t", "position": "coda", "prev": "k", "morpheme": "-ed"}]})
    sc = rec["structuredContent"]
    assert sc["kind"] == "attempt_recorded" and sc["recorded"][0]["sound_id"] == "ed_t_after_voiceless"
    assert rec["content"][0]["text"].startswith("Noted:")
    payload = json.loads(rec["content"][0]["text"].split("\n\n", 1)[1])
    assert "speech" not in payload and payload["recorded"]
    weak = call(server_url, "get_weak_sounds", {"learner_id": lid, "limit": 2})["structuredContent"]
    assert weak["weak_sounds"][0]["sound_id"] == "ed_t_after_voiceless"
    ok = call(server_url, "record_attempt", {"learner_id": lid, "sound_id": "plural_s", "correct": True, "score": 0.9})
    assert ok["structuredContent"]["recorded"][0]["correct"] is True and "clear" in ok["content"][0]["text"]
    summ = call(server_url, "progress_summary", {"learner_id": lid, "days": 7})["structuredContent"]
    assert summ["kind"] == "sound_progress" and summ["attempts"] == 2 and summ["sounds_tracked"] == 2


def test_record_attempt_bad_input_is_tool_error(server_url):
    assert call(server_url, "record_attempt", {"learner_id": "m2", "sound_id": "nope", "correct": True})["isError"] is True
    assert call(server_url, "record_attempt", {"learner_id": "m2", "sound_id": "plural_s"})["isError"] is True
    assert call(server_url, "record_attempt", {"learner_id": "m2", "sound_id": "plural_s", "correct": True, "score": 2})["isError"] is True
    nothing = call(server_url, "record_attempt", {"learner_id": "m2"})
    assert nothing["structuredContent"]["recorded"] == [] and "Nothing" in nothing["content"][0]["text"]


def test_pack_skill_resources(server_url):
    uris = {r["uri"] for r in rpc(server_url, "resources/list")["result"]["resources"]}
    assert {"skill://l1-vi/SKILL.md", "skill://l1-vi/pack.json"} <= uris
    md = rpc(server_url, "resources/read", {"uri": "skill://l1-vi/SKILL.md"})["result"]["contents"][0]
    assert md["text"].startswith("---") and "name: l1-vi" in md["text"]
    pj = rpc(server_url, "resources/read", {"uri": "skill://l1-vi/pack.json"})["result"]["contents"][0]
    assert json.loads(pj["text"])["id"] == "l1-vi"


def test_l1_type_helper():
    from typing import get_args

    from speakloop.memory_tools import l1_type

    t, default = l1_type(["ja", "vi"])
    assert default == "vi"
    lit, field = get_args(t)
    assert get_args(lit) == ("ja", "vi") and field.json_schema_extra == {"enum": ["ja", "vi"]}
    _, default = l1_type(["ko"])
    assert default == "ko"
    t, _ = l1_type([])
    assert get_args(t)[0] is str
