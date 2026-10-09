import type { Files } from "./types";
export function archiveJob(request: {
  action: "export";
  files: Files;
  template: string;
}): Promise<Uint8Array>;
export function archiveJob(request: {
  action: "import";
  bytes: Uint8Array;
}): Promise<{ files: Files; template: string }>;
export function archiveJob(request: unknown): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const worker = new Worker(new URL("./archive.worker.ts", import.meta.url), { type: "module" });
    const timer = setTimeout(() => {
      worker.terminate();
      reject(new Error("Archive processing exceeded 10 seconds; no files were changed."));
    }, 10_000);
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
