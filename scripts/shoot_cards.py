"""Render every card fixture at 768x480 (base canvas, zoom 1) and 1280x800 (Echo Show 8/15, zoom 1.667)
in dark and light mode. Usage: python scripts/shoot_cards.py [outdir] [fixture ...]"""
import os, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
CARD = ROOT / "speakloop" / "ui_card.html"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "design" / "screens"
NAMES = sys.argv[2:] or ["assessment", "karaoke", "rings", "drill", "listen", "mic", "plan"]
EXTRA = {"karaoke": "&t=1.37"}
SIZES = {"768x480": ("web", 768, 480), "1280x800": ("echo-show-8", 1280, 800)}


def chromium_path():
    for p in (os.environ.get("CHROMIUM"), "/usr/bin/chromium", "/usr/bin/chromium-browser"):
        if p and Path(p).exists():
            return p
    return None


def shoot(out=OUT, names=NAMES):
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    with sync_playwright() as pw:
        b = pw.chromium.launch(executable_path=chromium_path(), args=["--force-color-profile=srgb", "--font-render-hinting=none"])
        for size, (device, w, h) in SIZES.items():
            page = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1)
            for name in names:
                for theme in ("dark", "light"):
                    page.goto(f"{CARD.as_uri()}?fixture={name}&theme={theme}&device={device}{EXTRA.get(name, '')}")
                    page.wait_for_function("document.fonts.status === 'loaded'")
                    page.wait_for_timeout(250)
                    p = out / f"{name}-{theme}-{size}.png"
                    page.screenshot(path=str(p))
                    paths.append(p)
            page.close()
        b.close()
    return paths


if __name__ == "__main__":
    for p in shoot():
        print(p)
