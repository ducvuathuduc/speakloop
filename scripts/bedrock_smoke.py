"""One tiny live Amazon Bedrock Converse call (tool use) to prove the integration.

Usage:  AWS_BEARER_TOKEN_BEDROCK=... python scripts/bedrock_smoke.py [model_id]
Prints the planner decision for "how am I doing?" given SpeakLoop's real tool list + Agent Skill.
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from speakloop import agent  # noqa: E402

if len(sys.argv) > 1:
    os.environ["BEDROCK_MODEL_ID"] = sys.argv[1]
os.environ.setdefault("BEDROCK_MODEL_ID", "amazon.nova-micro-v1:0")
skill = (Path(__file__).resolve().parent.parent / "skills/speakloop-coach/SKILL.md").read_text()
tools = [{"name": "progress_report", "description": "Show the learner's practice estimate trend and weak sounds.",
          "inputSchema": {"type": "object", "properties": {"learner_id": {"type": "string"}}, "required": ["learner_id"]}},
         {"name": "start_drill", "description": "Start one speaking drill.",
          "inputSchema": {"type": "object", "properties": {"learner_id": {"type": "string"}, "task_type": {"type": "string"}}, "required": ["learner_id"]}}]
body = {"learner_id": "lan", "skill": skill, "tools": tools, "messages": [{"role": "user", "content": "How am I doing?"}]}
t = time.time()
decision = agent.bedrock_step(body)
print(json.dumps({"model": os.environ["BEDROCK_MODEL_ID"], "latency_s": round(time.time() - t, 2), "decision": decision}, indent=2))
