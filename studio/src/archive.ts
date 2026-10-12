import type { BuildInfo, Files } from "./types";

export type ArchiveRequest =
  | { action: "export"; files: Files; template: string; build: BuildInfo }
  | { action: "import"; bytes: Uint8Array; build: BuildInfo };

export function archiveJob(
  request: Extract<ArchiveRequest, { action: "export" }>,
): Promise<Uint8Array>;
export function archiveJob(
  request: Extract<ArchiveRequest, { action: "import" }>,
): Promise<{ files: Files; template: string }>;
export function archiveJob(request: ArchiveRequest): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL("./archive.worker.ts", import.meta.url), { type: "module" });
    const timer = setTimeout(() => {
      worker.terminate();
      reject(new Error("Archive processing exceeded 30 seconds; no files were changed."));
    }, 30_000);
    worker.onmessage = (event) => {
      clearTimeout(timer);
      worker.terminate();
      if (event.data.error) reject(new Error(event.data.error));
      else resolve(event.data.result);
    };
    worker.onerror = () => {
      clearTimeout(timer);
      worker.terminate();
      reject(new Error("Archive processing failed; no files were changed."));
    };
    worker.postMessage(request);
  });
}
