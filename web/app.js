// SpeakLoop — Alexa+ experience simulator.
// The page is a real MCP client: it negotiates MCP 2025-11-25 over Streamable HTTP,
// lists tools, loads the Agent Skill and MCP App resources, and executes every tool call.
// A pluggable planner (/agent/step: rules | Amazon Bedrock | OpenAI-compatible) decides the next step.
import { McpHttpClient, AppBridge } from "./mcp-client.js";

const $ = (id) => document.getElementById(id);
const SKILL_URI = "skill://speakloop-coach/SKILL.md";

const ui = {
  status: $("status"), conversation: $("conversation"), traffic: $("traffic"), tools: $("tools"),
  skill: $("skill"), planner: $("planner"), card: $("card"), lightbar: $("lightbar"),
  learner: $("learner"), tts: $("tts"), voice: $("voice"),
};

const session = { messages: [], tools: [], skill: "", cardHtml: {}, state: { active_drill_id: null, plan_steps: null, step_index: 0 } };
let busy = false;

// ------------------------------------------------------------------ traffic inspector
function logTraffic(dir, msg) {
  const li = document.createElement("li");
  li.className = dir;
  const label = msg.method || (msg.error ? "error" : "result");
  const short = msg.method === "tools/call" ? ` ${msg.params.name}` : msg.method === "resources/read" ? ` ${msg.params.uri}` : "";
  li.innerHTML = `<details><summary><span class="dir">${dir === "out" ? "→" : "←"}</span>${label}${short}${msg.id !== undefined ? ` <span class="muted">#${msg.id}</span>` : ""}</summary></details>`;
  const pre = document.createElement("pre");
  pre.textContent = JSON.stringify(msg, null, 2).slice(0, 4000);
  li.querySelector("details").appendChild(pre);
  ui.traffic.appendChild(li);
  ui.traffic.parentElement.scrollTop = ui.traffic.parentElement.scrollHeight;
}

const client = new McpHttpClient("/mcp", { protocolVersion: "2025-11-25", clientInfo: { name: "speakloop-alexa-sim", version: "1.0.0" }, onTraffic: logTraffic });

const bridge = new AppBridge(ui.card, {
  client,
  hostInfo: { name: "speakloop-alexa-sim", version: "1.0.0" },
  onSize: (h) => { if (h) ui.card.style.height = Math.min(Math.max(h + 8, 160), 900) + "px"; },
  onToolResult: (name, args, result) => {
    // A button inside the MCP App called a tool: keep the agent's context in sync and speak the outcome.
    const id = `app-${Date.now()}`;
    session.messages.push({ role: "assistant", tool_call: { id, name, arguments: args } });
    session.messages.push({ role: "tool", tool_call_id: id, name, result: result.structuredContent || {} });
    afterTool(name, result, { fromApp: true });
  },
});

// ------------------------------------------------------------------ speech
const synth = window.speechSynthesis;
function loadVoices() {
  if (!synth) return;
  const voices = synth.getVoices().filter((v) => v.lang.startsWith("en"));
  ui.voice.innerHTML = voices.map((v, i) => `<option value="${i}">${v.name}</option>`).join("");
  const pref = voices.findIndex((v) => /female|samantha|aria|jenny|google us/i.test(v.name));
  if (pref >= 0) ui.voice.value = String(pref);
}
if (synth) { loadVoices(); synth.onvoiceschanged = loadVoices; }

function speak(text, { rate = 1.0 } = {}) {
  return new Promise((resolve) => {
    if (!text || !ui.tts.checked || !synth) return resolve();
    const u = new SpeechSynthesisUtterance(text);
    const voices = synth.getVoices().filter((v) => v.lang.startsWith("en"));
    if (voices[+ui.voice.value]) u.voice = voices[+ui.voice.value];
    u.rate = rate;
    setLight("speaking");
    u.onend = u.onerror = () => { setLight(""); resolve(); };
    synth.speak(u);
  });
}

function setLight(mode) { ui.lightbar.className = "lightbar " + (mode || ""); }

function bubble(role, text) {
  const div = document.createElement("div");
  div.className = `bubble ${role}`;
  div.textContent = text;
  ui.conversation.appendChild(div);
  ui.conversation.scrollTop = ui.conversation.scrollHeight;
}

// ------------------------------------------------------------------ cards (MCP Apps)
async function renderCard(toolName, args, result) {
  const tool = session.tools.find((t) => t.name === toolName);
  const uri = tool?._meta?.ui?.resourceUri;
  if (!uri || !result.structuredContent) return;
  if (!session.cardHtml[uri]) {
    const res = await client.readResource(uri);
    session.cardHtml[uri] = res.contents[0].text;
  }
  bridge.load(session.cardHtml[uri]);
  bridge.sendToolInput(args);
  bridge.sendToolResult(result);
}

// ------------------------------------------------------------------ state + agent loop
function updateState(sc) {
  const s = session.state;
  if (!sc) return;
  if (sc.kind === "plan") { s.plan_steps = sc.steps; s.step_index = 0; }
  if ((sc.kind === "drill" || sc.kind === "review") && sc.drill_id) {
    s.active_drill_id = sc.drill_id;
    s.drill_started_at = performance.now();
    if (s.plan_steps) s.step_index = Math.min(s.step_index + 1, s.plan_steps.length);
  }
  if (sc.kind === "result") s.active_drill_id = null;
}

