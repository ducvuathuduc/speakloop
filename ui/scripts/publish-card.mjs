// Copy the single-file build into the Python package and record its content hash.
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const html = readFileSync(join(here, "../dist/index.html"), "utf8");
const pkg = join(here, "../../speakloop");
writeFileSync(join(pkg, "ui_card.html"), html);
const hash = createHash("sha256").update(html).digest("hex").slice(0, 12);
writeFileSync(join(pkg, "ui_card.sha"), hash + "\n");
console.log(`speakloop/ui_card.html  ${(html.length / 1024).toFixed(1)} KiB  sha ${hash}`);
