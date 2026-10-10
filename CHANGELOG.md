# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/ducvuathuduc/speakloop/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ducvuathuduc/speakloop/releases/tag/v0.1.0
