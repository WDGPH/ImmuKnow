import { exportProject, importProject } from "./archive-core";
globalThis.onmessage = async (event) => {
  try {
    const result =
      event.data.action === "export"
        ? await exportProject(event.data.files, event.data.template)
        : importProject(event.data.bytes);
    postMessage({ result });
  } catch (error) {
    postMessage({ error: String(error) });
  }
};
