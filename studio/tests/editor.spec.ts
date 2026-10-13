import { readFile } from "node:fs/promises";
import { expect, test, type Page } from "@playwright/test";
import { unzipSync } from "fflate";
import { exportProject } from "../src/archive-core";
import type { Bundle, Files } from "../src/types";

async function currentPreview(page: Page) {
  await expect
    .poll(
      async () =>
        page.locator("#preview-state").evaluate((el) => {
          const state = (el as HTMLElement).dataset;
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

test("a component error opens the supplied library for reading without changing it", async ({
  page,
}) => {
  await page.goto("./");
  await currentPreview(page);
  await page.locator("#template-tab").click();
  const source = page.locator(".cm-content");
  await source.click();
  await source.press("Control+End");
  await page.keyboard.insertText(
    '\n#immuknow.check-notice(notice, version: "wrong", language: "en")',
  );
  const finding = page
    .locator("#diagnostics button")
    .filter({ hasText: "lib/immuknow/src/validation.typ" })
    .first();
  await expect(finding).toBeVisible();
  await finding.click();
  await expect(source).toHaveAttribute("contenteditable", "false");
  const before = await source.textContent();
  await source.press("Control+End");
  await source.press("Control+]");
  await source.press("Control+/");
  await page.keyboard.insertText("Do not change the library");
  expect(await source.textContent()).toBe(before);
  await page.locator("#template-tab").click();
  await expect(source).toHaveAttribute("contenteditable", "true");
  await source.press("Control+z");
  await currentPreview(page);
});

test("history warnings follow edited suspension content and recover after errors", async ({
  page,
}) => {
  await page.goto("./");
  await page.locator("#theme-tab").click();
  await page.locator("#template").selectOption("templates/suspension_order_v1.en.typ");
  await currentPreview(page);
  await expect(page.locator("#diagnostics")).not.toContainText("content.history_validity");
  await page.locator("#template-tab").click();
  const source = page.locator(".cm-content");
  await source.click();
  await source.press("Control+End");
  await page.keyboard.insertText(
    "\n#pagebreak()\n#immuknow.immunization-history(notice, show-validity: true)\n",
  );
  await currentPreview(page);
  await expect(page.locator("#diagnostics")).toContainText("content.history_validity");
  await source.press("Control+z");
  await currentPreview(page);
  await expect(page.locator("#diagnostics")).not.toContainText("content.history_validity");
  await source.press("Control+End");
  await page.keyboard.insertText('\n#panic("failed preview")');
  await expect(page.locator("#diagnostics")).toContainText("failed preview", { timeout: 30_000 });
  await expect(page.locator("#diagnostics")).not.toContainText("content.history_validity");
  await source.press("Control+z");
  await currentPreview(page);
  await expect(page.locator("#diagnostics")).not.toContainText("content.history_validity");
});

test("authored project survives editing, warning/error recovery, drafts and export", async ({
  page,
}, testInfo) => {
  let pdfWorkers = 0;
  page.on("worker", (worker) => {
    if (worker.url().includes("pdf.worker")) pdfWorkers++;
  });
  await page.goto("./");
  const bundle = (await (await page.request.get("./generated/project.json")).json()) as Bundle;
  const files: Files = Object.fromEntries(
    Object.entries(bundle.files).map(([name, bytes]) => [
      name,
      new Uint8Array(Buffer.from(bytes, "base64")),
    ]),
  );
  const settings = new TextDecoder()
    .decode(files["templates/settings.typ"])
    .replace("#let body-size = 10pt", "#let body-size = 10.12345pt")
    .replace('#let signature-name = "Dr. Annie Body"', '#let signature-name = ""')
    .replace("  enabled: true,", "  enabled: false,")
    .replaceAll("\n", "\r\n");
  files["templates/settings.typ"] = new TextEncoder().encode(`\ufeff${settings}`);
  const untouched = new Uint8Array([0, 1, 127, 128, 255]);
  files["templates/assets/preserved.bin"] = untouched;
  const archive = await exportProject(files, "templates/overdue_diseases_v1.en.typ", bundle.build);
  await page.locator("#archive").setInputFiles({
    name: "authored.zip",
    mimeType: "application/zip",
    buffer: Buffer.from(archive),
  });
  await currentPreview(page);
  await expect(page.locator(".preview-page")).toHaveCount(2);
  await page.locator("#next").click();
  await currentPreview(page);
  await page.locator("#next").click();
  await expect(page.locator("#diagnostics")).toContainText("source.age_unknown");
  await currentPreview(page);

  await expect(page.locator(".preview-page")).toHaveCount(2);
  await expect
    .poll(() =>
      page
        .locator(".preview-page canvas")
        .first()
        .evaluate((canvas) => (canvas as HTMLCanvasElement).width),
    )
    .toBeGreaterThan(0);
  await expect(page.locator("#preview-state")).toHaveAttribute("data-state", "ready");
  await page.screenshot({ path: testInfo.outputPath("editor-warning.png") });
  const source = page.locator(".cm-content");
  await source.click();
  await source.press("Control+End");
  await page.keyboard.insertText('\n#unknown-workflow-function("broken")');
  await expect(page.locator(".preview-page")).toHaveCount(2);
  await expect(page.locator("#preview-state")).toHaveAttribute(
    "aria-label",
    /last successful version/,
  );
  await expect
    .poll(() =>
      page
        .locator(".preview-page canvas")
        .first()
        .evaluate((canvas) => (canvas as HTMLCanvasElement).width),
    )
    .toBeGreaterThan(0);
  await expect(page.locator("#diagnostics")).toContainText("unknown variable", { timeout: 30_000 });
  await expect(page.locator(".cm-lintRange-error")).toHaveText("u");
  await source.press("Control+z");
  await expect(page.locator(".cm-lintRange-error")).toHaveCount(0);
  await currentPreview(page);
  await source.press("Control+End");
  await source.press("Control+]");
  expect(await page.locator(".cm-line").last().textContent()).toMatch(/^ {2}/);
  await source.press("Control+[");
  await source.press("Control+/");
  await expect(page.locator(".cm-line").last()).toHaveText(/^\/\//);
  await source.press("Control+/");
  await page.locator("#divider").focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.locator("#divider")).toHaveAttribute("aria-valuenow", "53");
  await page.keyboard.press("ArrowLeft");

  await page.locator("#theme-tab").click();
  await page.locator("#body-font-picker").selectOption("FreeSerif");
  const image = Buffer.from(
    '<svg xmlns="http://www.w3.org/2000/svg" width="30" height="20"><rect width="30" height="20" fill="#005568"/></svg>',
  );
  await page
    .locator("#extra-upload")
    .setInputFiles({ name: "authored.svg", mimeType: "image/svg+xml", buffer: image });
  await expect(page.locator("#extra-preview")).toBeVisible();
  await currentPreview(page);
  await expect
    .poll(() =>
      page.evaluate(async () => {
        return await new Promise<boolean>((resolve, reject) => {
          const request = indexedDB.open("immuknow-studio-drafts-v2", 1);
          request.onerror = () => reject(request.error);
          request.onsuccess = () => {
            const db = request.result;
            const read = db.transaction("drafts").objectStore("drafts").get("current");
            read.onsuccess = () => {
              resolve(Boolean(read.result?.files["templates/assets/studio-extra.svg"]));
              db.close();
            };
          };
        });
      }),
    )
    .toBe(true);
  // Normal editing never starts a PDF parser worker.
  expect(pdfWorkers).toBe(0);
  await page.reload();
  await currentPreview(page);
  await expect(page.locator("#position")).toHaveText("3 of 3");
  await page.locator("#theme-tab").click();
  await expect(page.locator("#body-font-picker")).toHaveValue("FreeSerif");
  await expect(page.locator("#extra-preview")).toBeVisible();

  await page.locator(".project-actions summary").click();
  const downloaded = page.waitForEvent("download");
  await page.locator("#export").click();
  const path = await (await downloaded).path();
  const saved = unzipSync(new Uint8Array(await readFile(path as string)));
  const expectedSettings = `\ufeff${settings.replace('#let body-font = "FreeSans"', '#let body-font = "FreeSerif"')}`;
  expect(saved["templates/settings.typ"]).toEqual(new TextEncoder().encode(expectedSettings));
  expect(saved["templates/assets/preserved.bin"]).toEqual(untouched);
  expect(Buffer.from(saved["templates/assets/studio-extra.svg"])).toEqual(image);
  expect(saved["templates/overdue_diseases_v1.en.typ"]).toEqual(
    files["templates/overdue_diseases_v1.en.typ"],
  );

  await page.locator("#theme-toggle").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.locator("#help-open").click();
  await expect(page.locator("#tour-dialog")).toBeVisible();
  await page.locator("#tour-close").click();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator("#editor-panel")).toBeHidden();
  await expect(page.locator("#theme-panel")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("editor-narrow.png") });
});

test("updates retain painted pages, zoom and live reading position, then clamp on page removal", async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("./");
  await currentPreview(page);
  const source = page.locator(".cm-content");
  await source.click();
  await source.press("Control+End");
  await page.keyboard.insertText(
    "\n#pagebreak()\nSecond page marker\n#pagebreak()\nThird page marker",
  );
  await currentPreview(page);
  await page.locator("#zoom-in").click();
  const scroller = page.locator("#preview-scroll");
  await expect
    .poll(() =>
      page
        .locator(".preview-page")
        .first()
        .evaluate((p) => p.clientWidth),
    )
    .toBeGreaterThan(500);
  await scroller.evaluate((el) => {
    const pages = el.querySelectorAll<HTMLElement>(".preview-page");
    el.scrollTop += pages[1].getBoundingClientRect().top - el.getBoundingClientRect().top + 150;
    el.scrollLeft = 30;
  });
  await expect(page.locator("#pages")).toHaveText(/^2 \/ /);
  const before = await scroller.evaluate((el) => ({
    top: el.scrollTop,
    left: el.scrollLeft,
    width: el.querySelector<HTMLElement>(".preview-page")?.clientWidth,
  }));
  // Track every animation frame while editing: there must always be a painted
  // canvas in the viewport, including while the replacement is prepared.
  await page.evaluate(() => {
    const state = { blank: 0, stop: false };
    Object.assign(window, { paintProof: state });
    const check = () => {
      const container = document.querySelector("#preview-scroll") as HTMLElement,
        bounds = container.getBoundingClientRect();
      if (
        !Array.from(container.querySelectorAll("canvas")).some(
          (c) =>
            c.width > 0 &&
            c.getBoundingClientRect().bottom > bounds.top &&
            c.getBoundingClientRect().top < bounds.bottom,
        )
      )
        state.blank++;
      if (!state.stop) requestAnimationFrame(check);
    };
    requestAnimationFrame(check);
  });
  await source.press("Control+End");
  await page.keyboard.insertText("\n// ordinary edit");
  // A scroll made while loading/rendering must win over the earlier position.
  await scroller.evaluate((el) => {
    el.scrollTop += 80;
  });
  await currentPreview(page);
  const after = await scroller.evaluate((el) => ({
    top: el.scrollTop,
    left: el.scrollLeft,
    width: el.querySelector<HTMLElement>(".preview-page")?.clientWidth,
  }));
  expect(Math.abs(after.top - before.top - 80)).toBeLessThan(3);
  expect(after.width).toBe(before.width);
  expect(after.left).toBe(before.left);
  await page.keyboard.insertText('\n#panic("temporary syntax failure")');
  await expect(page.locator("#diagnostics")).toContainText("temporary syntax failure");
  await expect(page.locator("#preview-state")).toHaveAttribute("data-state", "stale");
  await source.press("Control+z");
  await currentPreview(page);
  const blanks = await page.evaluate(() => {
    const state = (window as unknown as { paintProof: { blank: number; stop: boolean } })
      .paintProof;
    state.stop = true;
    return state.blank;
  });
  expect(blanks).toBe(0);
  await page.locator("#theme-toggle").click();
  await page.screenshot({ path: info.outputPath("stable-page-two.png") });
  // Replace source in this context with one page, preserving zoom and clamping.
  await source.press("Control+a");
  await page.keyboard.insertText("One remaining page.");
  await currentPreview(page);
  await expect(page.locator(".preview-page")).toHaveCount(1);
  await expect(page.locator("#pages")).toHaveText("1 / 1");
  expect(
    await scroller.evaluate((el) => el.scrollTop <= el.scrollHeight - el.clientHeight + 1),
  ).toBe(true);
  expect(errors).toEqual([]);
});

test("continuous typing advances stale previews and context switches isolate old pages", async ({
  page,
}) => {
  let compilerWorkers = 0,
    pdfWorkers = 0,
    fontRequests = 0;
  page.on("worker", (worker) => {
    if (worker.url().includes("compile.worker")) compilerWorkers++;
    if (worker.url().includes("pdf.worker")) pdfWorkers++;
  });
  page.on("request", (request) => {
    if (request.url().includes("generated/fonts/")) fontRequests++;
  });
  await page.goto("./");
  await currentPreview(page);
  const initialRequests = fontRequests;
  const initial = Number(
    await page.locator("#preview-state").getAttribute("data-displayed-revision"),
  );
  const source = page.locator(".cm-content");
  await source.click();
  await source.press("Control+End");
  await page.keyboard.insertText("\n// ");
  let advanced = false;
  let displayed = initial;
  for (let i = 0; i < 45; i++) {
    await page.keyboard.type("a");
    await page.waitForTimeout(30);
    const revisions = await page.locator("#preview-state").evaluate((el) => ({
      displayed: Number(el.getAttribute("data-displayed-revision")),
      requested: Number(el.getAttribute("data-requested-revision")),
    }));
    expect(revisions.displayed).toBeGreaterThanOrEqual(displayed);
    displayed = revisions.displayed;
    if (revisions.displayed > initial && revisions.displayed < revisions.requested) {
      advanced = true;
    }
  }
  expect(advanced).toBe(true);
  await currentPreview(page);
  expect(compilerWorkers).toBe(1);
  expect(pdfWorkers).toBe(0);
  expect(fontRequests).toBe(initialRequests);
  await page.locator("#theme-tab").click();
  await page.locator("#template").selectOption("templates/overdue_diseases_v1.fr.typ");
  await expect(page.locator("#preview-state")).toHaveAttribute("data-displayed-revision", "0");
  await page.locator("#template").selectOption("templates/overdue_diseases_v1.en.typ");
  await page.locator("#next").click();
  await currentPreview(page);
  const state = await page
    .locator("#preview-state")
    .evaluate((el) => ({ ...(el as HTMLElement).dataset }));
  expect(state.displayedRevision).toBe(state.requestedRevision);
  await page.locator(".project-actions summary").click();
  await page.locator("#restart").click();
  await currentPreview(page);
  expect(compilerWorkers).toBe(2);
  expect(pdfWorkers).toBe(0);
});

test("envelope geometry stays with displayed pages and source navigation survives redraw", async ({
  page,
}) => {
  await page.goto("./");
  await currentPreview(page);
  await page.locator("#settings-tab").click();
  await page.locator("#guide").check();
  await expect(page.locator(".envelope-window")).toBeVisible();
  const geometry = await page.locator(".envelope-window").getAttribute("style");
  const source = page.locator(".cm-content");
  await source.click();
  await source.press("Control+End");
  await page.keyboard.insertText('\n#panic("settings temporarily broken")');
  await expect(page.locator("#diagnostics")).toContainText("settings temporarily broken");
  expect(await page.locator(".envelope-window").getAttribute("style")).toBe(geometry);
  await source.press("Control+z");
  await currentPreview(page);
  await page.locator("#template-tab").click();
  await source.click();
  await source.press("Control+a");
  await page.keyboard.insertText(
    "#set page(width: 612pt, height: 792pt, margin: 24pt)\n#text(size: 24pt)[Navigation marker]",
  );
  await currentPreview(page);
  await expect(page.locator(".envelope-window")).toHaveCount(0);
  for (let i = 0; i < 2; i++) {
    const paper = page.locator(".preview-page").first();
    await paper.dblclick({
      position: await paper.evaluate((el) => ({
        x: (60 * el.clientWidth) / 612,
        y: (35 * el.clientWidth) / 612,
      })),
    });
    await expect(page.locator(".cm-content .source-target")).toHaveText(/Navigation/);
    if (i === 0) {
      await source.press("Control+End");
      await page.keyboard.insertText("\n// redraw");
      await currentPreview(page);
      await page.locator("#divider").focus();
      await page.keyboard.press("ArrowRight");
    }
  }
});

test("delayed compiler replies cannot cross an import or language boundary", async ({ page }) => {
  await page.addInitScript(() => {
    const control = { compiler: 0, heldCompiler: 0 };
    Object.assign(window, { delays: control });
    const NativeWorker = window.Worker;
    window.Worker = class extends NativeWorker {
      override set onmessage(handler: ((this: Worker, event: MessageEvent) => unknown) | null) {
        super.onmessage = handler
          ? (event) => {
              const delay = event.data.type === "result" ? control.compiler : 0;
              if (delay) {
                control.compiler = 0;
                control.heldCompiler++;
                setTimeout(() => handler.call(this, event), delay);
              } else handler.call(this, event);
            }
          : null;
      }
    };
  });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("./");
  await currentPreview(page);
  const source = page.locator(".cm-content");
  await source.click();
  await source.press("Control+End");
  await page.evaluate(() => {
    (window as unknown as { delays: { compiler: number } }).delays.compiler = 800;
  });
  await page.keyboard.insertText("\n// delayed reply");
  await page.waitForFunction(
    () => (window as unknown as { delays: { heldCompiler: number } }).delays.heldCompiler > 0,
  );
  await page.locator("#theme-tab").click();
  await page.locator("#template").selectOption("templates/overdue_diseases_v1.fr.typ");
  await expect(page.locator(".preview-page")).toHaveCount(0);
  await currentPreview(page);
  await page.locator("#template-tab").click();
  await source.click();
  await source.press("Control+End");
  await page.evaluate(() => {
    (window as unknown as { delays: { compiler: number } }).delays.compiler = 800;
  });
  await page.keyboard.insertText("\n// delayed import reply");
  await page.waitForFunction(
    () => (window as unknown as { delays: { heldCompiler: number } }).delays.heldCompiler > 1,
  );
  const bundle = (await (await page.request.get("./generated/project.json")).json()) as Bundle;
  const files: Files = Object.fromEntries(
    Object.entries(bundle.files).map(([name, bytes]) => [
      name,
      new Uint8Array(Buffer.from(bytes, "base64")),
    ]),
  );
  const archive = await exportProject(files, "templates/suspension_order_v1.en.typ", bundle.build);
  await page.locator("#archive").setInputFiles({
    name: "replacement.zip",
    mimeType: "application/zip",
    buffer: Buffer.from(archive),
  });
  await expect(page.locator("#archive")).toHaveValue("");
  await currentPreview(page);
  await expect(page.locator("#template")).toHaveValue("templates/suspension_order_v1.en.typ");
  const state = await page
    .locator("#preview-state")
    .evaluate((el) => ({ ...(el as HTMLElement).dataset }));
  expect(state.displayedRevision).toBe(state.requestedRevision);
  await expect(page.locator("#diagnostics")).not.toContainText("content.history_validity");
  expect(errors).toEqual([]);
});

test("a prepared replacement cannot publish after the viewer context is cleared", async ({
  page,
}) => {
  await page.goto("proof.html");
  await page.waitForFunction(() => Boolean(window.proof?.compiler.compilerVersion));
  await page.evaluate(async () => {
    const { proof } = window;
    const initial = proof.submit([proof.job]);
    while (!proof.results.find((r) => r.revision === initial)?.timing?.committed)
      await new Promise((resolve) => setTimeout(resolve, 10));
    // Hold a real completed preparation before it can reach the visible swap.
    const viewer = proof.viewer as unknown as {
      prepare: (...args: unknown[]) => Promise<void>;
    };
    const prepare = viewer.prepare.bind(viewer);
    const control = { held: false, release: () => {} };
    Object.assign(window, { preparation: control });
    viewer.prepare = async (...args) => {
      viewer.prepare = prepare;
      await prepare(...args);
      control.held = true;
      await new Promise<void>((resolve) => {
        control.release = resolve;
      });
    };
    proof.submit([
      {
        ...proof.job,
        files: {
          ...proof.job.files,
          [`/${proof.job.template}`]: new TextEncoder().encode("Obsolete prepared notice"),
        },
      },
    ]);
  });
  await page.waitForFunction(
    () => (window as unknown as { preparation: { held: boolean } }).preparation.held,
  );
  await page.evaluate(() => {
    const { proof } = window;
    proof.compiler.invalidate();
    proof.viewer.clear();
    proof.submit([
      {
        ...proof.job,
        files: {
          ...proof.job.files,
          [`/${proof.job.template}`]: new TextEncoder().encode("Current replacement notice"),
        },
      },
    ]);
    (window as unknown as { preparation: { release: () => void } }).preparation.release();
  });
  await expect(page.locator(".preview-page")).toContainText("Current replacement notice");
  await expect(page.locator(".preview-page")).not.toContainText("Obsolete prepared notice");
});

test("a worker script load failure has a readable error and recovers after restart", async ({ page }) => {
  let attempts = 0;
  await page.route("**/compile.worker*.js", async (route) => {
    attempts++;
    if (attempts === 1) await route.abort("failed");
    else await route.continue();
  });
  await page.goto("./");
  await expect(page.locator("#diagnostics")).toContainText(
    "Compiler worker failed. Use Restart compiler.",
    { timeout: 60_000 },
  );
  await page.locator(".project-actions summary").click();
  await page.locator("#restart").click();
  await currentPreview(page);
  expect(attempts).toBe(2);
  await expect(page.locator("#diagnostics")).not.toContainText("Compiler worker failed");
});

test("a failed local renderer load can recover after restarting the compiler", async ({ page }) => {
  let attempts = 0;
  await page.route("**/typst_ts_renderer_bg*.wasm", async (route) => {
    attempts++;
    if (attempts === 1) await route.abort("failed");
    else await route.continue();
  });
  await page.goto("./");
  await expect(page.locator("#diagnostics")).toContainText(
    "Could not display the compiled notice",
    { timeout: 60_000 },
  );
  await page.locator(".project-actions summary").click();
  await page.locator("#restart").click();
  await currentPreview(page);
  expect(attempts).toBe(2);
  await expect(page.locator(".preview-page canvas")).toHaveCount(2);
});
