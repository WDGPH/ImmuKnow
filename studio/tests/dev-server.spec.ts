import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";
import { createServer } from "vite";

test("the dev worker loads its data checks under a proxy path and renders despite extra coverage", async ({ page }) => {
  const previous = process.env.IMMUKNOW_DEV_PROXY_BASE;
  const prefix = "/notebook/test/proxy/5173/";
  process.env.IMMUKNOW_DEV_PROXY_BASE = prefix;
  const server = await createServer({
    root: fileURLToPath(new URL("../", import.meta.url)),
    configFile: fileURLToPath(new URL("../vite.config.ts", import.meta.url)),
    server: { host: "127.0.0.1", port: 0, open: false },
  });
  try {
    await server.listen();
    const address = server.httpServer?.address();
    if (!address || typeof address === "string") throw new Error("No dev server address");
    await page.goto(`http://127.0.0.1:${address.port}${prefix}`);
    await expect(page.locator(".preview-page canvas")).toHaveCount(2, { timeout: 60_000 });
      await expect(page.locator("#diagnostics .error")).toHaveCount(0);
  } finally {
    await server.close();
    if (previous === undefined) delete process.env.IMMUKNOW_DEV_PROXY_BASE;
    else process.env.IMMUKNOW_DEV_PROXY_BASE = previous;
  }
});
