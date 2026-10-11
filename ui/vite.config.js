import { defineConfig } from "vite";
import preact from "@preact/preset-vite";
import { viteSingleFile } from "vite-plugin-singlefile";

// One self-contained HTML bundle (Alexa+ Layout & Rendering: "Ship as one self-contained bundle").
export default defineConfig({
  plugins: [preact(), viteSingleFile({ removeViteModuleLoader: true })],
  build: { target: "es2020", assetsInlineLimit: 100_000_000, cssCodeSplit: false, outDir: "dist", emptyOutDir: true },
  test: { environment: "jsdom", include: ["test/**/*.test.{js,jsx}"] },
});
