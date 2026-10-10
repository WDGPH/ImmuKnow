import { expect, test } from "@playwright/test";

const prefix = (process.env.IMMUKNOW_PROXY_PREFIX ?? "").replace(/\/+$/, "");
test("proxy prefix is retained by editor, worker, font, WASM and PDF requests", async ({
  page,
  context,
}) => {
  test.skip(!prefix, "Build with IMMUKNOW_PROXY_PREFIX to exercise the proxy route");
  const escaped: string[] = [];
  const requested: string[] = [];
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  context.on("request", (request) => {
    const url = new URL(request.url());
    if (url.protocol === "http:" || url.protocol === "https:") {
      requested.push(url.pathname);
      if (url.origin !== "http://localhost:4173" || !url.pathname.startsWith(`${prefix}/`))
        escaped.push(request.url());
    }
  });
  await page.goto(`${prefix}/ImmuKnow/playground/`);
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 90_000 });
  await page.locator("#next").click();
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 30_000 });
  const pending = page.waitForEvent("download");
  await page.locator("#pdf").click();
  expect((await pending).suggestedFilename()).toContain("long-history");
  expect(requested.some((path) => path.endsWith(".wasm"))).toBe(true);
  expect(requested.some((path) => path.endsWith(".ttf"))).toBe(true);
  expect(requested.some((path) => path.includes("pdf.worker"))).toBe(true);
  expect(escaped).toEqual([]);
  expect(errors).toEqual([]);
});
