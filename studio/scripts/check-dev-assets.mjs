import { existsSync } from "node:fs";

const root = new URL("../", import.meta.url);
const required = [
  "public/generated/project.json",
  "public/generated/build.json",
  "public/generated/fonts/manifest.json",
  "vendor/compiler/typst_ts_web_compiler.js",
  "vendor/compiler/typst_ts_web_compiler_bg.wasm",
  "vendor/renderer/typst_ts_renderer.js",
  "vendor/renderer/typst_ts_renderer_bg.wasm",
];
const missing = required.filter((path) => !existsSync(new URL(path, root)));
if (missing.length) {
  console.error(
    `Studio needs generated assets before Vite can start. Missing:\n${missing.join("\n")}\n\n` +
      "From the repository root, install the build prerequisites in\n" +
      "docs/developer_guide/testing.md, then run:\n" +
      "  uv run python -m studio.scripts.build-site\n\n" +
      "npm run dev does not install build tools or prepare these assets automatically.",
  );
  process.exitCode = 1;
}
