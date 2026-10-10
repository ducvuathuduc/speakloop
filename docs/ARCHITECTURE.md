# Architecture and design decisions

## Why an MCP server (and not just a chatbot)
Alexa+ add-ons are MCP integrations. Putting the coaching capability behind MCP means the same server works in
the Alexa+ simulator, in any MCP host (Claude, VS Code, MCP Inspector) and, when the Alexa+ MCP tooling opens up,
on Echo devices — without rewriting the domain logic.

## Protocol choices
- **Spec 2025-11-25, Streamable HTTP**, via the official MCP Python SDK (`MCPServer.streamable_http_app`).
  The browser client sends `protocolVersion: "2025-11-25"` and the server echoes it (tested).
- **Stateless HTTP mode**: no in-memory MCP session is required, so the server can scale horizontally or run in a
  function; learner state is in SQLite keyed by `learner_id` (swap for DynamoDB/RDS in production).
- **DNS-rebinding protection** enabled with an explicit allow-list (`SPEAKLOOP_ALLOWED_HOSTS`).
- Every tool result carries `structuredContent` (machine-readable, with `kind` and a `speech` line) **and** a text
  block (speech + JSON) for hosts that ignore structured output.
- Tool annotations (`readOnlyHint`, `idempotentHint`) let a host auto-approve safe calls.

## Voice-first design rules
- One or two spoken sentences per turn; the card carries detail.
- Audio-only tasks (Repeat Sentence, Answer Short Question) are *spoken* by the device, never displayed — the tool
  returns `speak_text` and `display_text: null` so a host can't leak the answer on screen.
- Feedback names **one** fix, with up to two example words heard wrong.
- Bilingual tips (English + Vietnamese) on screen only, so speech stays short.

## MCP App (ui://speakloop/card.html)
One self-contained HTML view renders every `kind` (profile, plan, drill, result, review, progress, tip). It speaks
the MCP Apps postMessage dialect directly (no framework): `ui/initialize` → `ui/notifications/initialized`,
listens for `ui/notifications/tool-result`, reports `ui/notifications/size-changed`, and issues `tools/call`
through the host for its buttons. The simulator's host bridge (`web/mcp-client.js::AppBridge`) renders it in an
`allow-scripts`-only sandboxed iframe and proxies tool calls to the MCP server.

## Agent Skill
`skills/speakloop-coach/SKILL.md` follows the Agent Skills format (YAML front matter `name`, `description`, then
instructions) with a `references/` file. It is served over MCP as resources (`skill://speakloop-coach/SKILL.md`),
matching the URI convention of the MCP Skills extension (SEP-2640) while staying compatible with 2025-11-25
clients that only know `resources/read`. LLM planners load it as their system prompt at runtime.

## Agent loop and guardrail
The browser owns the conversation and executes tool calls; `/agent/step` is a stateless "what next?" planner so
providers can be swapped without touching the client. While a drill is active, the next utterance is always sent
to `submit_attempt` unchanged (`agent.guardrail`) — LLMs like to fix grammar, which would hide the very errors
being coached.

## Coaching logic (state across sessions)
- **Attempts** table: every scored attempt with its weak features.
- **Spaced repetition**: a mispronounced word enters `review_items` due tomorrow; a correct review grows the
  interval (1 → ×ease days); a lapse resets it and lowers ease (SM-2-style).
- **Plan**: due reviews first, then task types ordered by average score, sized to the minutes available; the most
  frequent weak sound becomes the session focus and steers drill selection.
- **Streaks** and **days-to-exam** shape the greeting and plan intensity.

## Scoring
See `speakloop/scoring.py`. It is deliberately deterministic and explainable: judges and learners can see which
word triggered which rule. The pronunciation proxy relies on how ASR mis-hears dropped sounds; an acoustic
model (e.g. phoneme-level scoring) is the natural next step.
