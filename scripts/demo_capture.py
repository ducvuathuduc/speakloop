"""Drive the simulator headlessly and save a screenshot per demo beat.

Usage: python scripts/demo_capture.py http://127.0.0.1:8765 out_dir [chromium_path]
"""
import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

URL, OUT = sys.argv[1], Path(sys.argv[2])
CHROME = sys.argv[3] if len(sys.argv) > 3 else None
OUT.mkdir(parents=True, exist_ok=True)

# (label, utterance or callable key, spoken-duration seconds for attempts)
BEATS = [
    ("01_greet", "Hi", None),
    ("02_plan", "Let's practise for 10 minutes", None),
    ("03_review", "Yes", None),
    ("04_review_result", "@review_words", 4.0),
    ("05_drill", "Yes", None),
    ("06_attempt", "@attempt_with_slips", None),
    ("07_progress", "How am I doing?", None),
]


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        page = await browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        await page.goto(URL)
        await page.wait_for_function("document.getElementById('status').textContent.includes('MCP 2025-11-25')", timeout=15000)
        await page.uncheck("#tts")
        await page.screenshot(path=str(OUT / "00_connected.png"))
        log = []
        for label, utter, secs in BEATS:
            if utter == "@review_words":
                words = await page.evaluate("[...window.speakloop.session.messages].reverse().find(m=>m.role==='tool').result.items.map(i=>i.word).join(' ')")
                utter = words
            elif utter == "@attempt_with_slips":
                ref = await page.evaluate("""(() => { const r=[...window.speakloop.session.messages].reverse().find(m=>m.role==='tool').result; return r.display_text || r.speak_text || ''; })()""")
                # Simulate a typical learner: drop a few -s / -ed endings and one TH.
                import re
                words = ref.split()
                out = []
                for i, w in enumerate(words):
                    core = re.sub(r"[^A-Za-z']", "", w)
                    lw = core.lower()
                    if i % 3 == 0 and lw.endswith("ed") and len(lw) > 4:
                        w = w.replace(core, core[:-2])
                    elif i % 2 == 0 and lw.endswith("s") and len(lw) > 4 and not lw.endswith("ss"):
                        w = w.replace(core, core[:-1])
                    elif lw.startswith("th") and lw not in ("the", "that", "they", "this", "there", "their", "than", "then"):
                        w = w.replace(core, "t" + core[2:])
                    out.append(w)
                utter = " ".join(out)
                secs = round(len(out) / 2.3, 1)
            await page.evaluate("([t, d]) => window.speakloop.userSay(t, d)", [utter, secs])
            await page.wait_for_timeout(1800)
            await page.screenshot(path=str(OUT / f"{label}.png"))
            last = await page.evaluate("[...document.querySelectorAll('.bubble.assistant')].map(b=>b.textContent).slice(-1)[0] || ''")
            log.append({"beat": label, "said": utter, "assistant": last})
            print(label, "|", utter[:60], "->", last)
        (OUT / "beats.json").write_text(json.dumps(log, indent=2, ensure_ascii=False))
        await browser.close()

asyncio.run(main())
