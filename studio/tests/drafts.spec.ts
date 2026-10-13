import { readFileSync } from "node:fs";
import { expect, type Page, test } from "@playwright/test";
import { unzipSync } from "fflate";
import { exportProject } from "../src/archive-core";
import type { Draft } from "../src/drafts";
import type { Bundle, Files } from "../src/types";

const database = "immuknow-studio-drafts-v2";
const template = "templates/overdue_diseases_v1.en.typ";

declare global {
  interface Window {
    draftProbe: { hold: boolean; fail: boolean; abortNext: boolean; release: () => void };
  }
}

async function ready(page: Page) {
  await expect(page.locator("#template-tab")).toBeEnabled();
  await page.locator("#template-tab").click();
  await expect(page.locator(".cm-content")).not.toBeEmpty();
  await page.locator(".cm-content").press("Control+End");
}
async function saved(page: Page) {
  await expect(page.locator("#save-state")).toHaveAttribute("data-state", "saved");
}
async function append(page: Page, text: string) {
  await page.locator(".cm-content").click();
  await page.keyboard.press("Control+End");
  await page.keyboard.insertText(`\n// ${text}`);
}
async function menu(page: Page, id: string) {
  await page.locator(".project-actions").evaluate((element) => element.setAttribute("open", ""));
  await page.locator(`#${id}`).click();
}
async function stored(page: Page, name = database): Promise<Draft | undefined> {
  return page.evaluate(async (name) => {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open(name, 1);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
    try {
      return await new Promise<Draft | undefined>((resolve, reject) => {
        const request = db.transaction("drafts").objectStore("drafts").get("current");
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
    } finally {
      db.close();
    }
  }, name);
}
async function storageProbe(page: Page) {
  await page.addInitScript(() => {
    const pending: (() => void)[] = [];
    window.draftProbe = {
      hold: false,
      fail: false,
      abortNext: false,
      release: () => {
        window.draftProbe.hold = false;
        for (const done of pending.splice(0)) done();
      },
    };
    for (const eventName of ["oncomplete", "onabort", "onerror"]) {
      const descriptor = Object.getOwnPropertyDescriptor(IDBTransaction.prototype, eventName);
      if (!descriptor?.set) throw new Error("Missing transaction event");
      Object.defineProperty(IDBTransaction.prototype, eventName, {
        set(handler: (event: Event) => void) {
          descriptor.set?.call(this, (event: Event) => {
            const done = () => handler.call(this, event);
            if (this.mode === "readwrite" && window.draftProbe.hold) pending.push(done);
            else done();
          });
        },
      });
    }
    const put = IDBObjectStore.prototype.put;
    IDBObjectStore.prototype.put = function (value, key) {
      if (window.draftProbe.fail) throw new DOMException("Storage full", "QuotaExceededError");
      const request = put.call(this, value, key);
      if (window.draftProbe.abortNext) {
        window.draftProbe.abortNext = false;
        this.transaction.abort();
      }
      return request;
    };
  });
}

test("an immediate reload is guarded until the newest edit has saved", async ({ page }) => {
  await storageProbe(page);
  await page.goto("./");
  await ready(page);
  const position = await page.locator("#workspace").boundingBox();
  await append(page, "Earlier saved edit");
  await saved(page);
  expect(await page.locator("#workspace").boundingBox()).toEqual(position);
  const before = (await stored(page))?.revision ?? 0;
  await page.evaluate(() => {
    window.draftProbe.hold = true;
  });
  await append(page, "First pending edit");
  await append(page, "Newest edit survives reload");
  await expect(page.locator("#save-state")).toHaveAttribute("data-state", "saving");
  expect(await page.locator("#workspace").boundingBox()).toEqual(position);
  const prompt = page.waitForEvent("dialog");
  await page.evaluate(() => {
    setTimeout(() => location.reload(), 0);
  });
  const dialog = await prompt;
  expect(dialog.type()).toBe("beforeunload");
  await dialog.dismiss();
  await expect(page.locator(".cm-content")).toContainText("Newest edit survives reload");
  await page.evaluate(() => window.draftProbe.release());
  await saved(page);
  expect((await stored(page))?.revision).toBeGreaterThan(before);
  await page.reload();
  await ready(page);
  await expect(page.locator(".cm-content")).toContainText("Newest edit survives reload");
});

test("import replaces a pending save and retains its reset baseline after reload", async ({
  page,
}) => {
  await storageProbe(page);
  await page.goto("./");
  await ready(page);
  await page.evaluate(() => {
    window.draftProbe.hold = true;
  });
  await append(page, "Old project waiting to save");
  const bundle = (await (await page.request.get("./generated/project.json")).json()) as Bundle;
  const files: Files = Object.fromEntries(
    Object.entries(bundle.files).map(([name, bytes]) => [
      name,
      new Uint8Array(Buffer.from(bytes, "base64")),
    ]),
  );
  const custom = "templates/my_notice_v2.en.typ";
  files[custom] = new TextEncoder().encode(
    `${new TextDecoder().decode(files[template])}\n// Imported baseline`,
  );
  const archive = await exportProject(files, custom, bundle.build);
  await page.locator("#archive").setInputFiles({
    name: "authored.zip",
    mimeType: "application/zip",
    buffer: Buffer.from(archive),
  });
  await expect(page.locator("#archive")).toHaveValue("");
  await page.locator(".cm-content").press("Control+End");
  await expect(page.locator(".cm-content")).toContainText("Imported baseline");
  await page.evaluate(() => window.draftProbe.release());
  await saved(page);
  await page.reload();
  await ready(page);
  await expect(page.locator("#template")).toHaveValue(custom);
  await expect(page.locator(".cm-content")).not.toContainText("Old project waiting to save");
  await append(page, "Remove this edit on reset");
  await saved(page);
  await menu(page, "reset");
  await saved(page);
  await expect(page.locator(".cm-content")).toContainText("Imported baseline");
  await expect(page.locator(".cm-content")).not.toContainText("Remove this edit on reset");
  await page.reload();
  await ready(page);
  await expect(page.locator(".cm-content")).toContainText("Imported baseline");
  await expect(page.locator(".cm-content")).not.toContainText("Remove this edit on reset");
});

test("clearing cancels pending saves, preserves the open project and leaves older storage untouched", async ({
  page,
}) => {
  await storageProbe(page);
  await page.goto("./proof.html");
  await page.evaluate(async () => {
    await new Promise<void>((resolve, reject) => {
      const request = indexedDB.open("immuknow-studio-drafts", 1);
      request.onupgradeneeded = () => request.result.createObjectStore("drafts");
      request.onerror = () => reject(request.error);
      request.onsuccess = () => {
        const db = request.result;
        const tx = db.transaction("drafts", "readwrite");
        tx.objectStore("drafts").put({ schemaVersion: 1, text: "Keep my older work" }, "current");
        tx.oncomplete = () => {
          db.close();
          resolve();
        };
      };
    });
  });
  await page.goto("./");
  await ready(page);
  const legacy = await stored(page, "immuknow-studio-drafts");
  await page.evaluate(() => {
    window.draftProbe.hold = true;
  });
  await append(page, "Open work remains after clearing");
  await menu(page, "clear");
  await expect(page.locator("#save-state")).toHaveAttribute("data-state", "clearing");
  await page.evaluate(() => window.draftProbe.release());
  await expect(page.locator("#save-state")).toHaveAttribute("data-state", "cleared");
  expect(await stored(page)).toBeUndefined();
  expect(await stored(page, "immuknow-studio-drafts")).toEqual(legacy);
  await expect(page.locator(".cm-content")).toContainText("Open work remains after clearing");
  await append(page, "Editing saves again");
  await saved(page);
  await page.reload();
  await ready(page);
  await expect(page.locator(".cm-content")).toContainText("Editing saves again");
  expect(await stored(page, "immuknow-studio-drafts")).toEqual(legacy);
});

test("failed storage keeps current work downloadable and a later edit retries saving", async ({
  page,
}) => {
  await storageProbe(page);
  await page.goto("./");
  await ready(page);
  await append(page, "Saved before storage filled");
  await saved(page);
  await page.evaluate(() => {
    window.draftProbe.fail = true;
  });
  await append(page, "Keep this unsaved edit in the ZIP");
  await expect(page.locator("#save-state")).toHaveAttribute("data-state", "error");
  const pending = page.waitForEvent("download");
  await menu(page, "export");
  const path = await (await pending).path();
  const files = unzipSync(readFileSync(path as string));
  expect(new TextDecoder().decode(files[template])).toContain("Keep this unsaved edit in the ZIP");
  await page.evaluate(() => {
    window.draftProbe.fail = false;
  });
  await append(page, "Retry succeeds");
  await saved(page);
  await page.reload();
  await ready(page);
  await expect(page.locator(".cm-content")).toContainText("Keep this unsaved edit in the ZIP");
  await expect(page.locator(".cm-content")).toContainText("Retry succeeds");
});

test("a second tab cannot overwrite the draft and can reopen it after the first closes", async ({
  page,
  context,
}) => {
  await page.goto("./");
  await ready(page);
  await append(page, "Work from the first tab");
  await saved(page);
  const second = await context.newPage();
  await second.goto("./");
  await expect(second.locator("#storage")).toContainText("Studio is open in another tab");
  await expect(second.locator("#workspace")).toHaveAttribute("inert", "");
  await expect(second.locator("#import")).toBeDisabled();
  await page.close();
  await second.reload();
  await ready(second);
  await expect(second.locator(".cm-content")).toContainText("Work from the first tab");
  await append(second, "Work from the next tab");
  await saved(second);
  await second.reload();
  await ready(second);
  await expect(second.locator(".cm-content")).toContainText("Work from the next tab");
});

test("a requested clear still finishes after the preceding write fails", async ({ page }) => {
  await storageProbe(page);
  await page.goto("./");
  await ready(page);
  await append(page, "Earlier saved work");
  await saved(page);
  await page.evaluate(() => {
    window.draftProbe.hold = true;
    window.draftProbe.abortNext = true;
  });
  await append(page, "This write is aborted");
  await menu(page, "clear");
  await expect(page.locator("#save-state")).toHaveAttribute("data-state", "clearing");
  await page.evaluate(() => window.draftProbe.release());
  await expect(page.locator("#save-state")).toHaveAttribute("data-state", "cleared");
  expect(await stored(page)).toBeUndefined();
});

test("unavailable storage leaves editing and project download available", async ({ page }) => {
  await page.addInitScript(() => {
    indexedDB.open = () => {
      throw new DOMException("Storage denied", "SecurityError");
    };
  });
  await page.goto("./");
  await ready(page);
  await append(page, "Work without local storage");
  await expect(page.locator("#save-state")).toHaveAttribute("data-state", "error");
  const pending = page.waitForEvent("download");
  await menu(page, "export");
  const path = await (await pending).path();
  const files = unzipSync(readFileSync(path as string));
  expect(new TextDecoder().decode(files[template])).toContain("Work without local storage");
});

for (const incompatible of [
  "format",
  "build",
  "template",
  "library",
  "baseline-library",
] as const) {
  test(`an unsupported draft ${incompatible} is retained until explicitly cleared`, async ({
    page,
  }) => {
    await page.goto("./");
    await ready(page);
    await append(page, "Retain this unsupported draft");
    await saved(page);
    await page.goto("./proof.html");
    await page.evaluate(
      async ({ database, incompatible }) => {
        const db = await new Promise<IDBDatabase>((resolve) => {
          const request = indexedDB.open(database, 1);
          request.onsuccess = () => resolve(request.result);
        });
        await new Promise<void>((resolve) => {
          const tx = db.transaction("drafts", "readwrite");
          const store = tx.objectStore("drafts");
          const read = store.get("current");
          read.onsuccess = () => {
            const draft = read.result;
            if (incompatible === "format") draft.schemaVersion = 99;
            else if (incompatible === "build") draft.build.shared_resources.sha256 = "unsupported";
            else if (incompatible === "library" || incompatible === "baseline-library") {
              const target = incompatible === "library" ? draft.files : draft.baseline;
              target["templates/lib/immuknow/lib.typ"] = new TextEncoder().encode(
                "Changed library",
              );
            } else {
              draft.template = "config/notice.en.typ";
              draft.files[draft.template] = new TextEncoder().encode("Wrong directory");
              draft.baseline[draft.template] = draft.files[draft.template];
            }
            store.put(draft, "current");
          };
          tx.oncomplete = () => {
            db.close();
            resolve();
          };
        });
      },
      { database, incompatible },
    );
    const before = await stored(page);
    await page.goto("./");
    await ready(page);
    await expect(page.locator("#storage")).toContainText(
      incompatible === "format"
        ? "unsupported format"
        : incompatible === "build"
          ? "different ImmuKnow format"
          : incompatible === "template"
            ? "entry point"
            : "differs from the supplied version",
    );
    await append(page, "Do not replace stored work without clearing");
    await expect(page.locator("#save-state")).toHaveAttribute("data-state", "error");
    expect(await stored(page)).toEqual(before);
    await menu(page, "clear");
    await expect(page.locator("#save-state")).toHaveAttribute("data-state", "cleared");
    expect(await stored(page)).toBeUndefined();
    await append(page, "Now save the open project");
    await saved(page);
    expect((await stored(page))?.schemaVersion).toBe(2);
  });
}
