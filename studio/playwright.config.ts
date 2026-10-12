import { defineConfig } from "@playwright/test";

const site = process.env.IMMUKNOW_SITE === "1";
const external = process.env.IMMUKNOW_BASE_URL;
const baseURL = external ?? `http://127.0.0.1:4173/${site ? "studio/" : ""}`;

export default defineConfig({
  testDir: "./tests",
  timeout: 150_000,
  workers: 1,
  use: { baseURL, screenshot: "only-on-failure" },
  webServer: external
    ? undefined
    : {
        command: site
          ? "uv run python -m http.server 4173 --bind 0.0.0.0 --directory ../site"
          : "npm run preview -- --host 0.0.0.0 --port 4173",
        url: `${baseURL}proof.html`,
        reuseExistingServer: false,
      },
});
