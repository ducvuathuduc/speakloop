// MCP Apps view-side bridge (SEP-1865, spec 2026-01-26).
// postMessage is the only channel to the host. No window.parent property access, no storage.

export function createBridge({ onToolResult, onToolInput, onHostContext, target } = {}) {
  let nextId = 1;
  const pending = new Map();
  const host = target || (typeof window !== "undefined" ? window.parent : null);
  const embedded = !!host && host !== window;
  const state = { hostContext: {}, hostCapabilities: {}, initialized: false };

  const post = (msg) => { if (embedded) host.postMessage(msg, "*"); };
  const request = (method, params) => new Promise((resolve, reject) => {
    if (!embedded) return reject(new Error("not embedded in an MCP Apps host"));
    const id = nextId++;
    pending.set(id, { resolve, reject });
    post({ jsonrpc: "2.0", id, method, params });
  });
  const notify = (method, params) => post({ jsonrpc: "2.0", method, params });

  function onMessage(ev) {
    const m = ev.data;
    if (!m || m.jsonrpc !== "2.0") return;
    if (m.id != null && !m.method && pending.has(m.id)) {
      const p = pending.get(m.id); pending.delete(m.id);
      m.error ? p.reject(Object.assign(new Error(m.error.message || "host error"), m.error)) : p.resolve(m.result);
      return;
    }
    switch (m.method) {
      case "ui/notifications/tool-result":
        onToolResult?.(m.params || {});
        break;
      case "ui/notifications/tool-input":
        onToolInput?.(m.params || {});
        break;
      case "ui/notifications/host-context-changed":
        state.hostContext = { ...state.hostContext, ...(m.params || {}) };
        onHostContext?.(state.hostContext);
        break;
      default:
        if (m.id != null && m.method) post({ jsonrpc: "2.0", id: m.id, error: { code: -32601, message: `Unsupported: ${m.method}` } });
    }
  }

  async function initialize() {
    if (typeof window !== "undefined") window.addEventListener("message", onMessage);
    if (!embedded) return state;
    const res = await request("ui/initialize", {
      protocolVersion: "2026-01-26",
      appInfo: { name: "speakloop-card", version: "0.2.0" },
      appCapabilities: { availableDisplayModes: ["inline", "fullscreen"] },
    });
    state.hostContext = res?.hostContext || {};
    state.hostCapabilities = res?.hostCapabilities || {};
    state.initialized = true;
    onHostContext?.(state.hostContext);
    notify("ui/notifications/initialized", {});
    return state;
  }

  return {
    state,
    embedded,
    initialize,
    request,
    notify,
    callTool: (name, args) => request("tools/call", { name, arguments: args || {} }),
    openLink: (url) => request("ui/open-link", { url }),
    canFullscreen: () => (state.hostContext.availableDisplayModes || []).includes("fullscreen"),
    requestDisplayMode: (mode) => request("ui/request-display-mode", { mode }),
    micGranted: () => !!state.hostCapabilities?.sandbox?.permissions?.microphone,
    sizeChanged: (height, width) => notify("ui/notifications/size-changed", { height, width }),
    dispose: () => typeof window !== "undefined" && window.removeEventListener("message", onMessage),
  };
}
