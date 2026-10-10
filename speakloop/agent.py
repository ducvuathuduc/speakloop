"""Pluggable planner for the Alexa+ experience simulator.

The browser is the MCP client: it owns the conversation and executes every
tool call against the MCP server over Streamable HTTP. For each turn it asks
this planner "what next?" and gets back either a tool call or a line to speak.

Providers (env SPEAKLOOP_LLM):
  rules   - deterministic intent router, no keys needed (default; used in tests)
  bedrock - Amazon Bedrock Converse API with tool use (boto3); the Agent Skill
            fetched from the MCP server becomes the system prompt
  openai  - any OpenAI-compatible chat-completions endpoint

Guardrail shared by all providers: while a drill is active, the learner's next
utterance is submitted verbatim with submit_attempt, so no model can "fix" the
transcript (dropped endings are exactly what the coach measures).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
log = logging.getLogger("speakloop.agent")


class LLMThrottled(RuntimeError):
    """Provider refused for quota/throttling (e.g. Bedrock 'Too many tokens per day')."""


# Circuit breaker: after a throttle, skip the LLM for a while so every turn isn't a slow failed call.
_COOLDOWN_S = float(os.environ.get("SPEAKLOOP_LLM_COOLDOWN_S", "600"))
_throttled_until = 0.0

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
     "november", "december"], start=1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})

TASK_WORDS = [
    (r"read(ing)? aloud|read a passage", "read_aloud"),
    (r"repeat", "repeat_sentence"),
    (r"short question|quiz|question", "answer_short_question"),
    (r"describe|chart|image|graph", "describe_image"),
]
CONTROL = re.compile(r"^(stop|skip|cancel|next|progress|how am i doing)\b", re.I)


def provider_name() -> str:
    return os.environ.get("SPEAKLOOP_LLM", "rules").lower()


# ------------------------------------------------------------------ helpers
def parse_exam_date(text: str, today: date | None = None) -> str | None:
    today = today or datetime.now(TZ).date()
    t = text.lower()
    m = re.search(r"(20\d\d)-(\d{1,2})-(\d{1,2})", t)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3])).isoformat()
    m = re.search(r"in (\d+|a|one|two|three|four|five|six|eight|ten|twelve) (day|week|month)s?", t)
    if m:
        words = {"a": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "eight": 8, "ten": 10, "twelve": 12}
        n = int(m[1]) if m[1].isdigit() else words[m[1]]
        days = n * {"day": 1, "week": 7, "month": 30}[m[2]]
        return (today + timedelta(days=days)).isoformat()
    month_names = "|".join(sorted(MONTHS, key=len, reverse=True))
    m = re.search(rf"\b({month_names})\.? (\d{{1,2}})(st|nd|rd|th)?\b", t) or None
    if m:
        mon, day_ = MONTHS[m[1]], int(m[2])
    else:
        m = re.search(rf"\b(\d{{1,2}})(st|nd|rd|th)? (of )?({month_names})\b", t)
        if not m:
            return None
        mon, day_ = MONTHS[m[4]], int(m[1])
    d = date(today.year, mon, day_)
    if d < today:
        d = date(today.year + 1, mon, day_)
    return d.isoformat()


def parse_target(text: str) -> int | None:
    m = re.search(r"\b(score|target|aim|get|need|goal)\D{0,25}?\b([1-8]\d|90)\b(?! ?(minutes|mins|days|weeks|months))", text.lower())
    return int(m[2]) if m else None


def _last(messages: list[dict], role: str) -> dict | None:
    for m in reversed(messages):
        if m.get("role") == role:
            return m
    return None


def guardrail(body: dict) -> dict | None:
    """Submit the learner's utterance verbatim while a drill is active."""
    msgs = body.get("messages") or []
    state = body.get("state") or {}
    if not msgs or msgs[-1].get("role") != "user" or not state.get("active_drill_id"):
        return None
    text = msgs[-1].get("content", "")
    if CONTROL.match(text.strip()):
        return None
    return {
        "type": "tool_call",
        "name": "submit_attempt",
        "arguments": {
            "learner_id": body.get("learner_id", "demo"),
            "drill_id": state["active_drill_id"],
            "transcript": text,
            **({"duration_seconds": round(float(msgs[-1]["duration_seconds"]), 1)} if msgs[-1].get("duration_seconds") else {}),
        },
        "reason": "guardrail: active drill → submit transcript verbatim",
    }


