import { validateFiles, validateTemplate, verifyProjectBuild } from "./project";
import { verifyComponents } from "./component-resources";
import type { BuildInfo, Files } from "./types";

export interface Draft {
  schemaVersion: 2;
  revision: number;
  build: BuildInfo;
  files: Files;
  baseline: Files;
  template: string;
  example: string;
}
export type SaveState = "saving" | "saved" | "clearing" | "cleared" | "error";
const databaseName = "immuknow-studio-drafts-v2";
const key = "current";

function validateDraft(draft: Draft, build: BuildInfo): void {
  if (draft.schemaVersion !== 2 || !Number.isSafeInteger(draft.revision) || draft.revision < 1)
    throw new Error(
      "This saved draft uses an unsupported format. Import a current project or clear the draft.",
    );
  if (!draft.files || !draft.baseline || typeof draft.template !== "string")
    throw new Error(
      "The saved draft is incomplete. Import your downloaded project or clear the draft.",
    );
  verifyProjectBuild(draft.build, build);
  validateFiles(draft.files);
  validateFiles(draft.baseline);
  validateTemplate(draft.files, draft.template);
  validateTemplate(draft.baseline, draft.template);
  if (typeof draft.example !== "string")
    throw new Error(
      "The saved draft is incomplete. Import your downloaded project or clear the draft.",
    );
}

// One connection and one active write. While it finishes, retain only the newest
// requested save or clear; an older completion must never report the newest edit saved.
export class DraftStore {
  private next: Draft | null | undefined;
  private writing = false;

  private constructor(
    private db: IDBDatabase,
    private build: BuildInfo,
    private changed: (state: SaveState) => void,
  ) {}

  static async open(build: BuildInfo, changed: (state: SaveState) => void): Promise<DraftStore> {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const request = indexedDB.open(databaseName, 1);
      request.onupgradeneeded = () => request.result.createObjectStore("drafts");
      request.onsuccess = () => resolve(request.result);
      request.onerror = () =>
        reject(new Error("Draft storage is unavailable. Download your project to keep your work."));
      request.onblocked = () =>
        reject(new Error("Close other Studio tabs, then reload to open draft storage."));
    });
    db.onversionchange = () => db.close();
    return new DraftStore(db, build, changed);
  }

  private transaction<T>(
    mode: IDBTransactionMode,
    operation: (store: IDBObjectStore) => IDBRequest<T>,
  ): Promise<T> {
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction("drafts", mode);
      const request = operation(tx.objectStore("drafts"));
      tx.oncomplete = () => resolve(request.result);
      tx.onerror = tx.onabort = () =>
        reject(new Error("Draft storage failed. Download your project to keep your work."));
    });
  }

  async load(): Promise<Draft | undefined> {
    const draft = await this.transaction<Draft | undefined>("readonly", (store) => store.get(key));
    if (draft) {
      validateDraft(draft, this.build);
      await verifyComponents(draft.files, this.build);
      await verifyComponents(draft.baseline, this.build);
    }
    return draft;
  }

  save(draft: Draft): void {
    validateDraft(draft, this.build);
    this.next = draft;
    this.changed("saving");
    void this.write();
  }

  clear(): void {
    this.next = null;
    this.changed("clearing");
    void this.write();
  }

  private async write(): Promise<void> {
    if (this.writing) return;
    this.writing = true;
    try {
      while (this.next !== undefined) {
        const next = this.next;
        this.next = undefined;
        try {
          if (next === null) await this.transaction("readwrite", (store) => store.delete(key));
          else await this.transaction("readwrite", (store) => store.put(next, key));
        } catch {
          // A newer save or clear still gets its own attempt after a failed write.
          if (this.next !== undefined) continue;
          this.next = next;
          this.changed("error");
          return;
        }
        if (this.next === undefined) this.changed(next === null ? "cleared" : "saved");
      }
    } finally {
      this.writing = false;
    }
  }
}

// The browser releases the lock when the editing page closes. A restored page
// must reload and acquire it again before it can read or change the draft.
export function claimEditingTab(): Promise<boolean> {
  if (!navigator.locks)
    return Promise.reject(new Error("Studio could not protect this draft. Try another browser."));
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) location.reload();
  });
  return new Promise((resolve, reject) => {
    void navigator.locks
      .request("immuknow-studio-editor-v2", { ifAvailable: true }, async (lock) => {
        if (!lock) {
          resolve(false);
          return;
        }
        await new Promise<void>((release) => {
          window.addEventListener("pagehide", () => release(), { once: true });
          resolve(true);
        });
      })
      .catch(reject);
  });
}
