"""Run the Strands planner against a local llama.cpp model and record the decisions.

Usage (llama-server must already be listening):
    SPEAKLOOP_LOCAL_LLM_URL=http://127.0.0.1:8088 python scripts/local_planner_smoke.py out.json
No Bedrock call is made: tiers are forced to "local,rules".
"""
import asyncio, json, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["SPEAKLOOP_TIERS"] = "local,rules"
from speakloop import planner  # noqa: E402

TOOLS = [
    {"name": "progress_report", "description": "Show the learner's progress over the last 14 days.",
     "inputSchema": {"type": "object", "properties": {"learner_id": {"type": "string"}}, "required": ["learner_id"]}},
    {"name": "next_drill", "description": "Pick the English sound to drill now from the learner's Sound Graph (FSRS spaced repetition).",
     "inputSchema": {"type": "object", "properties": {"learner_id": {"type": "string"}, "l1": {"type": "string"}}, "required": ["learner_id"]}},
    {"name": "plan_today_session", "description": "Build today's practice plan sized to the minutes available.",
     "inputSchema": {"type": "object", "properties": {"learner_id": {"type": "string"}, "minutes": {"type": "integer"}}, "required": ["learner_id"]}},
]
SKILL = "You are SpeakLoop, an English pronunciation coach on a voice assistant. Use exactly one tool when the learner asks for something a tool does."
CASES = [
    "How am I doing this week?",
    "Which sound should I practise now?",
    "I have 10 minutes, let's practise.",
]

async def main(out):
    rows = []
    for text in CASES:
        body = {"learner_id": "demo", "skill": SKILL, "tools": TOOLS, "messages": [{"role": "user", "content": text}]}
        t0 = time.time()
        d = await planner.plan(body)
        rows.append({"utterance": text, "decision": {k: d.get(k) for k in ("type", "name", "arguments", "text", "provider")},
                     "trace": d.get("trace"), "seconds": round(time.time() - t0, 1)})
        print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    Path(out).write_text(json.dumps({"model": os.environ.get("SPEAKLOOP_LOCAL_MODEL", "qwen2.5-1.5b-instruct-q4_k_m"),
                                     "server": "llama.cpp llama-server b11552 (CPU, 2 threads)", "runs": rows}, indent=2, ensure_ascii=False))

asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "local_planner_smoke.json"))
