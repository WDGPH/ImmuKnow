import type { ArchiveRequest } from "./archive";
import { exportProject, importProject } from "./archive-core";

globalThis.onmessage = async (event: MessageEvent<ArchiveRequest>) => {
  try {
    const request = event.data;
    const result =
      request.action === "export"
        ? await exportProject(request.files, request.template, request.build)
        : await importProject(request.bytes, request.build);
    postMessage({ result });
  } catch (error) {
    postMessage({ error: String(error) });
  }
};
