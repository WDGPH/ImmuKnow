import { expect, test } from "@playwright/test";

test("continuous pages and compact layout controls persist into native export", async ({
  page,
}) => {
  const { readFile, mkdir } = await import("node:fs/promises");
  const { unzipSync, strFromU8 } = await import("fflate");
  const { execFile } = await import("node:child_process");
  const { promisify } = await import("node:util");
  const prefix = (process.env.IMMUKNOW_PROXY_PREFIX ?? "").replace(/\/+$/, "");
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(`${prefix}/ImmuKnow/playground/`);
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 90_000 });
  await expect(page.locator(".layout-controls")).not.toHaveAttribute("open");
  await expect(page.locator(".project-actions")).not.toHaveAttribute("open");
  await expect(page.getByRole("textbox", { name: "Source editor" })).not.toContainText(
    "#let list-columns",
  );
  await expect(page.locator(".pdf-page")).toHaveCount(2);
  await page.locator("#page-next").click();
  await expect(page.locator("#pages")).toHaveText("2 / 2");
  await expect
    .poll(() =>
      page
        .locator('.pdf-page[data-page="2"] canvas')
        .evaluate((el) => (el as HTMLCanvasElement).width),
    )
    .toBeGreaterThan(0);
  await page.locator("#preview-scroll").evaluate((el) => {
    el.scrollTop = 0;
  });
  await expect(page.locator("#pages")).toHaveText("1 / 2");
  await page.locator("#client").selectOption("long-history");
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 30_000 });
  expect(await page.locator(".pdf-page").count()).toBeGreaterThan(2);
  await page.locator("#preview-scroll").evaluate((el) => {
    el.scrollTop = el.scrollHeight;
  });
  await expect(page.locator("#pages")).toHaveText("5 / 5");
  await page.locator("#client").selectOption("short");
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 30_000 });
  await page.locator(".layout-controls summary").click();
  const image = await page.evaluate(async () => {
    const canvas = document.createElement("canvas");
    canvas.width = 40;
    canvas.height = 20;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Canvas missing");
    context.fillStyle = "#008080";
    context.fillRect(0, 0, 20, 20);
    return canvas.toDataURL("image/png").split(",")[1];
  });
  await page.locator("#logo-upload").setInputFiles({
    name: "brand.png",
    mimeType: "image/png",
    buffer: Buffer.from(image, "base64"),
  });
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 30_000 });
  await page.locator("#signature-upload").setInputFiles({
    name: "signature.png",
    mimeType: "image/png",
    buffer: Buffer.from(image, "base64"),
  });
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 30_000 });
  await page.locator("#paper-size").selectOption("us-legal");
  await page.locator("#envelope").selectOption("number10");
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 30_000 });
  const size = await page.locator(".pdf-page").first().boundingBox();
  expect((size?.height ?? 0) / (size?.width ?? 1)).toBeCloseTo(14 / 8.5, 2);
  await page.locator("#guide").check();
  await expect(page.locator(".envelope-window")).toHaveCount(1);
  await page.locator("#template").selectOption("templates/overdue_agents_v1.fr.typ");
  await expect(page.locator("#paper-size")).toHaveValue("us-letter");
  await page.locator("#template").selectOption("templates/overdue_diseases_v1.en.typ");
  await expect(page.locator("#paper-size")).toHaveValue("us-legal");
  await expect(page.locator("#envelope")).toHaveValue("number10");
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 30_000 });
  await mkdir("test-results/layout", { recursive: true });
  let pending = page.waitForEvent("download");
  await page.locator("#source").click();
  await (await pending).saveAs("test-results/layout/source.typ");
  pending = page.waitForEvent("download");
  await page.locator("#pdf").click();
  await (await pending).saveAs("test-results/layout/browser.pdf");
  await page.locator(".project-actions summary").click();
  pending = page.waitForEvent("download");
  await page.locator("#export").click();
  await (await pending).saveAs("test-results/layout/project.zip");
  const zip = unzipSync(await readFile("test-results/layout/project.zip"));
  expect(
    JSON.parse(strFromU8(zip["templates/layout-settings.json"])).notices["overdue_diseases_v1.en"],
  ).toEqual({ paper: "us-legal", envelope: "number10" });
  expect(Array.from(zip["templates/assets/logo.png"].slice(0, 8))).toEqual([
    137, 80, 78, 71, 13, 10, 26, 10,
  ]);
  expect(zip["templates/assets/logo.png"]).toEqual(zip["templates/assets/signature.png"]);
  const result = await promisify(execFile)(
    "uv",
    [
      "run",
      "python",
      "-m",
      "playground.scripts.verify_export",
      "playground/test-results/layout/project.zip",
      "playground/test-results/layout/browser.pdf",
      "--flattened",
      "playground/test-results/layout/source.typ",
    ],
    { cwd: "..", timeout: 90_000 },
  );
  expect(JSON.parse(result.stdout)).toHaveLength(2);
  expect(errors).toEqual([]);
  await page.screenshot({ path: "test-results/layout/controls.png", fullPage: true });
});
