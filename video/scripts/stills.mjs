// Usage: node scripts/stills.mjs <compId> <outDir> <frame> [frame...]
import { bundle } from "@remotion/bundler";
import { renderStill, selectComposition, openBrowser } from "@remotion/renderer";
import path from "node:path";
const [comp, outDir, ...frames] = process.argv.slice(2);
const serveUrl = await bundle({ entryPoint: path.resolve("src/index.ts") });
const browser = await openBrowser("chrome", { chromiumOptions: { gl: "swangle" } });
const composition = await selectComposition({ serveUrl, id: comp, puppeteerInstance: browser });
for (const fr of frames) {
  const t = Date.now();
  await renderStill({ composition, serveUrl, frame: Number(fr), output: path.join(outDir, `f${String(fr).padStart(4, "0")}.png`), puppeteerInstance: browser });
  console.log("still", fr, Date.now() - t, "ms");
}
await browser.close({ silent: true });
console.log("DONE");