# ------------------------------------------------------------------ rules
def rules_step(body: dict) -> dict:
    msgs = body.get("messages") or []
    learner = body.get("learner_id", "demo")
    state = body.get("state") or {}
    if not msgs:
        return {"type": "tool_call", "name": "get_learner_profile", "arguments": {"learner_id": learner}}
    last = msgs[-1]
    if last.get("role") == "tool":
        sc = last.get("result") or {}
        return {"type": "say", "text": sc.get("speech") or "Done."}

    text = (last.get("content") or "").strip()
    t = text.lower()

    if re.search(r"\b(stop|cancel|goodbye|bye)\b", t):
        return {"type": "say", "text": "Great session. See you tomorrow — keep the streak going!", "end": True}
    if re.search(r"how am i doing|progress|my score|report", t):
        return {"type": "tool_call", "name": "progress_report", "arguments": {"learner_id": learner}}
    if re.search(r"\breview\b|tricky words|my words", t):
        return {"type": "tool_call", "name": "start_sound_review", "arguments": {"learner_id": learner}}

    m = re.search(r"remind me|reminder|every (day|morning|evening|night)|routine", t)
    if m:
        tm = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", t)
        if tm:
            hh = int(tm[1]) % 12 + (12 if tm[3] == "pm" else 0) if tm[3] else int(tm[1])
            mins = re.search(r"(\d+)\s*(minutes|mins|min)", t)
            return {"type": "tool_call", "name": "set_practice_routine",
                    "arguments": {"learner_id": learner, "time_local": f"{hh:02d}:{int(tm[2] or 0):02d}",
                                  **({"minutes": int(mins[1])} if mins else {})}}
        return {"type": "say", "text": "Sure — what time should I remind you each day?"}

    exam = parse_exam_date(t)
    target = parse_target(t)
    if exam or target:
        args: dict[str, Any] = {"learner_id": learner}
        if exam:
            args["exam_date"] = exam
        if target:
            args["target_score"] = target
        return {"type": "tool_call", "name": "set_goal", "arguments": args}

    m = re.search(r"\b(th|final s|ed ending|-ed|cluster)s?\b.*\b(tip|explain|how)\b|\b(tip|explain|how)\b.*\b(th|final s|-ed|ed|cluster)", t)
    if m and "practi" not in t:
        feat = "th" if " th" in f" {t}" else "final_ed" if "ed" in t else "clusters" if "cluster" in t else "final_s"
        return {"type": "tool_call", "name": "explain_sound", "arguments": {"feature": feat}}

    for pattern, task in TASK_WORDS:
        if re.search(pattern, t):
            return {"type": "tool_call", "name": "start_drill", "arguments": {"learner_id": learner, "task_type": task}}

    if re.search(r"\b(yes|yeah|yep|sure|ok|okay|ready|next|go|continue|start step)\b", t) and state.get("plan_steps"):
        idx = int(state.get("step_index", 0))
        steps = state["plan_steps"]
        if idx < len(steps):
            s = steps[idx]
            if s.get("tool") == "start_sound_review":
                return {"type": "tool_call", "name": "start_sound_review", "arguments": {"learner_id": learner}}
            args = {"learner_id": learner, "task_type": s.get("task_type")}
            if s.get("focus"):
                args["focus"] = s["focus"]
            return {"type": "tool_call", "name": "start_drill", "arguments": args}
        return {"type": "say", "text": "That's today's plan done! Say 'how am I doing' to see your progress."}

    if re.search(r"practi[cs]e|let'?s (go|start|begin)|study|plan|lesson|session|train", t):
        mm = re.search(r"(\d+)\s*(minutes|mins|min)", t)
        return {"type": "tool_call", "name": "plan_today_session",
                "arguments": {"learner_id": learner, "minutes": int(mm[1]) if mm else 15}}
    if re.search(r"\b(hi|hello|hey|open|start)\b", t):
        return {"type": "tool_call", "name": "get_learner_profile", "arguments": {"learner_id": learner}}
    if re.search(r"\b(yes|ok|okay|sure|ready|next)\b", t):
        return {"type": "tool_call", "name": "start_drill", "arguments": {"learner_id": learner}}
    return {"type": "say", "text": "You can say “let's practise”, “how am I doing”, or “review my words”."}


