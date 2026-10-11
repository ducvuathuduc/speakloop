"""Vendor the SpeakLoop card UI (feat/ui, ui/src) into src/ui/ so Remotion renders the real components.

The card is Preact; Remotion is React. The transform is mechanical: hooks from "react", `class` ->
`className`, kebab SVG attributes -> camelCase, CSS scoped under `.slui` with transitions off (Remotion
renders frame by frame, so every animation is driven by props instead), and the in-card brand mark
swapped for the /d/ loop mark from feat/brand (assets/brand/logo-mark.svg, commit 9389ba6).
Usage: python3 scripts/vendor_ui.py <speakloop worktree on feat/ui>
"""
import re, subprocess, sys
from pathlib import Path

SRC = Path(sys.argv[1]) / "ui" / "src"
OUT = Path(__file__).resolve().parent.parent / "src" / "ui"
OUT.mkdir(exist_ok=True)
rev = subprocess.run(["git", "-C", str(SRC), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
HEAD = f"// Vendored from speakloop feat/ui@{rev} ui/src by scripts/vendor_ui.py. Do not edit by hand.\n// @ts-nocheck\n"

NEW_BRAND = '''export function Brand() {
  return (
    <span className="brand" aria-label="SpeakLoop">
      <svg className="brand-mark" width="24" height="24" viewBox="0 0 64 64" aria-hidden="true" focusable="false">
        <rect width="64" height="64" rx="15" fill="#FF8A3D" />
        <g fill="none" stroke="#1A1007" strokeWidth="5.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M14 48 L22 16" /><path d="M48.5 15.5 L43.1 33.5 A8.6 8.6 0 1 1 43.1 27" />
        </g>
      </svg>
      <span className="brand-word">SpeakLoop</span>
    </span>
  );
}'''

def jsx(s):
    s = s.replace('from "preact/hooks"', 'from "react"')
    s = re.sub(r'\bclass=', 'className=', s)
    s = re.sub(r'\bclass: cls', 'className: cls', s)
    for a in ["stroke-width", "stroke-linecap", "stroke-linejoin", "stroke-dasharray", "stroke-dashoffset"]:
        camel = re.sub(r'-(\w)', lambda m: m.group(1).upper(), a)
        s = s.replace(a + "=", camel + "=")
    return s

for name in ["components.jsx", "cards.jsx", "model.js", "fixtures.js"]:
    s = (SRC / name).read_text()
    if name.endswith(".jsx"):
        s = jsx(s)
    if name == "components.jsx":
        s = re.sub(r'export function Brand\(\) \{.*?\n\}', NEW_BRAND, s, flags=re.S)
        assert "48.5 15.5" in s
    (OUT / name).write_text(HEAD + s)

# CSS: tokens without @font-face (lib.tsx loads the same OFL fonts), styles scoped to .slui
tok = (SRC / "tokens.css").read_text()
tok = re.sub(r'@font-face\s*\{.*?\}', '', tok, flags=re.S)
tok = tok.replace('[data-theme="light"]', '.slui-light-unused')
css = (SRC / "styles.css").read_text()
css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
css = re.sub(r'@media \(prefers-reduced-motion: reduce\) \{.*?\}\s*\}', '', css, flags=re.S)
out = []
for m in re.finditer(r'([^{}]+)\{([^{}]*)\}', css):
    sels, body = m.group(1).strip(), m.group(2)
    keep = []
    for sel in sels.split(","):
        sel = sel.strip()
        if sel.startswith("html") or sel == "body" or sel.startswith("html,"):
            if sel == "body":
                keep.append(".slui")
            continue
        keep.append(".slui " + sel if not sel.startswith("*") else ".slui " + sel)
    if keep:
        out.append(",\n".join(keep) + " {" + body + "}")
scoped = "\n".join(out)
scoped += "\n.slui *, .slui *::before, .slui *::after { transition: none !important; animation: none !important; }\n"
(OUT / "tokens.css").write_text("/* vendored from feat/ui@%s */\n" % rev + tok)
(OUT / "styles.css").write_text("/* vendored from feat/ui@%s, scoped to .slui */\n" % rev + scoped)
print("vendored", rev, "->", OUT)
