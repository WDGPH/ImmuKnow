import { readFileSync } from "node:fs";
import { unzipSync } from "fflate";
import { expect, test, type Page } from "@playwright/test";

test.use({ actionTimeout: 15_000 });

async function currentPreview(page: Page) {
  await expect
    .poll(
      () =>
        page.locator("#preview-state").evaluate((element) => {
          const state = (element as HTMLElement).dataset;
          return (
            Number(state.displayedRevision) > 0 &&
            state.displayedRevision === state.requestedRevision &&
            state.displayedContext === state.context
          );
        }),
      { timeout: 60_000 },
    )
    .toBe(true);
}

async function openProjectActions(page: Page) {
  const menu = page.locator(".project-actions");
  if (!(await menu.evaluate((element) => (element as HTMLDetailsElement).open)))
    await menu.locator("summary").click();
  await expect(page.locator("#export")).toBeVisible();
}

async function exportProbe(page: Page) {
  await page.addInitScript(() => {
    const probe = { requests: 0, held: 0, delayMs: 0, failNext: false };
    Object.assign(window, { exportProbe: probe });
    const NativeWorker = window.Worker;
    window.Worker = class extends NativeWorker {
      override postMessage(
        message: unknown,
        transfer?: Transferable[] | StructuredSerializeOptions,
      ) {
        if ((message as { action?: string }).action === "export") probe.requests++;
        if (transfer) super.postMessage(message, transfer as Transferable[]);
        else super.postMessage(message);
      }
      override set onmessage(handler: ((this: Worker, event: MessageEvent) => unknown) | null) {
        super.onmessage = handler
          ? (event) => {
              if (!(event.data.result instanceof Uint8Array)) {
                handler.call(this, event);
                return;
              }
              const delay = probe.delayMs;
              probe.delayMs = 0;
              if (delay) probe.held++;
              const reply = probe.failNext
                ? new MessageEvent("message", {
                    data: { error: "Injected project download failure" },
                  })
                : event;
              probe.failNext = false;
              if (delay) setTimeout(() => handler.call(this, reply), delay);
              else handler.call(this, reply);
            }
          : null;
      }
    };
  });
}

async function probeState(page: Page) {
  return page.evaluate(
    () =>
      (
        window as unknown as {
          exportProbe: { requests: number; held: number; delayMs: number; failNext: boolean };
        }
      ).exportProbe,
  );
}

for (const includeFonts of [false, true])
  test(`project download preserves authored text with fonts ${includeFonts ? "included" : "omitted"}`, async ({
    page,
  }) => {
    await exportProbe(page);
    await page.goto("./");
    await currentPreview(page);
    await page.locator("#template-tab").click();
    const source = page.locator(".cm-content");
    await source.click();
    await source.press("Control+End");
    await page.keyboard.insertText('\n#text("Explicit export marker 8f7c")');
    await currentPreview(page);
    expect((await probeState(page)).requests).toBe(0);
    await page.evaluate(() => {
      (window as unknown as { exportProbe: { delayMs: number } }).exportProbe.delayMs = 800;
    });
    await openProjectActions(page);
    await expect(page.locator("#include-fonts")).not.toBeChecked();
    if (includeFonts) await page.locator("#include-fonts").check();
    const downloaded = page.waitForEvent("download");
    await page.locator("#export").click();
    await expect(page.locator("#export")).toBeDisabled();
    await expect.poll(async () => (await probeState(page)).held).toBe(1);
    expect((await probeState(page)).requests).toBe(1);
    const path = await (await downloaded).path();
    expect(path).toBeTruthy();
    const files = unzipSync(readFileSync(path as string));
    const template = await page.locator("#template").inputValue();
    expect(new TextDecoder().decode(files[template])).toContain(
      '\n#text("Explicit export marker 8f7c")',
    );
    expect(Object.keys(files)).toContain("immuknow-project.json");
    expect(Object.keys(files).some((path) => path.startsWith("templates/lib/"))).toBe(true);
    expect(
      Object.keys(files).some(
        (path) => path.startsWith("templates/fonts/") && path.endsWith(".ttf"),
      ),
    ).toBe(includeFonts);
    if (includeFonts) expect(Object.keys(files)).toContain("templates/fonts/LICENSE");
    await expect(page.locator("#pdf, #source, #python-project")).toHaveCount(0);
    expect((await probeState(page)).requests).toBe(1);
    await expect(page.locator("#export")).toBeEnabled();
  });