# ------------------------------------------------------------------ LLM providers
def _system_prompt(body: dict) -> str:
    skill = body.get("skill") or ""
    state = json.dumps(body.get("state") or {}, ensure_ascii=False)
    return (
        f"{skill}\n\n---\nRuntime context: learner_id={body.get('learner_id', 'demo')}; "
        f"today={datetime.now(TZ).date().isoformat()} (Asia/Ho_Chi_Minh); simulator state={state}.\n"
        "Call at most one tool per turn. When the last message is a tool result, reply with one or two spoken sentences "
        "(you may reuse its 'speech' field)."
    )


def _compact(result: dict) -> dict:
    keep = {k: v for k, v in (result or {}).items() if k not in ("profile",)}
    s = json.dumps(keep, ensure_ascii=False, default=str)
    return keep if len(s) < 6000 else {"speech": keep.get("speech"), "kind": keep.get("kind")}


def to_bedrock_messages(msgs: list[dict]) -> list[dict]:
    out: list[dict] = []

    def push(role: str, block: dict) -> None:
        if out and out[-1]["role"] == role:
            out[-1]["content"].append(block)
        else:
            out.append({"role": role, "content": [block]})

    for m in msgs:
        r = m.get("role")
        if r == "user":
            push("user", {"text": m.get("content") or "…"})
        elif r == "assistant" and m.get("tool_call"):
            tc = m["tool_call"]
            push("assistant", {"toolUse": {"toolUseId": tc["id"], "name": tc["name"], "input": tc.get("arguments") or {}}})
        elif r == "assistant":
            push("assistant", {"text": m.get("content") or "…"})
        elif r == "tool":
            push("user", {"toolResult": {"toolUseId": m["tool_call_id"], "content": [{"json": _compact(m.get("result") or {})}],
                                         **({"status": "error"} if m.get("is_error") else {})}})
    if out and out[0]["role"] != "user":
        out.insert(0, {"role": "user", "content": [{"text": "(session started)"}]})
    return out


def _clean_schema(node):
    """Make SDK-generated JSON Schema friendly to Bedrock models (e.g. Amazon Nova):
    collapse Optional (anyOf [X, null]) to X and drop titles / null defaults."""
    if isinstance(node, dict):
        if "anyOf" in node:
            non_null = [n for n in node["anyOf"] if n.get("type") != "null"]
            if len(non_null) == 1:
                merged = {k: v for k, v in node.items() if k != "anyOf"}
                merged.update(non_null[0])
                node = merged
        return {k: _clean_schema(v) for k, v in node.items()
                if k != "title" and not (k == "default" and v is None)}
    if isinstance(node, list):
        return [_clean_schema(n) for n in node]
    return node


def bedrock_tool_config(tools: list[dict]) -> dict:
    return {"tools": [{"toolSpec": {"name": t["name"], "description": (t.get("description") or t["name"])[:1000],
                                    "inputSchema": {"json": _clean_schema(t.get("inputSchema") or {"type": "object"})}}}
                      for t in tools]}


def _bedrock_request(body: dict) -> tuple[str, dict]:
    model = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
    msgs = to_bedrock_messages(body.get("messages") or []) or [{"role": "user", "content": [{"text": "Hello"}]}]
    req = {
        "system": [{"text": _system_prompt(body)}],
        "messages": msgs,
        "toolConfig": bedrock_tool_config(body.get("tools") or []),
        "inferenceConfig": {"maxTokens": 400, "temperature": 0.2},
    }
    return model, req


def _bedrock_decision(resp: dict) -> dict:
    content = resp["output"]["message"]["content"]
    for block in content:
        if "toolUse" in block:
            tu = block["toolUse"]
            return {"type": "tool_call", "id": tu["toolUseId"], "name": tu["name"], "arguments": tu.get("input") or {}}
    text = " ".join(b.get("text", "") for b in content).strip()
    # Nova sometimes wraps its reasoning in <thinking> tags; never speak it.
    text = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.S).strip()
    return {"type": "say", "text": text or "Okay."}


