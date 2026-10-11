# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-10-11

### Added
- **Phone-level pronunciation scoring** (`speakloop/phoneme/`): open wav2vec2 espeak-phoneme CTC model, espeak-ng
  G2P, CTC forced alignment and goodness-of-pronunciation per phone, weak forms for function words, per-phone
  thresholds tuned on L2-ARCTIC dev speakers (false alarms capped at 15 %). Optional install
  (`requirements-phoneme.txt`).
- **Benchmark** (`benchmarks/`): L2-ARCTIC Vietnamese speakers, held-out THV + TLV. On the same 100 utterances the
  scorer reaches P 0.59 / R 0.53 / F1 0.56 vs 0.62 / 0.22 / 0.32 for a Whisper-small transcript diff; latency and
  memory in `benchmarks/LATENCY.md`.
- MCP tools **`assess_pronunciation`** (reference text + base64 WAV → phones, words, L1 findings; records misses in
  the Sound Graph) and **`start_pair_drill`** (minimal pairs for a finding, a sound, or the FSRS-due sound).
- **Sound Graph** (`speakloop/memory.py`): per-learner, per-sound FSRS scheduling and a confusion graph, with tools
  `get_weak_sounds`, `next_drill`, `record_attempt`, `progress_summary`.
- **L1 sound packs** as Agent Skills: `skills/l1-vi/` (SKILL.md + `pack.json` + `rules.yaml`), `skills/l1-template/`,
  `python -m speakloop.skillpacks validate|install|list`; packs are served as `skill://l1-<code>/…` resources.
- **Strands Agents tiered planner** (`speakloop/planner.py`): Bedrock → local llama.cpp → rules, with circuit breakers.
- **MCP App card rebuilt** in Preact/Vite (`ui/`) on Alexa+ design tokens: transcript-vs-sounds split, karaoke phone
  strip, weak-sound rings, minimal-pair drill, mic capture; 17 vitest tests.
- **Brand kit** (`assets/brand/`), README hero, feature strip and architecture diagram.
- CI: espeak-ng on the pytest matrix, a vitest job, simulator script syntax check.

### Changed
- `SPEAKLOOP_LLM` defaults to `auto` (falls back to the offline rules router when no model tier is configured).
- The two Vietnamese skills (`skills/speakloop-l1-vietnamese/` and `skills/l1-vi/`) are now one canonical
  `skills/l1-vi/`; each rule in `rules.yaml` links its Sound Graph node.
- Base requirements add `fsrs`, `numpy` and `pyyaml`.

## [0.1.0] - 2026-10-11

First public release, built for the Alexa+ track of *Build, Ship, Shape: Amazon Developer Hackathon 2026*.

### Added
- Self-hosted **MCP server** (official MCP Python SDK `mcp==2.3.0`) over Streamable HTTP, negotiating protocol
  version `2025-11-25`, stateless mode, DNS-rebinding protection.
- **9 tools**: `get_learner_profile`, `set_goal`, `plan_today_session`, `start_drill`, `submit_attempt`,
  `start_sound_review`, `progress_report`, `explain_sound`, `set_practice_routine`.
- **MCP App** `ui://speakloop/card.html` (`text/html;profile=mcp-app`) with buttons that call tools back through the host.
- **Agent Skill** `skills/speakloop-coach/SKILL.md`, served as `skill://` resources; `daily_session` prompt.
- Explainable **scorer** (content, fluency, pronunciation proxy for Vietnamese-L1 patterns) and SQLite **learner
  memory** with streaks, plans and spaced repetition; 20 original drills; bilingual (EN/VI) tips.
- **Alexa+ experience simulator** (`web/`): a real MCP client with voice in/out and an MCP traffic inspector.
- Planners: offline rules (default), **Amazon Bedrock Converse** with tool use (bearer API key or AWS credential
  chain), OpenAI-compatible; verbatim-transcript guardrail and throttle circuit breaker.
- iCalendar practice routine (`/calendar/{learner_id}.ics`).
- Narrated demo video (`assets/speakloop-demo.mp4`, 2:49) and README GIFs.
- 33 pytest tests including a real Streamable HTTP round trip and the official SDK client; GitHub Actions CI on
  Python 3.11, 3.12 and 3.13.
- Docs: architecture, AWS setup, friction log, product feedback, feature requests; contributing guide, code of
  conduct, security policy, issue and PR templates.

### Known limitations
- Live Amazon Bedrock calls from the author's new AWS account return `429 Too many tokens per day`; the demo uses
  the offline planner.
- Not tested on a physical Alexa+ device (add-on tooling is partner-only).

[Unreleased]: https://github.com/ducvuathuduc/speakloop/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/ducvuathuduc/speakloop/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/ducvuathuduc/speakloop/releases/tag/v0.1.0