test("edits and template switches refuse delayed project downloads", async ({ page }) => {
  await exportProbe(page);
  const downloads: string[] = [];
  page.on("download", (download) => downloads.push(download.suggestedFilename()));
  await page.goto("./");
  await currentPreview(page);
  await page.evaluate(() => {
    (window as unknown as { exportProbe: { delayMs: number } }).exportProbe.delayMs = 800;
  });
  await openProjectActions(page);
  await page.locator("#export").click();
  await expect.poll(async () => (await probeState(page)).held).toBe(1);
  await page.locator("#template-tab").click();
  const source = page.locator(".cm-content");
  await source.click();
  await source.press("Control+End");
  await page.keyboard.insertText("\n// changed after project request");
  await expect(page.locator("#diagnostics")).toContainText("project changed");
  await currentPreview(page);
  expect(downloads).toEqual([]);

  await page.evaluate(() => {
    (window as unknown as { exportProbe: { delayMs: number } }).exportProbe.delayMs = 800;
  });
  await openProjectActions(page);
  await page.locator("#export").click();
  await expect.poll(async () => (await probeState(page)).held).toBe(2);
  await page.locator("#theme-tab").click();
  await page.locator("#template").selectOption("templates/overdue_diseases_v1.fr.typ");
  await currentPreview(page);
  expect(downloads).toEqual([]);
  expect((await probeState(page)).requests).toBe(2);
});

test("an export error keeps the current painted preview available", async ({ page }) => {
  await exportProbe(page);
  await page.goto("./");
  await currentPreview(page);
  const before = await page.locator("#preview-state").getAttribute("data-displayed-revision");
  await page.evaluate(() => {
    (window as unknown as { exportProbe: { failNext: boolean } }).exportProbe.failNext = true;
  });
  await openProjectActions(page);
  await page.locator("#export").click();
  await expect(page.locator("#diagnostics")).toContainText("Injected project download failure");
  await expect(page.locator("#preview-state")).toHaveAttribute(
    "data-displayed-revision",
    before as string,
  );
  await expect(page.locator(".preview-page")).not.toHaveCount(0);
  await expect(page.locator("#export")).toBeEnabled();
  expect((await probeState(page)).requests).toBe(1);
});

test("oversized imports are refused before reading the file", async ({ page }) => {
  await page.addInitScript(() => {
    const size = Object.getOwnPropertyDescriptor(Blob.prototype, "size")?.get;
    if (!size) throw new Error("Missing file size accessor");
    Object.defineProperty(File.prototype, "size", {
      get() {
        return this.name === "oversized.zip" ? 32 * 1024 * 1024 + 1 : size.call(this);
      },
    });
    const read = File.prototype.arrayBuffer;
    File.prototype.arrayBuffer = function () {
      if (this.name === "oversized.zip") throw new Error("Oversized file was read");
      return read.call(this);
    };
  });
  await page.goto("./");
  await currentPreview(page);
  const before = await page.locator("#preview-state").getAttribute("data-displayed-revision");
  await page.locator("#archive").setInputFiles({
    name: "oversized.zip",
    mimeType: "application/zip",
    buffer: Buffer.from("Not read"),
  });
  await expect(page.locator("#diagnostics")).toContainText("Compressed project exceeds 32 MB");
  await expect(page.locator("#preview-state")).toHaveAttribute(
    "data-displayed-revision",
    before as string,
  );
});
