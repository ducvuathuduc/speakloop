"""End-to-end over real Streamable HTTP, exactly as the browser simulator talks to the server."""
import asyncio
import json

import httpx

HEADERS = {"content-type": "application/json", "accept": "application/json, text/event-stream"}


def rpc(url, method, params=None, id_=1, version="2025-11-25"):
    h = dict(HEADERS)
    if method != "initialize":
        h["mcp-protocol-version"] = version
    r = httpx.post(url + "/mcp", headers=h, json={"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}}, timeout=10)
    r.raise_for_status()
    if r.headers["content-type"].startswith("text/event-stream"):
        data = [l[5:].strip() for l in r.text.splitlines() if l.startswith("data:")]
        return json.loads(data[-1])
    return r.json()


def test_initialize_negotiates_2025_11_25(server_url):
    res = rpc(server_url, "initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                          "clientInfo": {"name": "pytest", "version": "1"}})["result"]
    assert res["protocolVersion"] == "2025-11-25"
    assert res["serverInfo"]["name"] == "speakloop"
    assert "tools" in res["capabilities"] and "resources" in res["capabilities"]


def test_tools_have_mcp_app_meta(server_url):
    tools = rpc(server_url, "tools/list")["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {"get_learner_profile", "set_goal", "plan_today_session", "start_drill", "submit_attempt",
            "start_sound_review", "progress_report", "explain_sound", "set_practice_routine"} <= names
    drill = next(t for t in tools if t["name"] == "start_drill")
    assert drill["_meta"]["ui"]["resourceUri"] == "ui://speakloop/card.html"


def test_resources_app_and_skill(server_url):
    res = rpc(server_url, "resources/list")["result"]["resources"]
    uris = {r["uri"]: r for r in res}
    assert uris["ui://speakloop/card.html"]["mimeType"] == "text/html;profile=mcp-app"
    card = rpc(server_url, "resources/read", {"uri": "ui://speakloop/card.html"})["result"]["contents"][0]
    assert "ui/initialize" in card["text"]
    skill = rpc(server_url, "resources/read", {"uri": "skill://speakloop-coach/SKILL.md"})["result"]["contents"][0]
    assert skill["text"].startswith("---\nname: speakloop-coach")


def test_drill_roundtrip_over_http(server_url):
    sc = rpc(server_url, "tools/call", {"name": "start_drill", "arguments": {"learner_id": "http", "task_type": "repeat_sentence"}})["result"]["structuredContent"]
    assert sc["kind"] == "drill" and sc["speak_text"]
    res = rpc(server_url, "tools/call", {"name": "submit_attempt", "arguments": {
        "learner_id": "http", "drill_id": sc["drill_id"], "transcript": sc["speak_text"], "duration_seconds": 3}})["result"]
    assert res["structuredContent"]["kind"] == "result"
    assert res["structuredContent"]["score"]["content"] == 90
    assert "overall" in res["content"][0]["text"]


def test_error_is_tool_error_not_crash(server_url):
    res = rpc(server_url, "tools/call", {"name": "submit_attempt", "arguments": {"learner_id": "x", "drill_id": "bad", "transcript": "hi"}})["result"]
    assert res["isError"] is True


def test_official_sdk_client(server_url):
    from mcp import Client

    async def go():
        async with Client(server_url + "/mcp") as c:
            tools = await c.list_tools()
            assert any(t.name == "progress_report" for t in tools.tools)
            r = await c.call_tool("get_learner_profile", {"learner_id": "sdk", "name": "SDK"})
            return r
    r = asyncio.run(go())
    assert r.structured_content["kind"] == "profile"


def test_simulator_page_and_planner(server_url):
    assert "Alexa+ experience simulator" in httpx.get(server_url + "/").text
    assert "McpHttpClient" in httpx.get(server_url + "/web/mcp-client.js").text
    assert httpx.get(server_url + "/web/../speakloop/server.py").status_code == 404
    d = httpx.post(server_url + "/agent/step", json={"learner_id": "p", "messages": [{"role": "user", "content": "how am I doing"}]}).json()
    assert d["type"] == "tool_call" and d["name"] == "progress_report" and d["provider"] == "rules"


def test_routine_tool_and_calendar_route(server_url):
    sc = rpc(server_url, "tools/call", {"name": "set_practice_routine", "arguments": {"learner_id": "cal", "time_local": "07:15"}})["result"]["structuredContent"]
    assert sc["kind"] == "routine" and sc["calendar_url"].endswith("/calendar/cal.ics")
    r = httpx.get(server_url + "/calendar/cal.ics")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/calendar") and "BEGIN:VEVENT" in r.text
