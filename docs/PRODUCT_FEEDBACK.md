# Product feedback (for the Devpost "Product Feedback" field)

## Model Context Protocol — spec 2025-11-25, Streamable HTTP (Alexa+ track requirement)
- **Used for:** the SpeakLoop server (9 tools, 3 resources, 1 prompt) and the browser client in the simulator.
- **Worked well:** Streamable HTTP is just POST + JSON/SSE, so a dependency-free browser client was ~150 lines;
  the spec pages for transports and lifecycle are precise.
- **Needs work:** the hackathon requires 2025-11-25 "or later once confirmed" while the current SDKs already
  default to 2026-07-28 — we had to read SDK source to confirm the handshake still negotiates 2025-11-25. A short
  "which version should Alexa+ add-ons target" note would save time.
- **Onboarding:** zero → first tool call over HTTP in under an hour with the Python SDK.
- **Build again?** Yes — one server reaches Alexa+, desktop assistants and IDEs.

## MCP Python SDK (`mcp` 2.3.0)
- **Used for:** `MCPServer`, tool/resource/prompt decorators, `streamable_http_app`, `Client` in tests.
- **Worked well:** typed tool signatures → JSON Schema; `structured_content`; `custom_route` let us serve the
  simulator from the same app; the in-repo `Client("http://…/mcp")` made an end-to-end test trivial.
- **Needs work:** v2 moved several APIs (the high-level server is now `MCPServer`, result fields are snake_case in Python); many tutorials
  still show v1. Default stateless JSON vs SSE response behaviour is not obvious from docs.
- **Build again?** Yes.

## MCP Apps (SEP-1865, spec 2026-01-26)
- **Used for:** the on-screen card (`ui://speakloop/card.html`, `text/html;profile=mcp-app`) and a minimal host bridge.
- **Worked well:** the postMessage dialect is small; one HTML file can serve every tool.
- **Needs work:** the only host reference is the TypeScript `basic-host`; a vanilla-JS host snippet in the spec
  would help builders who need to *host* apps (every Alexa+ simulator does). How an Alexa+ device will render MCP
  Apps (voice + screen, Echo Show sizes) is undocumented.
- **Build again?** Yes — it is the natural replacement for APL-style cards in an MCP world.

## Agent Skills (agentskills.io format)
- **Used for:** `skills/speakloop-coach/SKILL.md`, served over MCP and used as the planner system prompt.
- **Needs work:** for 2025-11-25 servers there is no standard discovery (the Skills extension's `skills/list` is
  2026-07-28+), so we exposed `skill://` resources; guidance on what judges/Alexa+ expect would help.

## Amazon Bedrock — Converse API with tool use (AWS Builder)
- **Used for:** the optional LLM planner (`SPEAKLOOP_LLM=bedrock`).
- **Worked well:** Converse's `toolSpec.inputSchema.json` accepts MCP tool schemas as-is, so the MCP → Bedrock
  bridge is a few lines.
- **Needs work:** no offline emulator (as the FAQ says) — we stubbed the client in tests; hackathon credit codes
  ran out on Oct 7, which makes live testing harder for late starters.
- **Build again?** Yes.

## Alexa+ developer tooling
- The Alexa+ Add-on SDK / MCP Toolkit / Web Simulator are partner-only; individual setup pages don't always say so
  (the FAQ confirms this). A public Alexa+ simulator that can point at a self-hosted MCP URL would let every
  entrant demo on the real experience.
