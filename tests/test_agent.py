from datetime import date

from speakloop import agent


def test_parse_exam_date():
    today = date(2026, 10, 10)
    assert agent.parse_exam_date("my exam is on December 15", today) == "2026-12-15"
    assert agent.parse_exam_date("exam on 3rd of march", today) == "2027-03-03"
    assert agent.parse_exam_date("it's in 6 weeks", today) == "2026-11-21"
    assert agent.parse_exam_date("2027-01-05", today) == "2027-01-05"
    assert agent.parse_exam_date("let's practise", today) is None


def test_parse_target():
    assert agent.parse_target("I need a score of 65") == 65
    assert agent.parse_target("practise for 10 minutes") is None


def body(text, **state):
    return {"learner_id": "lan", "messages": [{"role": "user", "content": text}], "state": state}


def test_rules_routing():
    assert agent.rules_step(body("Hi"))["name"] == "get_learner_profile"
    d = agent.rules_step(body("My exam is on December 15 and I need a score of 65"))
    assert d["name"] == "set_goal" and d["arguments"]["target_score"] == 65
    d = agent.rules_step(body("Let's practise for 10 minutes"))
    assert d["name"] == "plan_today_session" and d["arguments"]["minutes"] == 10
    assert agent.rules_step(body("How am I doing?"))["name"] == "progress_report"
    assert agent.rules_step(body("review my words"))["name"] == "start_sound_review"
    steps = [{"tool": "start_drill", "task_type": "repeat_sentence", "focus": "th"}]
    d = agent.rules_step(body("yes", plan_steps=steps, step_index=0))
    assert d["arguments"] == {"learner_id": "lan", "task_type": "repeat_sentence", "focus": "th"}


def test_tool_result_is_spoken():
    b = {"messages": [{"role": "tool", "result": {"speech": "Good work — 72 overall."}}]}
    assert agent.rules_step(b) == {"type": "say", "text": "Good work — 72 overall."}


def test_guardrail_submits_verbatim():
    b = body("tree of the student ask for more time", active_drill_id="rs-02:abc")
    b["messages"][0]["duration_seconds"] = 3.1
    g = agent.guardrail(b)
    assert g["name"] == "submit_attempt"
    assert g["arguments"]["transcript"] == "tree of the student ask for more time"
    assert g["arguments"]["duration_seconds"] == 3.1
    assert agent.guardrail(body("stop", active_drill_id="x")) is None


def test_bedrock_message_mapping_and_stubbed_call():
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "tool_call": {"id": "t1", "name": "get_learner_profile", "arguments": {"learner_id": "lan"}}},
        {"role": "tool", "tool_call_id": "t1", "result": {"speech": "Hi Lan", "kind": "profile"}},
    ]
    out = agent.to_bedrock_messages(msgs)
    assert [m["role"] for m in out] == ["user", "assistant", "user"]
    assert out[2]["content"][0]["toolResult"]["toolUseId"] == "t1"

    class FakeBedrock:
        def converse(self, **kw):
            assert kw["toolConfig"]["tools"][0]["toolSpec"]["name"] == "start_drill"
            assert "speakloop" in kw["system"][0]["text"].lower()
            return {"output": {"message": {"content": [{"toolUse": {"toolUseId": "x", "name": "start_drill", "input": {"learner_id": "lan"}}}]}}}

    tools = [{"name": "start_drill", "description": "d", "inputSchema": {"type": "object"}}]
    d = agent.bedrock_step({"messages": msgs, "tools": tools, "skill": "# SpeakLoop coach", "learner_id": "lan"}, client=FakeBedrock())
    assert d == {"type": "tool_call", "id": "x", "name": "start_drill", "arguments": {"learner_id": "lan"}}


def test_schema_cleaning_for_nova():
    schema = {"type": "object", "title": "x", "properties": {"name": {"anyOf": [{"type": "string"}, {"type": "null"}], "default": None, "title": "Name"}}}
    assert agent._clean_schema(schema) == {"type": "object", "properties": {"name": {"type": "string"}}}


def test_bedrock_bearer_token_http_path(monkeypatch):
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "test-token")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.delenv("BEDROCK_MODEL_ID", raising=False)
    seen = {}

    class Resp:
        status_code = 200
        def json(self):
            return {"output": {"message": {"content": [{"text": "<thinking>plan</thinking>Hi Lan!"}]}}}

    def fake_post(url, json, timeout, headers):
        seen.update(url=url, headers=headers, body=json)
        return Resp()

    d = agent.bedrock_step({"messages": [{"role": "user", "content": "hi"}], "tools": [], "skill": "skill"}, http=fake_post)
    assert d == {"type": "say", "text": "Hi Lan!"}
    assert seen["url"] == "https://bedrock-runtime.us-east-1.amazonaws.com/model/amazon.nova-lite-v1%3A0/converse"
    assert seen["headers"]["Authorization"] == "Bearer test-token"
    assert seen["body"]["messages"][0]["content"][0]["text"] == "hi"


def test_llm_failure_falls_back_to_rules(monkeypatch):
    import asyncio
    monkeypatch.setenv("SPEAKLOOP_LLM", "bedrock")
    monkeypatch.setattr(agent, "bedrock_step", lambda body: (_ for _ in ()).throw(RuntimeError("no network")))
    d = asyncio.run(agent.step(body("how am I doing")))
    assert d["name"] == "progress_report" and d["provider"] == "bedrock→rules" and "no network" in d["reason"]


def test_llm_unknown_tool_is_rejected(monkeypatch):
    import asyncio
    monkeypatch.setenv("SPEAKLOOP_LLM", "bedrock")
    monkeypatch.setattr(agent, "bedrock_step", lambda body: {"type": "tool_call", "name": "rm_rf", "arguments": {}})
    b = body("hi"); b["tools"] = [{"name": "get_learner_profile"}]
    d = asyncio.run(agent.step(b))
    assert d["name"] == "get_learner_profile" and d["provider"] == "bedrock→rules"


def test_reminder_intent():
    d = agent.rules_step(body("Remind me every evening at 8:30 pm for 15 minutes"))
    assert d["name"] == "set_practice_routine" and d["arguments"]["time_local"] == "20:30" and d["arguments"]["minutes"] == 15


def test_bedrock_throttle_trips_circuit_breaker(monkeypatch):
    import asyncio
    monkeypatch.setenv("SPEAKLOOP_LLM", "bedrock")
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "t")
    monkeypatch.setattr(agent, "_throttled_until", 0.0)
    calls = {"n": 0}

    class Resp:
        status_code = 429
        text = '{"message":"Too many tokens per day, please wait before trying again."}'

    def fake_post(*a, **k):
        calls["n"] += 1
        return Resp()

    import httpx
    monkeypatch.setattr(httpx, "post", fake_post)
    d1 = asyncio.run(agent.step(body("how am I doing")))
    d2 = asyncio.run(agent.step(body("how am I doing")))
    assert d1["provider"] == d2["provider"] == "bedrock→rules"
    assert "quota" in d1["reason"] and "throttled" in d2["reason"]
    assert calls["n"] == 1  # second turn skipped the network call
    monkeypatch.setattr(agent, "_throttled_until", 0.0)
