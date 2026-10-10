import { expect, test } from "@playwright/test";

test("editor compiles locally and keeps source edits across clients", async ({ page, context }) => {
  const remote: string[] = [],
    errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await context.route("**/*", async (route) => {
    if (new URL(route.request().url()).origin !== "http://localhost:4173") {
      remote.push(route.request().url());
      await route.abort();
    } else await route.continue();
  });
  await page.goto("/ImmuKnow/playground/");
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 90_000 });
  await expect(page.locator("#pages")).toHaveText("1 / 2");
  const source = page.getByRole("textbox", { name: "Source editor" });
  await source.press("Control+End");
  await source.press("Enter");
  await source.pressSequentially("// saved across clients");
  await expect(page.getByRole("button", { name: "Export PDF", exact: true })).toBeDisabled();
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 30_000 });
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.locator("#client")).toHaveValue("long-history");
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 30_000 });
  await expect(source).toContainText("// saved across clients");
  await expect(page.locator("#pages")).not.toHaveText("1 / 2");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export PDF", exact: true }).click();
  expect((await download).suggestedFilename()).toContain("long-history");
  await page.locator("#guide").check();
  await expect(page.locator(".envelope-window")).toHaveCount(1);
  await page.screenshot({ path: "test-results/editor.png", fullPage: true });
  expect(remote).toEqual([]);
  expect(errors).toEqual([]);
});

test("syntax errors and remote imports leave a stale, non-exportable preview", async ({
  page,
  context,
}) => {
  const remote: string[] = [];
  await context.route("**/*", async (route) => {
    if (new URL(route.request().url()).origin !== "http://localhost:4173") {
      remote.push(route.request().url());
      await route.abort();
    } else await route.continue();
  });
  await page.goto("/ImmuKnow/playground/");
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 90_000 });
  const source = page.getByRole("textbox", { name: "Source editor" });
  await source.press("Control+End");
  await source.press("Enter");
  await page.keyboard.insertText("#let broken = (");
  await expect(page.locator("#status")).toContainText("Compilation failed", { timeout: 30_000 });
  await expect(page.locator("#diagnostics")).toContainText("unclosed");
  await expect(page.locator("#diagnostics button").first()).toContainText(".typ:");
  await expect(page.locator("#pdf")).toBeDisabled();
  await expect(page.locator("#preview-caption")).toContainText("Stale preview:");
  await source.press("Control+z");
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 30_000 });
  await page.keyboard.insertText('#import "@preview/tablex:0.0.9": *');
  await expect(page.locator("#status")).toContainText("Compilation failed", { timeout: 30_000 });
  await expect(page.locator("#diagnostics")).toContainText(
    "runtime package downloads are disabled",
  );
  await expect(page.locator("#pdf")).toBeDisabled();
  expect(remote).toEqual([]);
  await page.locator(".project-actions").evaluate((el) => {
    (el as HTMLDetailsElement).open = true;
  });
  await page.getByRole("button", { name: "Restart compiler", exact: true }).click();
  await expect(page.locator("#status")).toContainText("Compilation failed", { timeout: 30_000 });
  await source.press("Control+z");
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 30_000 });
});

test("drafts survive template switches and reload; project ZIP restores source", async ({
  page,
}) => {
  await page.goto("/ImmuKnow/playground/");
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 90_000 });
  const source = page.getByRole("textbox", { name: "Source editor" });
  await source.press("Control+End");
  await source.press("Enter");
  await page.keyboard.insertText("// portable draft é");
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 30_000 });
  const downloading = page.waitForEvent("download");
  await page.locator(".project-actions").evaluate((el) => {
    (el as HTMLDetailsElement).open = true;
  });
  await page.locator("#export").click();
  const archive = await downloading;
  const path = await archive.path();
  expect(path).toBeTruthy();
  await page.locator("#template").selectOption("templates/overdue_agents_v1.fr.typ");
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 30_000 });
  await page.locator("#template").selectOption("templates/overdue_diseases_v1.en.typ");
  await expect(source).toContainText("// portable draft é");
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 30_000 });
  await expect(page.locator("#storage")).toContainText("Drafts saved");
  await page.reload();
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 90_000 });
  await source.press("Control+End");
  await expect(source).toContainText("// portable draft é");
  page.on("dialog", (dialog) => dialog.accept());
  await page.locator(".project-actions").evaluate((el) => {
    (el as HTMLDetailsElement).open = true;
  });
  await page.locator("#clear").click();
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 30_000 });
  await expect(source).not.toContainText("// portable draft é");
  await page.locator("#archive").setInputFiles(path as string);
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 30_000 });
  await source.press("Control+End");
  await expect(source).toContainText("// portable draft é");
});

