"""MCP tools over the learner Sound Graph (FSRS) and the L1 skill packs.

``register(mcp, graph)`` adds four tools to any MCPServer:
    get_weak_sounds, next_drill, record_attempt, progress_summary
plus each installed L1 pack as Agent Skill resources (``skill://l1-<code>/SKILL.md`` and
``skill://l1-<code>/pack.json``).

It is mounted on the main SpeakLoop server, and can also run on its own:
    python -m speakloop.memory_tools            # Streamable HTTP on :8766/mcp
"""

# No `from __future__ import annotations`: the SDK resolves tool signatures at runtime and the
# l1 type is built per server from the installed packs (a local name, not a module global).

import json
import os
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from mcp.types import CallToolResult, TextContent, ToolAnnotations

from .memory import SoundGraph

LearnerId = Annotated[str, Field(description="Stable id of the learner.")]


def l1_type(codes: list[str] | tuple[str, ...]) -> tuple[Any, str]:
    """Annotated type for the ``l1`` argument, restricted to the installed pack codes.

    The JSON Schema the client (and the model) sees becomes ``{"enum": [...installed codes]}``
    instead of a free string, so a model cannot invent ``"vietnamese"`` or ``"vn"``.
    Returns ``(type, default)``; the default is ``vi`` when installed, else the first pack.
    With no packs installed it degrades to ``str`` (calls then fail with a clear tool error).
    """
    codes = tuple(sorted(codes))
    if not codes:
        return Annotated[str, Field(description="Learner's first language as an installed pack code (none installed).")], "vi"
    default = "vi" if "vi" in codes else codes[0]
    desc = f"Learner's first language, one of the installed L1 pack codes: {', '.join(codes)}."
    # Always publish an explicit "enum" (pydantic emits "const" for a single-member Literal).
    return Annotated[Literal[codes], Field(description=desc, json_schema_extra={"enum": list(codes)})], default  # type: ignore[valid-type]


class PhoneError(BaseModel):
    """One phone-level error from the pronunciation scorer."""

    op: str = Field(description="delete | substitute | insert")
    target: str | None = Field(None, description="Expected phone in IPA (absent for insert)")
    realized: str | None = Field(None, description="Produced phone in IPA (absent for delete)")
    position: str | None = Field(None, description="onset | coda | nucleus")
    prev: str | None = Field(None, description="Canonical phone before the target")
    next: str | None = Field(None, description="Canonical phone after the target")
    morpheme: str | None = Field(None, description="'-ed' or '-s' when the phone is an inflection")
    word: str | None = Field(None, description="Word the error occurred in")
    sound_id: str | None = Field(None, description="Pre-classified sound id, if the scorer already knows it")


def _result(payload: dict[str, Any]) -> CallToolResult:
    speech = payload.get("speech", "")
    data = {k: v for k, v in payload.items() if k != "speech"}
    return CallToolResult(content=[TextContent(type="text", text=speech + "\n\n" + json.dumps(data, ensure_ascii=False, default=str))],
                          structured_content=payload)


def _err(msg: str) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=msg)], is_error=True)


