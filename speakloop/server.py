"""SpeakLoop MCP server (MCP 2025-11-25, Streamable HTTP).

Run:  python -m speakloop.server   (defaults to http://127.0.0.1:8765)

Exposes:
  * 9 tools for an Alexa+-style voice coaching session (stateful per learner)
  * 4 Sound Graph tools (FSRS memory per sound) and 2 pronunciation tools
    (assess_pronunciation: phone-level scoring of a WAV; start_pair_drill: minimal pairs)
  * skill://l1-<code>/...      - installed L1 sound packs (Agent Skills), e.g. l1-vi
  * ui://speakloop/card.html   - an MCP App (text/html;profile=mcp-app) every tool renders into
  * skill://speakloop-coach/... - the Agent Skill (SKILL.md + reference) served as resources
  * /            - the Alexa+ experience simulator (a browser MCP client)
  * /agent/step  - the pluggable LLM planner the simulator uses (rules | bedrock | openai)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from . import agent as agent_mod
from .coach import Coach
from .content import FEATURE_TIPS, TASK_LABELS
from .memory import SoundGraph
from .memory_tools import register as register_memory_tools
from .pronunciation import register as register_pronunciation_tools

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
SKILL_DIR = ROOT / "skills" / "speakloop-coach"
CARD_URI = "ui://speakloop/card.html"
CARD_MIME = "text/html;profile=mcp-app"
UI_META = {"ui": {"resourceUri": CARD_URI}}

coach = Coach(os.environ.get("SPEAKLOOP_DB", str(ROOT / "speakloop.db")))

mcp = MCPServer(
    name="speakloop",
    title="SpeakLoop — English speaking coach",
    description="Voice-first English speaking practice with memory across sessions.",
    instructions=(
        "SpeakLoop coaches English speaking (PTE-style tasks). Load the speakloop-coach Agent Skill "
        "(resource skill://speakloop-coach/SKILL.md) for the session flow. Every tool result has a "
        "'speech' field meant to be spoken aloud and renders into the ui://speakloop/card.html MCP App."
    ),
    version="0.2.0",
)

LearnerId = Annotated[str, Field(description="Stable id of the learner (e.g. the household profile id).")]


def _result(kind: str, speech: str, data: dict[str, Any], learner_id: str | None = None) -> CallToolResult:
    payload = {"kind": kind, "speech": speech, **data}
    if learner_id:
        payload["learner_id"] = learner_id
    return CallToolResult(
        content=[TextContent(type="text", text=speech + "\n\n" + json.dumps(data, ensure_ascii=False, default=str))],
        structured_content=payload,
    )


# ---------------------------------------------------------------------------- tools
@mcp.tool(
    title="Get learner profile",
    description="Return the learner's goal, practice estimate, streak, weak sounds and due reviews. Creates the learner on first use.",
    annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True),
    meta=UI_META,
)
def get_learner_profile(learner_id: LearnerId, name: Annotated[str | None, Field(description="Display name, optional")] = None) -> CallToolResult:
    if name:
        coach.ensure_learner(learner_id, name)
    p = coach.profile(learner_id)
    if p["total_attempts"] == 0:
        speech = f"Hi {p['name']}! I'm your speaking coach. What score are you aiming for, and when is your exam?"
    else:
        bits = [f"Welcome back, {p['name']}."]
        if p["streak_days"]:
            bits.append(f"You're on a {p['streak_days']}-day streak.")
        if p["review_due"]:
            bits.append(f"{p['review_due']} tricky word{'s are' if p['review_due'] > 1 else ' is'} due for review.")
        if p["days_until_exam"] is not None:
            bits.append(f"{p['days_until_exam']} days until your exam.")
        speech = " ".join(bits)
    return _result("profile", speech, p, learner_id)


@mcp.tool(
    title="Set exam goal",
    description="Save the learner's target score (10-90 practice scale) and exam date (YYYY-MM-DD).",
    annotations=ToolAnnotations(idempotent_hint=True),
    meta=UI_META,
)
def set_goal(
    learner_id: LearnerId,
    target_score: Annotated[int | None, Field(ge=10, le=90, description="Target overall score, 10-90")] = None,
    exam_date: Annotated[str | None, Field(description="Exam date, YYYY-MM-DD")] = None,
    name: Annotated[str | None, Field(description="Learner display name")] = None,
) -> CallToolResult:
    p = coach.set_goal(learner_id, target_score, exam_date, name)
    parts = []
    if p["target_score"]:
        parts.append(f"a target of {p['target_score']}")
    if p["days_until_exam"] is not None:
        parts.append(f"your exam in {p['days_until_exam']} days")
    speech = ("Got it: " + " and ".join(parts) + ". Say 'let's practise' when you're ready.") if parts else "Goal saved."
    return _result("profile", speech, p, learner_id)


@mcp.tool(
    title="Plan today's session",
    description="Build today's practice plan from the learner's history: due sound reviews first, then the weakest task types, sized to the minutes available.",
    annotations=ToolAnnotations(read_only_hint=True),
    meta=UI_META,
)
def plan_today_session(
    learner_id: LearnerId,
    minutes: Annotated[int, Field(ge=5, le=60, description="Minutes available today")] = 15,
) -> CallToolResult:
    plan = coach.plan_today(learner_id, minutes)
    for s in plan["steps"]:
        s["label"] = "Sound review" if s["step"] == "review" else TASK_LABELS[s["step"]]
    plan["focus_label"] = FEATURE_TIPS[plan["focus_feature"]]["label"] if plan["focus_feature"] else None
    first = plan["steps"][0]["label"] if plan["steps"] else "a drill"
    focus = f" We'll focus on {plan['focus_label'].lower()}." if plan["focus_label"] else ""
    speech = f"Here's your {plan['minutes']}-minute plan: {len(plan['steps'])} steps.{focus} First up, {first}. Ready?"
    return _result("plan", speech, plan, learner_id)


@mcp.tool(
    title="Start a speaking drill",
    description=(
        "Start one drill and return its drill_id. task_type: read_aloud | repeat_sentence | answer_short_question | describe_image "
        "(omit to pick the learner's weakest). focus: final_s | final_ed | th | clusters | final_consonant. "
        "For repeat_sentence / answer_short_question the device must speak 'speak_text' aloud and not display it."
    ),
    meta=UI_META,
)
def start_drill(
    learner_id: LearnerId,
    task_type: Annotated[str | None, Field(description="Task type; omit to auto-pick")] = None,
    focus: Annotated[str | None, Field(description="Pronunciation feature to target")] = None,
) -> CallToolResult:
    d = coach.start_drill(learner_id, task_type, focus)
    intro = {
        "read_aloud": "Read the passage on screen aloud. Start when you're ready.",
        "repeat_sentence": "Listen carefully, then repeat the sentence.",
        "answer_short_question": "Answer in one or two words.",
        "describe_image": "Look at the chart and describe it in about thirty seconds.",
    }[d["task_type"]]
    return _result("drill", intro, d, learner_id)


@mcp.tool(
    title="Submit a spoken attempt",
    description=(
        "Score the learner's spoken attempt for a drill. Pass the raw speech-to-text transcript unchanged and the speaking "
        "duration in seconds. Returns content/fluency/pronunciation scores (10-90 practice scale), word-level issues, "
        "and bilingual (English/Vietnamese) tips. Missed sounds are queued for spaced-repetition review."
    ),
    meta=UI_META,
)
def submit_attempt(
    learner_id: LearnerId,
    drill_id: Annotated[str, Field(description="drill_id returned by start_drill / start_sound_review")],
    transcript: Annotated[str, Field(description="Exact speech-to-text transcript of the attempt")],
    duration_seconds: Annotated[float | None, Field(description="How long the learner spoke, in seconds")] = None,
) -> CallToolResult:
    r = coach.submit_attempt(learner_id, drill_id, transcript, duration_seconds)
    s = r["score"]
    if r["task_type"] == "answer_short_question":
        speech = "Correct!" if s["correct"] else f"Not quite — the answer is {r['reference']}."
    else:
        verdict = "Excellent" if s["overall"] >= 85 else "Good work" if s["overall"] >= 65 else "Nice try"
        speech = f"{verdict} — {s['overall']} overall."
        if r["tips"]:
            t = r["tips"][0]
            examples = [i["expected"] for i in s["issues"] if i.get("feature") == t["feature"]][:2]
            ex = f" Listen for {' and '.join(examples)}." if examples else ""
            speech += f" Main fix: {t['label'].lower()}.{ex}"
        elif s["overall"] >= 65:
            speech += " Clear and steady."
    return _result("result", speech, r, learner_id)


@mcp.tool(
    title="Start sound review",
    description="Start a spaced-repetition review of words whose sounds the learner dropped in earlier sessions. Submit with submit_attempt.",
    meta=UI_META,
)
def start_sound_review(learner_id: LearnerId, limit: Annotated[int, Field(ge=1, le=10)] = 5) -> CallToolResult:
    r = coach.start_review(learner_id, limit)
    if not r["drill_id"]:
        return _result("review", "Nothing to review today — nice!", r, learner_id)
    return _result("review", f"Quick review of {len(r['items'])} words you missed before. Say each one clearly.", r, learner_id)


@mcp.tool(
    title="Progress report",
    description="Show the learner's practice estimate trend, streak, gap to target and recurring weak sounds.",
    annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True),
    meta=UI_META,
)
def progress_report(learner_id: LearnerId, days: Annotated[int, Field(ge=1, le=90)] = 14) -> CallToolResult:
    r = coach.progress(learner_id, days)
    p = r["profile"]
    if not p["total_attempts"]:
        speech = "No practice recorded yet. Want to start with a quick drill?"
    else:
        speech = f"Your current practice estimate is {p['estimated_score']}."
        if r["gap_to_target"] is not None:
            speech += (f" That's {r['gap_to_target']} points below your target." if r["gap_to_target"] > 0
                       else " You're at or above your target!")
        if p["weak_features"]:
            speech += f" Keep working on {p['weak_features'][0]['label'].lower()}."
    return _result("progress", speech, r, learner_id)


@mcp.tool(
    title="Get pronunciation tip",
    description="Explain one pronunciation feature in English and Vietnamese (final_s, final_ed, th, clusters, final_consonant, fluency, content).",
    annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True),
)
def explain_sound(feature: Annotated[str, Field(description="Feature id")]) -> CallToolResult:
    tip = FEATURE_TIPS.get(feature)
    if not tip:
        return CallToolResult(content=[TextContent(type="text", text=f"Unknown feature {feature!r}. Options: {', '.join(FEATURE_TIPS)}")], is_error=True)
    return _result("tip", tip["en"], {"feature": feature, **tip})


@mcp.tool(
    title="Set daily practice routine",
    description=(
        "Save the learner's practice routine (local time HH:MM, days MO..SU, minutes) and return a calendar link (iCalendar, "
        "recurring event with a 5-minute alarm) the household can add to any calendar or reminder app."
    ),
    annotations=ToolAnnotations(idempotent_hint=True),
    meta=UI_META,
)
def set_practice_routine(
    learner_id: LearnerId,
    time_local: Annotated[str, Field(description="Local time, 24h HH:MM (learner timezone)")],
    days: Annotated[list[str] | None, Field(description="Days, e.g. ['MO','WE','FR']; omit for every day")] = None,
    minutes: Annotated[int, Field(ge=5, le=60)] = 10,
) -> CallToolResult:
    r = coach.set_routine(learner_id, time_local, days, minutes)
    base = os.environ.get("SPEAKLOOP_PUBLIC_URL", "").rstrip("/")  # relative to the host page when unset
    r["calendar_url"] = f"{base}/calendar/{learner_id}.ics"
    every = "every day" if len(r["days"].split(",")) == 7 else "on " + ", ".join(r["days"].split(","))
    return _result("routine", f"Done — I'll remind you at {r['time_local']} {every} for {r['minutes']} minutes.", r, learner_id)


# ------------------------------------------------- Sound Graph (FSRS) memory tools + L1 packs
sound_graph = SoundGraph(os.environ.get("SPEAKLOOP_DB", str(ROOT / "speakloop.db")))
register_memory_tools(mcp, sound_graph, meta=UI_META)
register_pronunciation_tools(mcp, sound_graph, meta=UI_META)


# ------------------------------------------------------------------------ resources
@mcp.resource(CARD_URI, name="speakloop-card", title="SpeakLoop card (MCP App)", mime_type=CARD_MIME,
              description="Interactive card that renders every SpeakLoop tool result.")
def card_view() -> str:
    return (Path(__file__).parent / "ui_card.html").read_text(encoding="utf-8")


@mcp.resource("skill://speakloop-coach/SKILL.md", name="speakloop-coach", title="Agent Skill: SpeakLoop coach",
              mime_type="text/markdown", description="Agent Skill (agentskills.io format) with the coaching session flow.")
def skill_md() -> str:
    return (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")


@mcp.resource("skill://speakloop-coach/references/vietnamese-l1-pitfalls.md", name="speakloop-coach-pitfalls",
              mime_type="text/markdown", description="Reference: sound patterns the scorer flags.")
def skill_ref() -> str:
    return (SKILL_DIR / "references" / "vietnamese-l1-pitfalls.md").read_text(encoding="utf-8")


@mcp.prompt(name="daily_session", title="Daily speaking session",
            description="Kick off today's coached session for a learner.")
def daily_session(learner_id: str, minutes: str = "15") -> str:
    return (f"Use the speakloop-coach skill. Learner id: {learner_id}. They have {minutes} minutes. "
            "Greet them with get_learner_profile, then plan_today_session and start the first step.")


# --------------------------------------------------------------------- web + agent
@mcp.custom_route("/", methods=["GET"], include_in_schema=False)
async def index(_: Request) -> Response:
    return FileResponse(WEB_DIR / "index.html")


@mcp.custom_route("/web/{path:path}", methods=["GET"], include_in_schema=False)
async def static(request: Request) -> Response:
    target = (WEB_DIR / request.path_params["path"]).resolve()
    if WEB_DIR not in target.parents or not target.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(target)


@mcp.custom_route("/calendar/{learner_id}.ics", methods=["GET"], include_in_schema=False)
async def calendar(request: Request) -> Response:
    try:
        ics = coach.routine_ics(request.path_params["learner_id"])
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return Response(ics, media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="speakloop-{request.path_params["learner_id"]}.ics"'})


@mcp.custom_route("/healthz", methods=["GET"], include_in_schema=False)
async def healthz(_: Request) -> Response:
    from . import planner as planner_mod

    return JSONResponse({"ok": True, "llm_provider": agent_mod.provider_name(), "planner": planner_mod.status()})


@mcp.custom_route("/agent/step", methods=["POST"], include_in_schema=False)
async def agent_step(request: Request) -> Response:
    body = await request.json()
    try:
        decision = await agent_mod.step(body)
    except Exception as exc:  # surface provider errors to the simulator
        return JSONResponse({"type": "say", "text": f"Sorry, my planner hit an error: {exc}", "provider": agent_mod.provider_name()})
    return JSONResponse(decision)


def build_app(host: str = "127.0.0.1", port: int = 8765):
    allowed = os.environ.get("SPEAKLOOP_ALLOWED_HOSTS", "")
    hosts = [f"127.0.0.1:{port}", f"localhost:{port}", "127.0.0.1", "localhost"] + [h for h in allowed.split(",") if h]
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=not os.environ.get("SPEAKLOOP_DISABLE_HOST_CHECK"),
        allowed_hosts=hosts,
        allowed_origins=[f"http://{h}" for h in hosts],
    )
    return mcp.streamable_http_app(streamable_http_path="/mcp", stateless_http=True, transport_security=security, host=host)


def main() -> None:
    import uvicorn

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8765"))
    print(f"SpeakLoop MCP server: http://{host}:{port}/mcp  ·  simulator: http://{host}:{port}/  ·  planner: {agent_mod.provider_name()}")
    uvicorn.run(build_app(host, port), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