test("unavailable storage remains usable and narrow layout stacks the panes", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, "localStorage", {
      get() {
        throw new Error("storage unavailable");
      },
    });
  });
  await page.setViewportSize({ width: 600, height: 900 });
  await page.goto("/ImmuKnow/playground/");
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 90_000 });
  await expect(page.locator("#storage")).toContainText("storage may be unavailable");
  const source = page.getByRole("textbox", { name: "Source editor" });
  await source.press("Control+End");
  await page.keyboard.insertText("\n// local only");
  await expect(page.locator("#storage")).toContainText("download a project before leaving");
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 30_000 });
  const editor = await page.locator(".editor-pane").boundingBox(),
    preview = await page.locator(".preview-pane").boundingBox();
  expect(preview?.y).toBeGreaterThanOrEqual((editor?.y ?? 0) + (editor?.height ?? 0));
});

test("all maintained template and example combinations produce current PDFs", async ({
  page,
  context,
}) => {
  const { readFile, mkdir } = await import("node:fs/promises");
  const prepared = JSON.parse(
    await readFile(new URL("../examples/prepared.json", import.meta.url), "utf8"),
  );
  const remote: string[] = [],
    errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await context.route("**/*", async (route) => {
    if (new URL(route.request().url()).origin !== "http://localhost:4173") {
      remote.push(route.request().url());
      await route.abort();
    } else await route.continue();
  });
  await mkdir("test-results/examples", { recursive: true });
  await page.goto("/ImmuKnow/playground/");
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 90_000 });
  let count = 0;
  for (const example of prepared.examples)
    for (const name of Object.keys(example.payloads)) {
      await page.locator("#template").selectOption(`templates/${name}`);
      await page.locator("#client").selectOption(example.id);
      await expect(page.locator("#status")).toHaveText("Ready", { timeout: 30_000 });
      await expect(page.locator("#preview-caption")).toContainText(`${name} / ${example.id}`);
      const pending = page.waitForEvent("download");
      await page.locator("#pdf").click();
      const download = await pending;
      await download.saveAs(`test-results/examples/${name}-${example.id}.pdf`);
      count++;
    }
  expect(count).toBe(37);
  expect(remote).toEqual([]);
  expect(errors).toEqual([]);
});

test("browser edits export unchanged into both production CLI workflows", async ({ page }) => {
  const { readFile, mkdir } = await import("node:fs/promises");
  const { execFile } = await import("node:child_process");
  const { promisify } = await import("node:util");
  const { unzipSync, strFromU8 } = await import("fflate");
  const original = await readFile(
    new URL("../../immuknow/templates/settings/overdue_diseases_v1.en.typ", import.meta.url),
    "utf8",
  );
  const edited = original
    .replace("#let list-columns = 1", "#let list-columns = 2")
    .replace("#let history-diseases = auto", '#let history-diseases = ("Measles", "Polio")')
    .replace("#let history-ignore-agents = auto", "#let history-ignore-agents = ()")
    .replace("#let history-include-other = auto", "#let history-include-other = false")
    .replace("#let history-show-validity = auto", "#let history-show-validity = false");
  await page.goto("/ImmuKnow/playground/");
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 90_000 });
  await page.locator(".layout-controls summary").click();
  await page.locator("#template-settings").click();
  const source = page.getByRole("textbox", { name: "Source editor" });
  await source.focus();
  await source.press("Control+a");
  await page.keyboard.insertText(edited);
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 30_000 });
  await mkdir("test-results/roundtrip", { recursive: true });
  let pending = page.waitForEvent("download");
  await page.locator("#source").click();
  await (await pending).saveAs("test-results/roundtrip/source.typ");
  expect(await readFile("test-results/roundtrip/source.typ", "utf8")).toContain(edited);
  pending = page.waitForEvent("download");
  await page.locator("#pdf").click();
  await (await pending).saveAs("test-results/roundtrip/browser.pdf");
  await page.locator("#guide").check();
  await expect(page.locator(".envelope-window")).toHaveCount(1);
  pending = page.waitForEvent("download");
  await page.locator("#pdf").click();
  await (await pending).saveAs("test-results/roundtrip/guide.pdf");
  expect(await readFile("test-results/roundtrip/guide.pdf")).toEqual(
    await readFile("test-results/roundtrip/browser.pdf"),
  );
  pending = page.waitForEvent("download");
  await page.locator(".project-actions").evaluate((el) => {
    (el as HTMLDetailsElement).open = true;
  });
  await page.locator("#export").click();
  await (await pending).saveAs("test-results/roundtrip/project.zip");
  const zip = unzipSync(await readFile("test-results/roundtrip/project.zip"));
  expect(strFromU8(zip["templates/settings/overdue_diseases_v1.en.typ"])).toBe(edited);
  const result = await promisify(execFile)(
    "uv",
    [
      "run",
      "python",
      "-m",
      "playground.scripts.verify_export",
      "playground/test-results/roundtrip/project.zip",
      "playground/test-results/roundtrip/browser.pdf",
      "--flattened",
      "playground/test-results/roundtrip/source.typ",
    ],
    { cwd: "..", timeout: 90_000 },
  );
  const reports = JSON.parse(result.stdout);
  expect(reports.map((report: { selector: string }) => report.selector)).toEqual([
    "single",
    "manifest",
  ]);
  for (const report of reports) {
    expect(report.clients).toBe(8);
    expect(report.max_text_delta_pt).toBeLessThanOrEqual(0.01);
  }
});

