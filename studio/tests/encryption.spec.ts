import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

// The full Chromium browser includes its ordinary PDF viewer; headless shell does not.
test.use({ channel: "chromium", locale: "en-US" });

for (const [language, password] of [
  ["en", "Example-2026"],
  ["fr", "Été-2026-Чтение"],
]) {
  test(`encrypted ${language} notice opens in the PDF viewer only with its password`, async ({
    page,
    browser,
  }, info) => {
    const directory = info.outputPath("notice");
    execFileSync(
      "uv",
      [
        "run",
        "python",
        "-c",
        `
import sys
from pathlib import Path
from immuknow.encrypt_notices import encrypt_notice
from tests.fixtures.sample_input import create_test_client_record
from tests.integration.test_native_templates import prepare_case, compile_case
directory = Path(sys.argv[1])
job, _ = prepare_case(directory, language=sys.argv[2])
compile_case(job)
encrypt_notice(create_test_client_record(), job.pdf, directory / "encrypted.pdf", {"password": {"template": sys.argv[3]}})
`,
        directory,
        language,
        password,
      ],
      { cwd: resolve(".."), timeout: 60_000 },
    );
    const pdf = readFileSync(resolve(directory, "encrypted.pdf"));
    await page.route("**/encrypted-notice.pdf", (route) =>
      route.fulfill({ contentType: "application/pdf", body: pdf }),
    );
    await page.goto("encrypted-notice.pdf");
    await expect
      .poll(() =>
        page
          .frames()
          .find((frame) => frame.url().startsWith("chrome-extension://"))
          ?.url(),
      )
      .toBeTruthy();
    const viewer = page.frames().find((frame) => frame.url().startsWith("chrome-extension://"));
    expect(viewer).toBeDefined();
    if (!viewer) throw new Error("Chromium PDF viewer did not open");
    const input = viewer.locator('input[type="password"]');
    const submit = viewer.getByRole("button", { name: "Submit", exact: true });
    await expect(input).toBeVisible();
    await expect(viewer.locator("#pageSelector")).toBeHidden();
    await input.fill("wrong-password");
    await submit.click();
    await expect(viewer.locator("cr-input")).toHaveJSProperty("invalid", true);
    await expect(input).toBeVisible();
    await input.fill(password);
    await submit.click();
    await expect(input).toBeHidden();
    await expect(viewer.locator("pdf-viewer")).toHaveJSProperty("loadProgress_", 100);
    await expect(viewer.locator("#pageSelector")).toHaveValue("1");
    await page.screenshot({ path: info.outputPath("opened.png") });
    writeFileSync(
      info.outputPath("reader.json"),
      JSON.stringify(
        {
          reader: "Chromium PDF viewer",
          version: browser.version(),
          language,
          emptyPassword: "password required on opening",
          wrongPassword: "refused",
          correctPassword: "opened",
        },
        null,
        2,
      ),
    );
  });
}
