"""Tiered planner: circuit breakers and fall-through, with mock models (no network, no strands needed)."""
import asyncio
import sys

import pytest

from speakloop import planner
from speakloop.planner import CircuitBreaker, InvalidDecision, TierUnavailable

BODY = {"learner_id": "t", "tools": [], "messages": [{"role": "user", "content": "how am I doing"}]}


class FakeClock:
    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


class ModelThrottledException(Exception):
    """Same class name as strands.types.exceptions.ModelThrottledException."""


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for k in ("SPEAKLOOP_BREAKER_FAILURES", "SPEAKLOOP_BREAKER_COOLDOWN_S", "SPEAKLOOP_THROTTLE_COOLDOWN_S"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SPEAKLOOP_TIERS", "bedrock,local,rules")
    planner.reset_breakers()
    yield
    planner.reset_breakers()


def run(**kw):
    return asyncio.run(planner.plan(BODY, **kw))


# ------------------------------------------------------------------ CircuitBreaker unit
def test_breaker_opens_after_threshold_and_half_opens():
    clk = FakeClock()
    br = CircuitBreaker("x", failure_threshold=2, cooldown_s=60, throttle_cooldown_s=600, clock=clk)
    assert br.allow() and br.state == "closed"
    br.record_failure("timeout")
    assert br.state == "closed" and br.allow()
    br.record_failure("timeout")
    assert br.state == "open" and not br.allow() and br.seconds_left() == 60
    clk.t += 59.9
    assert not br.allow()
    clk.t += 0.2
    assert br.allow() and br.state == "half_open"
    br.record_failure("still broken")  # one failed trial re-opens at once
    assert br.state == "open" and br.seconds_left() == 60


def test_breaker_throttle_opens_immediately_with_long_cooldown():
    clk = FakeClock()
    br = CircuitBreaker("x", failure_threshold=5, cooldown_s=60, throttle_cooldown_s=600, clock=clk)
    br.record_failure("429 Too many tokens per day", throttled=True)
    assert br.state == "open" and br.seconds_left() == 600
    snap = br.snapshot()
    assert snap["tier"] == "x" and snap["state"] == "open" and snap["retry_in_s"] == 600 and "429" in snap["last_error"]


def test_breaker_success_resets():
    clk = FakeClock()
    br = CircuitBreaker("x", failure_threshold=2, cooldown_s=10, clock=clk)
    br.record_failure("a"); br.record_failure("b")
    clk.t += 11
    assert br.allow() and br.state == "half_open"
    br.record_success()
    assert br.state == "closed" and br.failures == 0 and br.last_error is None and br.seconds_left() == 0


def test_breaker_env_config(monkeypatch):
    monkeypatch.setenv("SPEAKLOOP_BREAKER_FAILURES", "3")
    monkeypatch.setenv("SPEAKLOOP_BREAKER_COOLDOWN_S", "5")
    monkeypatch.setenv("SPEAKLOOP_THROTTLE_COOLDOWN_S", "not-a-number")
    br = planner.breaker("bedrock")
    assert (br.failure_threshold, br.cooldown_s, br.throttle_cooldown_s) == (3, 5.0, 600.0)
    assert planner.breaker("bedrock") is br


def test_is_throttle_detection():
    assert planner._is_throttle(ModelThrottledException("slow down"))
    assert planner._is_throttle(RuntimeError("HTTP 429"))
    assert planner._is_throttle(RuntimeError("Too many tokens per day, please wait"))
    assert not planner._is_throttle(TimeoutError("read timeout"))


def test_tiers_always_end_with_rules(monkeypatch):
    monkeypatch.setenv("SPEAKLOOP_TIERS", "local, bedrock")
    assert planner.tiers() == ["local", "bedrock", "rules"]
    monkeypatch.setenv("SPEAKLOOP_TIERS", "rules")
    assert planner.tiers() == ["rules"]


# ------------------------------------------------------------------ plan() fall-through with mock models
def factories(**models):
    def make(tier):
        def f():
            m = models[tier]
            if isinstance(m, BaseException):
                raise m
            return m
        return f
    return {t: make(t) for t in models}


def test_first_tier_success():
    out = run(factories=factories(bedrock="B", local="L"),
              decide=lambda body, m: {"type": "say", "text": f"from {m}"})
    assert out["provider"] == "strands:bedrock" and out["text"] == "from B"
    assert out["trace"][0]["tier"] == "bedrock" and out["trace"][0]["ok"]


def test_throttle_falls_to_local_and_skips_bedrock_next_turn():
    calls = []

    def decide(body, m):
        calls.append(m)
        if m == "B":
            raise ModelThrottledException("Too many tokens per day")
        return {"type": "tool_call", "id": "1", "name": "progress_report", "arguments": {"learner_id": "t"}}

    f = factories(bedrock="B", local="L")
    out = run(factories=f, decide=decide)
    assert out["provider"] == "strands:local" and out["name"] == "progress_report"
    assert out["trace"][0]["throttled"] is True
    assert planner.breaker("bedrock").state == "open" and planner.breaker("bedrock").seconds_left() > 500
    out2 = run(factories=f, decide=decide)
    assert calls == ["B", "L", "L"], "open bedrock breaker must be skipped without a call"
    assert out2["trace"][0]["skipped"].startswith("circuit open")


def test_generic_failures_open_after_threshold():
    def decide(body, m):
        raise InvalidDecision("model chose unknown tool 'x'")

    f = factories(bedrock="B", local="L")
    for _ in range(2):
        out = run(factories=f, decide=decide)
        assert out["provider"] == "bedrock→local→rules" and out["type"] == "tool_call"
        assert "unknown tool" in out["reason"]
    assert planner.breaker("bedrock").state == "open" and planner.breaker("local").state == "open"
    assert planner.breaker("bedrock").seconds_left() <= 60
    out = run(factories=f, decide=decide)
    assert all("skipped" in t for t in out["trace"])


def test_half_open_trial_recovers():
    state = {"fail": True}

    def decide(body, m):
        if state["fail"]:
            raise TimeoutError("read timeout")
        return {"type": "say", "text": "back"}

    f = factories(bedrock="B")
    clk = FakeClock()
    br = planner.breaker("bedrock")
    br.clock = clk
    run(factories=f, decide=decide); run(factories=f, decide=decide)
    assert br.state == "open"
    clk.t += 61
    state["fail"] = False
    out = run(factories=f, decide=decide)
    assert out["provider"] == "strands:bedrock" and br.state == "closed"


def test_unavailable_and_missing_dependency_tiers_are_skipped_not_counted():
    f = factories(bedrock=TierUnavailable("no Bedrock API key"), local=ImportError("No module named 'strands'"))
    out = run(factories=f, decide=lambda b, m: pytest.fail("decide must not run"))
    assert out["type"] == "tool_call" and out["name"] == "progress_report"
    assert [t["tier"] for t in out["trace"]] == ["bedrock", "local"]
    assert "no Bedrock" in out["trace"][0]["skipped"] and "missing dependency" in out["trace"][1]["skipped"]
    assert planner.breaker("bedrock").failures == 0 and planner.breaker("local").failures == 0


def test_deadline_counts_as_failure(monkeypatch):
    import time as _t
    monkeypatch.setenv("SPEAKLOOP_BEDROCK_DEADLINE_S", "0.05")
    monkeypatch.setenv("SPEAKLOOP_TIERS", "bedrock,rules")
    out = run(factories=factories(bedrock="B"), decide=lambda b, m: _t.sleep(0.5) or {"type": "say", "text": "late"})
    assert out["provider"] == "bedrock→rules" and "TimeoutError" in out["trace"][0]["error"]
    assert planner.breaker("bedrock").failures == 1


def test_unknown_tier_skipped(monkeypatch):
    monkeypatch.setenv("SPEAKLOOP_TIERS", "gpt9,rules")
    out = run(factories={}, decide=lambda b, m: pytest.fail("no model"))
    assert out["trace"] == [{"tier": "gpt9", "skipped": "unknown tier"}]


# ------------------------------------------------------------------ CI without strands-agents
def test_planner_works_without_strands(monkeypatch):
    monkeypatch.setitem(sys.modules, "strands", None)  # import strands -> ImportError
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "dummy")
    monkeypatch.setenv("SPEAKLOOP_LOCAL_LLM_URL", "http://127.0.0.1:9/v1")
    assert planner.strands_available() is False
    with pytest.raises(TierUnavailable, match="strands-agents not installed"):
        planner.make_bedrock_model()
    with pytest.raises(TierUnavailable, match="strands-agents not installed"):
        planner.make_local_model()
    out = run()  # real factories
    assert out["type"] == "tool_call" and out["provider"] == "bedrock→local→rules"
    assert all("strands-agents not installed" in t["skipped"] for t in out["trace"])
    assert planner.status()["strands_installed"] is False


def test_unconfigured_tiers_are_unavailable(monkeypatch):
    for k in ("AWS_BEARER_TOKEN_BEDROCK", "AWS_ACCESS_KEY_ID", "AWS_PROFILE", "SPEAKLOOP_LOCAL_LLM_URL"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(TierUnavailable):
        planner.make_bedrock_model()
    with pytest.raises(TierUnavailable):
        planner.make_local_model()


def test_validate_args_rejects_schema_violations():
    pytest.importorskip("jsonschema")
    spec = {"name": "next_drill", "inputSchema": {"type": "object", "required": ["learner_id"],
                                                  "properties": {"learner_id": {"type": "string"},
                                                                 "l1": {"type": "string", "enum": ["vi"]}}}}
    planner._validate_args(spec, {"learner_id": "a", "l1": "vi"})
    with pytest.raises(InvalidDecision, match="fail schema"):
        planner._validate_args(spec, {"learner_id": "a", "l1": "vietnamese"})
    planner._validate_args(None, {"anything": 1})
