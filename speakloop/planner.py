"""Tiered planner built on the Strands Agents SDK.

The browser simulator is the MCP client and executes every tool call itself, so the
planner's job is one decision per turn: "call tool X with args Y" or "say Z".
We run a real Strands ``Agent`` whose tools are the MCP tools the client listed; each tool
is a *capture* tool that records the call and stops the Strands event loop
(``request_state["stop_event_loop"]``), so the decision goes back to the client instead
of being executed server-side.

Tiers, tried in order (env ``SPEAKLOOP_TIERS``, default ``bedrock,local,rules``):

  bedrock  Strands ``BedrockModel`` (Amazon Nova by default). Enabled when a Bedrock API key
           (``AWS_BEARER_TOKEN_BEDROCK``) or AWS credentials are configured.
  local    Strands ``LlamaCppModel`` against a llama.cpp ``llama-server`` (any OpenAI-compatible
           server) at ``SPEAKLOOP_LOCAL_LLM_URL``; tested with Qwen2.5-1.5B-Instruct Q4_K_M on CPU.
  rules    the deterministic intent router in ``agent.rules_step`` (always available).

Each model tier sits behind a circuit breaker: a throttle (``ModelThrottledException``, HTTP 429)
opens it at once for ``SPEAKLOOP_THROTTLE_COOLDOWN_S`` (600 s); other failures (timeouts,
invalid tool calls, unknown tools, schema-invalid arguments) open it after
``SPEAKLOOP_BREAKER_FAILURES`` (2) in a row for ``SPEAKLOOP_BREAKER_COOLDOWN_S`` (60 s).
After the cool-down one trial call is let through (half-open). Strands' own retry loop is
disabled (``retry_strategy=None``) so a throttled tier fails fast instead of backing off for
minutes.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("speakloop.planner")


# ------------------------------------------------------------------ circuit breaker
@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 2
    cooldown_s: float = 60.0
    throttle_cooldown_s: float = 600.0
    clock: Callable[[], float] = time.monotonic
    failures: int = 0
    open_until: float = 0.0
    last_error: str | None = None
    state: str = "closed"  # closed | open | half_open

    def allow(self) -> bool:
        if self.state == "open":
            if self.clock() >= self.open_until:
                self.state = "half_open"
                return True
            return False
        return True

    def record_success(self) -> None:
        self.failures, self.state, self.last_error = 0, "closed", None

    def record_failure(self, err: str, *, throttled: bool = False) -> None:
        self.last_error = err[:200]
        self.failures += 1
        if throttled or self.state == "half_open" or self.failures >= self.failure_threshold:
            self.state = "open"
            self.open_until = self.clock() + (self.throttle_cooldown_s if throttled else self.cooldown_s)

    def seconds_left(self) -> int:
        return max(0, int(self.open_until - self.clock())) if self.state == "open" else 0

    def snapshot(self) -> dict:
        return {"tier": self.name, "state": self.state, "failures": self.failures,
                "retry_in_s": self.seconds_left(), "last_error": self.last_error}


def _env_f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


BREAKERS: dict[str, CircuitBreaker] = {}


def breaker(tier: str) -> CircuitBreaker:
    if tier not in BREAKERS:
        BREAKERS[tier] = CircuitBreaker(
            tier,
            failure_threshold=int(_env_f("SPEAKLOOP_BREAKER_FAILURES", 2)),
            cooldown_s=_env_f("SPEAKLOOP_BREAKER_COOLDOWN_S", 60),
            throttle_cooldown_s=_env_f("SPEAKLOOP_THROTTLE_COOLDOWN_S", 600),
        )
    return BREAKERS[tier]


def reset_breakers() -> None:
    BREAKERS.clear()


# ------------------------------------------------------------------ model factories
class TierUnavailable(RuntimeError):
    pass


class InvalidDecision(RuntimeError):
    pass


def bedrock_configured() -> bool:
    return bool(os.environ.get("AWS_BEARER_TOKEN_BEDROCK") or os.environ.get("AWS_ACCESS_KEY_ID")
                or os.environ.get("AWS_PROFILE"))


def make_bedrock_model():
    if not bedrock_configured():
        raise TierUnavailable("no Bedrock API key or AWS credentials configured")
    from botocore.config import Config
    from strands.models.bedrock import BedrockModel

    return BedrockModel(
        model_id=os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0"),
        region_name=os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1")),
        temperature=0.2, max_tokens=400, streaming=False,
        boto_client_config=Config(read_timeout=20, connect_timeout=5, retries={"max_attempts": 1, "mode": "standard"}),
    )


def make_local_model():
    url = os.environ.get("SPEAKLOOP_LOCAL_LLM_URL")
    if not url:
        raise TierUnavailable("SPEAKLOOP_LOCAL_LLM_URL not set (start llama-server, see docs/AGENT.md)")
    from urllib.parse import urlparse

    from strands.models.llamacpp import LlamaCppModel

    host = urlparse(url).hostname or ""
    if host in ("127.0.0.1", "localhost", "::1"):  # never send a local model call through an HTTP proxy
        for k in ("NO_PROXY", "no_proxy"):
            cur = os.environ.get(k, "")
            if host not in cur.split(","):
                os.environ[k] = ",".join(x for x in (cur, host) if x)

    return LlamaCppModel(base_url=url, timeout=_env_f("SPEAKLOOP_LOCAL_TIMEOUT_S", 90),
                         model_id=os.environ.get("SPEAKLOOP_LOCAL_MODEL", "qwen2.5-1.5b-instruct"),
                         params={"temperature": 0.1, "max_tokens": 200})


MODEL_FACTORIES: dict[str, Callable[[], Any]] = {"bedrock": make_bedrock_model, "local": make_local_model}


def tiers() -> list[str]:
    raw = os.environ.get("SPEAKLOOP_TIERS", "bedrock,local,rules")
    out = [t.strip() for t in raw.split(",") if t.strip()]
    return out if "rules" in out else out + ["rules"]


# ------------------------------------------------------------------ Strands decision
def _capture_tools(specs: list[dict], sink: dict):
    from strands.tools.tools import PythonAgentTool

    from .agent import _clean_schema

    def make(spec: dict):
        name = spec["name"]

        def fn(tool_use, **invocation_state):
            if "name" not in sink:  # first call wins; one tool per turn
                sink.update(name=name, id=tool_use.get("toolUseId"), arguments=tool_use.get("input") or {})
            invocation_state.setdefault("request_state", {})["stop_event_loop"] = True
            return {"toolUseId": tool_use["toolUseId"], "status": "success",
                    "content": [{"text": "Queued: the MCP client will execute this call."}]}

        tspec = {"name": name, "description": (spec.get("description") or name)[:1000],
                 "inputSchema": {"json": _clean_schema(spec.get("inputSchema") or {"type": "object", "properties": {}})}}
        return PythonAgentTool(name, tspec, fn)

    return [make(s) for s in specs]


def _validate_args(spec: dict | None, args: dict) -> None:
    if not spec:
        return
    try:
        import jsonschema
    except ImportError:  # pragma: no cover - jsonschema ships with strands-agents
        return
    try:
        jsonschema.validate(args, spec.get("inputSchema") or {"type": "object"})
    except jsonschema.ValidationError as exc:
        raise InvalidDecision(f"arguments for {spec['name']} fail schema: {exc.message}") from exc


def strands_decide(body: dict, model) -> dict:
    """Run one Strands Agent turn and return a planner decision."""
    import re

    from strands import Agent

    from .agent import _system_prompt, to_bedrock_messages

    specs = body.get("tools") or []
    sink: dict[str, Any] = {}
    history = to_bedrock_messages(body.get("messages") or []) or [{"role": "user", "content": [{"text": "(session started)"}]}]
    prompt = history.pop()["content"] if history[-1]["role"] == "user" else [{"text": "(continue)"}]
    agent = Agent(model=model, tools=_capture_tools(specs, sink), system_prompt=_system_prompt(body),
                  messages=history, callback_handler=None, retry_strategy=None)
    result = agent(prompt)
    if sink.get("name"):
        by_name = {s["name"]: s for s in specs}
        if specs and sink["name"] not in by_name:
            raise InvalidDecision(f"model chose unknown tool {sink['name']!r}")
        args = dict(sink.get("arguments") or {})
        if "learner_id" in (by_name.get(sink["name"], {}).get("inputSchema") or {}).get("properties", {}):
            args.setdefault("learner_id", body.get("learner_id", "demo"))
        _validate_args(by_name.get(sink["name"]), args)
        return {"type": "tool_call", "id": sink.get("id"), "name": sink["name"], "arguments": args}
    text = str(result).strip()
    text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.S).strip()
    if not text:
        raise InvalidDecision("model returned neither a tool call nor text")
    return {"type": "say", "text": text}


def _is_throttle(exc: BaseException) -> bool:
    name = type(exc).__name__
    return name in ("ModelThrottledException", "ThrottlingException", "ServiceQuotaExceededException") or \
        "too many tokens" in str(exc).lower() or "429" in str(exc)


# ------------------------------------------------------------------ the chain
async def plan(body: dict, *, factories: dict[str, Callable[[], Any]] | None = None,
               decide: Callable[[dict, Any], dict] = strands_decide) -> dict:
    from .agent import rules_step

    factories = factories or MODEL_FACTORIES
    trace: list[dict] = []
    for tier in tiers():
        if tier == "rules":
            break
        br = breaker(tier)
        if not br.allow():
            trace.append({"tier": tier, "skipped": f"circuit open {br.seconds_left()}s"})
            continue
        try:
            model = factories[tier]()
        except TierUnavailable as exc:
            trace.append({"tier": tier, "skipped": str(exc)})
            continue
        except KeyError:
            trace.append({"tier": tier, "skipped": "unknown tier"})
            continue
        t0 = time.monotonic()
        try:
            timeout = _env_f(f"SPEAKLOOP_{tier.upper()}_DEADLINE_S", 25 if tier == "bedrock" else 100)
            out = await asyncio.wait_for(asyncio.to_thread(decide, body, model), timeout=timeout)
        except Exception as exc:  # noqa: BLE001 - every failure moves us down a tier
            throttled = _is_throttle(exc)
            msg = f"{type(exc).__name__}: {exc}" if str(exc) else type(exc).__name__
            br.record_failure(msg, throttled=throttled)
            trace.append({"tier": tier, "error": msg[:160], "throttled": throttled, "ms": int((time.monotonic() - t0) * 1000)})
            log.warning("planner tier %s failed (%s); trying next tier", tier, msg[:160])
            continue
        br.record_success()
        trace.append({"tier": tier, "ok": True, "ms": int((time.monotonic() - t0) * 1000)})
        return out | {"provider": f"strands:{tier}", "trace": trace}
    out = rules_step(body)
    fell = [t["tier"] for t in trace if not t.get("ok")]
    reason = "; ".join(f"{t['tier']}: {t.get('error') or t.get('skipped')}" for t in trace)
    return out | {"provider": ("→".join(fell + ["rules"]) if fell else "rules"), "trace": trace,
                  **({"reason": reason[:240]} if reason else {})}


def status() -> dict:
    return {"tiers": tiers(), "breakers": [breaker(t).snapshot() for t in tiers() if t != "rules"],
            "bedrock_configured": bedrock_configured(),
            "local_url": os.environ.get("SPEAKLOOP_LOCAL_LLM_URL")}