test("rapid client changes, dependency edits, and keyboard resizing preserve current output", async ({
  page,
}) => {
  await page.goto("/ImmuKnow/playground/");
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 90_000 });
  await page.locator("#client").selectOption("long-history");
  await page.locator("#client").selectOption("short");
  await page.locator("#client").selectOption("long-fields");
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 30_000 });
  await expect(page.locator("#preview-caption")).toContainText("/ long-fields");
  const downloading = page.waitForEvent("download");
  await page.locator("#pdf").click();
  expect((await downloading).suggestedFilename()).toContain("long-fields");
  await page.locator("#files-toggle").click();
  await page.getByRole("button", { name: "templates/conf.typ", exact: true }).click();
  const source = page.getByRole("textbox", { name: "Source editor" });
  await source.press("Control+End");
  await page.keyboard.insertText("\n// dependency draft");
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 30_000 });
  await page
    .getByRole("button", { name: "templates/overdue_diseases_v1.en.typ", exact: true })
    .click();
  await page.getByRole("button", { name: "templates/conf.typ", exact: true }).click();
  await expect(source).toContainText("// dependency draft");
  await page.locator("#divider").focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.locator("#divider")).toHaveAttribute("aria-valuenow", "52");
});

test("an unresponsive compiler worker is terminated and restarts", async ({ page, context }) => {
  // Inject a stuck message handler into the actual worker, without mocking any
  // successful compiler result. Typst itself rejects trivially infinite loops.
  await context.route("**/assets/compile.worker-*.js", async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      response,
      body: `addEventListener("message", () => { while (true) {} });\n${await response.text()}`,
    });
  });
  await page.goto("/ImmuKnow/playground/");
  await expect(page.locator("#status")).toContainText("exceeded 20 seconds", { timeout: 60_000 });
  await expect(page.locator("#pdf")).toBeDisabled();
  await context.unroute("**/assets/compile.worker-*.js");
  await page.locator(".project-actions").evaluate((el) => {
    (el as HTMLDetailsElement).open = true;
  });
  await page.locator("#restart").click();
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 45_000 });
  await expect(page.locator("#pdf")).toBeEnabled();
});

test("missing static font assets report failure and recover after restart", async ({
  page,
  context,
}) => {
  await context.route("**/generated/fonts/manifest.json", (route) =>
    route.fulfill({ status: 404, body: "missing" }),
  );
  await page.goto("/ImmuKnow/playground/");
  await expect(page.locator("#status")).toContainText("Pinned fonts are unavailable", {
    timeout: 30_000,
  });
  await expect(page.locator("#pdf")).toBeDisabled();
  await context.unroute("**/generated/fonts/manifest.json");
  await page.locator(".project-actions").evaluate((el) => {
    (el as HTMLDetailsElement).open = true;
  });
  await page.locator("#restart").click();
  await expect(page.locator("#status")).toHaveText("Ready", { timeout: 45_000 });
});
