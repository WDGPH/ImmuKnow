import { expect, test } from "@playwright/test";
import { mkdir, readFile } from "node:fs/promises";

test("maintained notices compile to PDF with the pinned browser engine", async ({
  page,
  context,
}) => {
  const unexpected: string[] = [];
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await context.route("**/*", async (route) => {
    if (new URL(route.request().url()).origin !== "http://localhost:4173") {
      unexpected.push(route.request().url());
      await route.abort();
    } else await route.continue();
  });
  await page.goto("/ImmuKnow/playground/proof.html");
  await expect(page.locator("body")).toHaveAttribute("data-complete", /true|error/, {
    timeout: 120_000,
  });
  expect(
    await page.locator("body").getAttribute("data-complete"),
    (await page.locator("body").textContent()) ?? "",
  ).toBe("true");
  expect(errors).toEqual([]);
  expect(unexpected).toEqual([]);
  const links = page.getByRole("link");
  await expect(links).toHaveCount(5);
  await mkdir("test-results/proof", { recursive: true });
  for (const link of await links.all()) {
    const downloading = page.waitForEvent("download");
    await link.click();
    const download = await downloading;
    const output = `test-results/proof/${download.suggestedFilename()}`;
    await download.saveAs(output);
    const pdf = await readFile(output);
    expect(pdf.subarray(0, 5).toString()).toBe("%PDF-");
  }
});
