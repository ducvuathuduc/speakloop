import { render } from "preact";
import "./tokens.css";
import "./styles.css";
import { App } from "./app.jsx";
import { FIXTURES } from "./fixtures.js";

// Standalone (not inside an MCP Apps host): ?fixture=<name>&theme=light|dark&device=echo-show-8&t=1.0
// powers the design gallery, Playwright screenshots and visual-regression tests.
const params = new URLSearchParams(location.search);
const embedded = window.parent !== window;
const name = params.get("fixture") || (embedded ? null : "assessment");
const initial = name ? FIXTURES[name] : null;
if (!embedded) document.documentElement.dataset.standalone = "true";
render(<App initial={initial} params={params} />, document.getElementById("app"));