def register(mcp, graph: SoundGraph, meta: dict | None = None) -> None:
    kw = {"meta": meta} if meta else {}
    L1, L1_DEFAULT = l1_type(list(graph.packs))

    @mcp.tool(title="Get weak sounds",
              description="The learner's weakest English sounds from their Sound Graph (error rate with recency decay, FSRS retrievability, top confusions such as t→∅ or θ→t).",
              annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True), **kw)
    def get_weak_sounds(learner_id: LearnerId, limit: Annotated[int, Field(ge=1, le=12)] = 3, l1: L1 = L1_DEFAULT) -> CallToolResult:
        try:
            return _result(graph.get_weak_sounds(learner_id, limit, l1))
        except KeyError as exc:
            return _err(str(exc))

    @mcp.tool(title="Next sound drill",
              description="Pick the sound to drill now: FSRS-due sounds first (highest priority), else the weakest, else the most common pitfall for the learner's first language. Returns minimal pairs, words, a tip in English and the learner's language.",
              annotations=ToolAnnotations(read_only_hint=True), **kw)
    def next_drill(learner_id: LearnerId, l1: L1 = L1_DEFAULT) -> CallToolResult:
        try:
            return _result(graph.next_drill(learner_id, l1))
        except KeyError as exc:
            return _err(str(exc))

    @mcp.tool(title="Record attempt",
              description="Record one attempt in the Sound Graph. Give either sound_id + correct (a drill result), or the scorer's phone-level errors (each is classified with the L1 pack, counted as a miss and added to the confusion graph), plus optional 'practised' sound ids that were said correctly. Updates the FSRS schedule.",
              annotations=ToolAnnotations(idempotent_hint=False), **kw)
    def record_attempt(
        learner_id: LearnerId,
        sound_id: Annotated[str | None, Field(description="Sound id from the L1 pack, for a direct drill result")] = None,
        correct: Annotated[bool | None, Field(description="Whether the sound was produced correctly (with sound_id)")] = None,
        errors: Annotated[list[PhoneError] | None, Field(description="Phone-level errors from the scorer")] = None,
        practised: Annotated[list[str] | None, Field(description="Sound ids exercised and produced correctly")] = None,
        word: Annotated[str | None, Field(description="Word practised")] = None,
        score: Annotated[float | None, Field(ge=0, le=1, description="Scorer confidence 0-1 (optional)")] = None,
        l1: L1 = L1_DEFAULT,
    ) -> CallToolResult:
        try:
            out = graph.record_attempt(learner_id, sound_id=sound_id, correct=correct,
                                       errors=[e.model_dump(exclude_none=True) for e in errors or []],
                                       practised=practised, word=word, score=score, l1=l1)
        except (KeyError, ValueError) as exc:
            return _err(str(exc))
        misses = [r for r in out["recorded"] if not r["correct"]]
        hits = [r for r in out["recorded"] if r["correct"]]
        if misses:
            s = graph.pack(l1).sound(misses[0]["sound_id"])
            speech = f"Noted: {s['speech_hint']} needs work. {s['tip_en']}"
        elif hits:
            speech = "Nice, that one was clear."
        else:
            speech = "Nothing to record."
        return _result({"kind": "attempt_recorded", **out, "speech": speech})

    @mcp.tool(title="Sound progress summary",
              description="Summary of the learner's sound practice over the last N days: attempts, accuracy, most-improved sounds, sounds mastered (FSRS stability ≥ 21 days) and how many are due.",
              annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True), **kw)
    def progress_summary(learner_id: LearnerId, days: Annotated[int, Field(ge=1, le=90)] = 7, l1: L1 = L1_DEFAULT) -> CallToolResult:
        try:
            return _result(graph.progress_summary(learner_id, days, l1))
        except KeyError as exc:
            return _err(str(exc))

    for code, pack in graph.packs.items():
        _register_pack_resources(mcp, pack)


def _register_pack_resources(mcp, pack) -> None:
    pid = pack.id

    @mcp.resource(f"skill://{pid}/SKILL.md", name=pid, title=f"Agent Skill: {pack.data['l1_name']} L1 sound pack",
                  mime_type="text/markdown", description=f"L1 pack {pid} v{pack.version} (agentskills.io format).")
    def _skill() -> str:
        return (pack.path / "SKILL.md").read_text(encoding="utf-8")

    @mcp.resource(f"skill://{pid}/pack.json", name=f"{pid}-data", title=f"{pid} sound rules",
                  mime_type="application/json", description="Machine-readable sounds, detect rules and drills.")
    def _data() -> str:
        return (pack.path / "pack.json").read_text(encoding="utf-8")


def build_standalone(db_path: str | None = None):
    from mcp.server.mcpserver import MCPServer

    srv = MCPServer(name="speakloop-memory", title="SpeakLoop learner memory",
                    instructions="Per-learner Sound Graph with FSRS scheduling. Use next_drill to choose practice and record_attempt after each try.",
                    version="0.2.0")
    register(srv, SoundGraph(db_path or os.environ.get("SPEAKLOOP_MEMORY_DB", "speakloop-memory.db")))
    return srv


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8766"))
    srv = build_standalone()
    uvicorn.run(srv.streamable_http_app(streamable_http_path="/mcp", stateless_http=True, host="127.0.0.1"),
                host="127.0.0.1", port=port)