def bedrock_step(body: dict, client=None, http=None) -> dict:
    """Amazon Bedrock Converse API with tool use.

    Auth, in order:
      1. AWS_BEARER_TOKEN_BEDROCK (Bedrock API key) -> direct HTTPS call with `Authorization: Bearer`
         to bedrock-runtime.<region>.amazonaws.com/model/<modelId>/converse (no AWS SDK needed);
      2. otherwise boto3 `bedrock-runtime.converse` with the standard AWS credential chain.
    """
    model, req = _bedrock_request(body)
    region = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
    token = os.environ.get("AWS_BEARER_TOKEN_BEDROCK")
    if client is None and token:
        import httpx
        from urllib.parse import quote

        url = f"https://bedrock-runtime.{region}.amazonaws.com/model/{quote(model, safe='')}/converse"
        post = http or httpx.post
        r = post(url, json=req, timeout=30,
                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"})
        if r.status_code == 429 or (r.status_code >= 400 and "too many" in r.text.lower()):
            raise LLMThrottled(f"Bedrock throttled ({r.status_code}): {r.text[:200]}")
        if r.status_code >= 400:
            raise RuntimeError(f"Bedrock {r.status_code}: {r.text[:300]}")
        return _bedrock_decision(r.json())
    if client is None:
        import boto3  # imported lazily so the default path needs no AWS SDK

        client = boto3.client("bedrock-runtime", region_name=region)
    try:
        resp = client.converse(modelId=model, **req)
    except Exception as exc:  # botocore ThrottlingException / ServiceQuotaExceededException
        if type(exc).__name__ in ("ThrottlingException", "ServiceQuotaExceededException") or "too many" in str(exc).lower():
            raise LLMThrottled(str(exc)[:200]) from exc
        raise
    return _bedrock_decision(resp)


def openai_step(body: dict) -> dict:
    import httpx

    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    messages: list[dict] = [{"role": "system", "content": _system_prompt(body)}]
    for m in body.get("messages") or []:
        if m["role"] == "user":
            messages.append({"role": "user", "content": m.get("content", "")})
        elif m["role"] == "assistant" and m.get("tool_call"):
            tc = m["tool_call"]
            messages.append({"role": "assistant", "content": None, "tool_calls": [
                {"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": json.dumps(tc.get("arguments") or {})}}]})
        elif m["role"] == "assistant":
            messages.append({"role": "assistant", "content": m.get("content", "")})
        elif m["role"] == "tool":
            messages.append({"role": "tool", "tool_call_id": m["tool_call_id"], "content": json.dumps(_compact(m.get("result") or {}))})
    tools = [{"type": "function", "function": {"name": t["name"], "description": t.get("description", ""),
                                               "parameters": t.get("inputSchema") or {"type": "object"}}} for t in body.get("tools") or []]
    r = httpx.post(f"{base}/chat/completions", timeout=60,
                   headers={"Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', '')}"},
                   json={"model": model, "messages": messages, "tools": tools, "temperature": 0.3})
    r.raise_for_status()
    msg = r.json()["choices"][0]["message"]
    if msg.get("tool_calls"):
        tc = msg["tool_calls"][0]
        return {"type": "tool_call", "id": tc["id"], "name": tc["function"]["name"],
                "arguments": json.loads(tc["function"]["arguments"] or "{}")}
    return {"type": "say", "text": msg.get("content") or "Okay."}


async def step(body: dict) -> dict:
    g = guardrail(body)
    provider = provider_name()
    if g:
        return g | {"provider": provider}
    global _throttled_until
    if provider in ("bedrock", "openai") and time.monotonic() < _throttled_until:
        left = int(_throttled_until - time.monotonic())
        return rules_step(body) | {"provider": f"{provider}→rules", "reason": f"LLM throttled; offline planner for {left}s more"}
    if provider in ("bedrock", "openai"):
        fn = bedrock_step if provider == "bedrock" else openai_step
        try:
            out = await asyncio.to_thread(fn, body)
            if out.get("type") == "tool_call" and body.get("tools") and out["name"] not in {t["name"] for t in body["tools"]}:
                raise ValueError(f"model chose unknown tool {out['name']!r}")
            return out | {"provider": provider, "model": os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0") if provider == "bedrock" else os.environ.get("OPENAI_MODEL")}
        except LLMThrottled as exc:
            _throttled_until = time.monotonic() + _COOLDOWN_S
            log.warning("%s throttled, using offline planner for %ss: %s", provider, int(_COOLDOWN_S), exc)
            return rules_step(body) | {"provider": f"{provider}→rules", "reason": f"quota/throttle — offline planner: {str(exc)[:120]}"}
        except Exception as exc:  # keep the session alive: fall back to the offline planner
            log.warning("%s planner failed, using offline planner: %s", provider, exc)
            return rules_step(body) | {"provider": f"{provider}→rules", "reason": f"fallback: {str(exc)[:160]}"}
    return rules_step(body) | {"provider": "rules"}
