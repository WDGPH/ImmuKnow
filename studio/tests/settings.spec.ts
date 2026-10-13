import { readFileSync } from "node:fs";
import { expect, type Page, test } from "@playwright/test";
import { unzipSync } from "fflate";
import { exportProject } from "../src/archive-core";
import type { Bundle, Files } from "../src/types";

async function current(page: Page) {
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
async function importSettings(page: Page, change: (source: string) => string) {
  await page.goto("./");
  await expect(page.locator("#import")).toBeEnabled();
  const bundle = (await (await page.request.get("./generated/project.json")).json()) as Bundle;
  const files: Files = Object.fromEntries(
    Object.entries(bundle.files).map(([path, bytes]) => [
      path,
      new Uint8Array(Buffer.from(bytes, "base64")),
    ]),
  );
  const source = change(new TextDecoder().decode(files["templates/settings.typ"]));
  files["templates/settings.typ"] = new TextEncoder().encode(source);
  const archive = await exportProject(files, "templates/overdue_diseases_v1.en.typ", bundle.build);
  await page.locator("#archive").setInputFiles({
    name: "settings.zip",
    mimeType: "application/zip",
    buffer: Buffer.from(archive),
  });
  await expect(page.locator("#archive")).toHaveValue("");
  await page.locator("#theme-tab").click();
  await current(page);
  return source;
}
async function downloadSettings(page: Page) {
  await page.locator(".project-actions summary").click();
  const pending = page.waitForEvent("download");
  await page.locator("#export").click();
  const path = await (await pending).path();
  return unzipSync(readFileSync(path as string))["templates/settings.typ"];
}

test("theme changes preserve commented examples and update the active QR fields", async ({
  page,
}) => {
  const source = await importSettings(
    page,
    (source) =>
      "\ufeff/*\n" +
      '#let body-font = "Commented"\n' +
      '/* nested sample */\n#let qr = (\n  module-shape: "commented",\n  corner-style: "commented",\n)\n*/\n' +
      source.replace(
        '  module-shape: "square",',
        '  /* module-shape: "commented field", */\n  module-shape: "square", // Keep this note',
      ),
  );
  await expect(page.locator("#body-font-picker")).toHaveValue("FreeSans");
  await page.locator("#health-unit-preset").selectOption("cedar-ridge");
  await expect(page.locator("#health-unit-undo")).toBeVisible();
  await current(page);
  await expect(page.locator("#body-font-picker")).toHaveValue("FreeSerif");
  const expected = source
    .replace('#let body-font = "FreeSans"', '#let body-font = "FreeSerif"')
    .replace("#let heading-color = black", '#let heading-color = rgb("#173e31")')
    .replace('#let link-color = rgb("#0000ee")', '#let link-color = rgb("#173e31")')
    .replace('#let accent-color = rgb("#005568")', '#let accent-color = rgb("#637c50")')
    .replace('module-shape: "square"', 'module-shape: "rounded"')
    .replace('corner-style: "square"', 'corner-style: "rounded"');
  expect(await downloadSettings(page)).toEqual(new TextEncoder().encode(expected));
  await page.locator("#health-unit-undo").click();
  await current(page);
  expect(await downloadSettings(page)).toEqual(new TextEncoder().encode(source));
});

test("calculated values stay in source editing and a refused theme leaves all Settings unchanged", async ({
  page,
}) => {
  const source = await importSettings(page, (source) =>
    source
      .replace(
        '#let body-font = "FreeSans"',
        '#let body-font = if true { "FreeSans" } else { "FreeSerif" }',
      )
      .replace('#let logo = image("assets/logo.png",', '#let logo = image("assets/" + "logo.png",')
      .replace(
        '#let signature-name = "Dr. Annie Body"',
        '#let signature-name = if true { "Dr. Annie Body" } else { "Dr. Other" }',
      ),
  );
  await expect(page.locator("#body-font-picker")).toBeDisabled();
  await expect(page.locator("#body-font-picker")).toHaveValue("");
  await expect(page.locator("#body-font-picker option:checked")).toHaveText("Edit in Settings");
  await expect(page.locator("#signature-name-picker")).toBeDisabled();
  await expect(page.locator("#signature-name-picker")).toHaveValue("");
  await expect(page.locator("#logo-upload")).toBeDisabled();
  await expect(page.locator("#logo-empty")).toHaveText("Edit in Settings");
  await page.locator("#health-unit-preset").selectOption("trillium-valley");
  await expect(page.locator("#diagnostics")).toContainText(
    /Edit (signature-name|body-font|logo) in Settings/,
  );
  await expect(page.locator("#health-unit-undo")).toBeHidden();
  expect(await downloadSettings(page)).toEqual(new TextEncoder().encode(source));
  await page.locator("#settings-tab").click();
  await expect(page.locator(".cm-content")).toHaveAttribute("contenteditable", "true");
});