async function afterTool(name, result, { fromApp = false } = {}) {
  const sc = result.structuredContent;
  updateState(sc);
  await renderCard(name, {}, result);
  if (fromApp && sc?.speech) { bubble("assistant", sc.speech); await speak(sc.speech); }
  if (fromApp && sc?.speak_text) await speak(sc.speak_text, { rate: 0.92 });
}

async function plannerStep() {
  const res = await fetch("/agent/step", {
    method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ messages: session.messages, tools: session.tools, skill: session.skill, learner_id: ui.learner.value.trim() || "demo", state: session.state }),
  });
  const decision = await res.json();
  ui.planner.textContent = `planner: ${decision.provider || "?"}${decision.reason ? " · " + decision.reason : ""}`;
  return decision;
}

async function userSay(text, durationSeconds) {
  if (!text.trim() || busy) return;
  busy = true;
  bubble("user", text);
  const msg = { role: "user", content: text };
  if (durationSeconds) msg.duration_seconds = durationSeconds;
  session.messages.push(msg);
  try {
    for (let hop = 0; hop < 4; hop++) {
      setLight("thinking");
      const d = await plannerStep();
      if (d.type === "tool_call") {
        const id = d.id || `call-${Date.now()}-${hop}`;
        session.messages.push({ role: "assistant", tool_call: { id, name: d.name, arguments: d.arguments } });
        bubble("tool", `⚙ ${d.name}(${JSON.stringify(d.arguments)})`);
        let result;
        try { result = await client.callTool(d.name, d.arguments); }
        catch (e) { result = { isError: true, content: [{ type: "text", text: e.message }], structuredContent: { speech: "Sorry, that didn't work." } }; }
        session.messages.push({ role: "tool", tool_call_id: id, name: d.name, result: result.structuredContent || { text: result.content?.[0]?.text }, is_error: !!result.isError });
        updateState(result.structuredContent);
        await renderCard(d.name, d.arguments, result);
        continue;
      }
      setLight("");
      session.messages.push({ role: "assistant", content: d.text });
      bubble("assistant", d.text);
      await speak(d.text);
      // Audio-only prompts (Repeat Sentence, Answer Short Question, review) are spoken, never shown.
      const lastTool = [...session.messages].reverse().find((m) => m.role === "tool");
      if (lastTool?.result?.speak_text && session.state.active_drill_id) await speak(lastTool.result.speak_text, { rate: 0.92 });
      break;
    }
  } finally { setLight(""); busy = false; }
}

// ------------------------------------------------------------------ input: mic + text
const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
let rec = null, recStart = 0, firstSpeech = 0;
$("mic").addEventListener("click", () => {
  if (!Recognition) { alert("Speech recognition needs Chrome or Edge. You can type instead."); return; }
  if (rec) { rec.stop(); return; }
  rec = new Recognition();
  rec.lang = "en-US"; rec.interimResults = false; rec.maxAlternatives = 1;
  recStart = performance.now(); firstSpeech = 0;
  rec.onspeechstart = () => { firstSpeech = performance.now(); };
  rec.onresult = (ev) => {
    const text = Array.from(ev.results).map((r) => r[0].transcript).join(" ");
    const dur = (performance.now() - (firstSpeech || recStart)) / 1000;
    userSay(text, Math.round(dur * 10) / 10);
  };
  rec.onend = () => { rec = null; $("mic").classList.remove("on"); setLight(""); };
  rec.start(); $("mic").classList.add("on"); setLight("listening");
});

function typedDuration(text) {
  // Typed demo input: estimate speaking time at ~145 words/min so fluency maths still applies.
  const words = text.trim().split(/\s+/).length;
  return Math.round((words / 145) * 60 * 10) / 10;
}

$("say-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const text = $("say").value; $("say").value = "";
  userSay(text, session.state.active_drill_id ? typedDuration(text) : undefined);
});
document.querySelectorAll("[data-say]").forEach((b) => b.addEventListener("click", () => {
  const t = b.dataset.say;
  userSay(t, session.state.active_drill_id ? typedDuration(t) : undefined);
}));
document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => {
  document.querySelectorAll(".tab, .pane").forEach((x) => x.classList.remove("active"));
  t.classList.add("active"); $("pane-" + t.dataset.tab).classList.add("active");
}));

// Expose a tiny hook for automated demos/tests (e.g. Playwright recording).
window.speakloop = { userSay, session, client };

// ------------------------------------------------------------------ boot
(async () => {
  try {
    const init = await client.connect();
    ui.status.textContent = `connected · ${init.serverInfo.name} · MCP ${client.negotiatedVersion}`;
    ui.status.classList.add("ok");
    session.tools = (await client.listTools()).tools;
    ui.tools.innerHTML = session.tools.map((t) => `<div class="tool"><b>${t.name}</b>${t._meta?.ui ? ` <span class="ui">MCP App: ${t._meta.ui.resourceUri}</span>` : ""}<div class="muted">${t.description}</div></div>`).join("");
    const skill = await client.readResource(SKILL_URI);
    session.skill = skill.contents[0].text;
    ui.skill.textContent = session.skill;
  } catch (e) {
    ui.status.textContent = "connection failed: " + e.message;
  }
})();
