import "./style.css";
import { SourceEditor } from "./editor";
import { Viewer } from "./viewer";
import { Compiler } from "./compile";
import { archiveJob } from "./archive";
import {
  base64,
  decodeFiles,
  download,
  editableFile,
  MAX_PROJECT,
  runtimeFiles,
  safePath,
  textFile,
  validateFiles,
} from "./project";
import type { Bundle, Diagnostic, Example, Files } from "./types";

const element = <T extends HTMLElement = HTMLElement>(id: string) =>
  document.getElementById(id) as T;
const button = (id: string) => element<HTMLButtonElement>(id);
const templateSelect = element<HTMLSelectElement>("template");
const clientSelect = element<HTMLSelectElement>("client");
const status = (message: string) => {
  element("status").textContent = message;
};
const storageKey = "immuknow:project:v1";
let bundle: Bundle, defaults: Files, files: Files;
let activeTemplate = "templates/overdue_diseases_v1.en.typ";
let activeExample = "short";
let examples: Example[] = [];
let currentPDF:
  | { revision: number; bytes: Uint8Array; template: string; example: string }
  | undefined;
let diagnostics: Diagnostic[] = [];
let saveTimer: ReturnType<typeof setTimeout>;
let compiler: Compiler;

const viewer = new Viewer(element("canvas"), element("paper"), element("overlay"), () => {
  element("pages").textContent = `${viewer.page} / ${viewer.pages}`;
  button("page-prev").disabled = viewer.page <= 1;
  button("page-next").disabled = viewer.page >= viewer.pages;
});
const editor = new SourceEditor(element("editor"), (name, bytes) => {
  files[name] = bytes;
  scheduleSave();
  requestCompile();
});
function scheduleSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(save, 450);
}
function save() {
  if (!files) return;
  try {
    const changes: Record<string, string> = {};
    for (const [name, value] of Object.entries(files)) {
      const encoded = base64(value);
      if (encoded !== bundle.files[name]) changes[name] = encoded;
    }
    const deleted = Object.keys(defaults).filter((name) => !files[name]);
    localStorage.setItem(
      storageKey,
      JSON.stringify({
        version: 1,
        files: changes,
        deleted,
        template: activeTemplate,
        example: activeExample,
      }),
    );
    element("storage").textContent =
      "Drafts saved in this browser. Download a project for a durable copy.";
  } catch {
    element("storage").textContent =
      "Browser storage is unavailable or full. Your edits work here, but download a project before leaving.";
  }
}
function restore() {
  try {
    const stored = localStorage.getItem(storageKey);
    if (!stored) return;
    if (stored.length > MAX_PROJECT * 2) throw new Error("Oversized draft");
    const draft = JSON.parse(stored);
    if (draft.version !== 1 || typeof draft.files !== "object" || !Array.isArray(draft.deleted))
      throw new Error("Unsupported draft");
    const restored = { ...files };
    for (const name of draft.deleted) delete restored[safePath(name)];
    for (const [name, value] of Object.entries(draft.files)) {
      if (typeof value !== "string") throw new Error("Invalid draft file");
      restored[safePath(name)] = Uint8Array.from(atob(value), (c) => c.charCodeAt(0));
    }
    validateFiles(restored);
    files = restored;
    if (typeof draft.template === "string" && files[draft.template])
      activeTemplate = draft.template;
    if (typeof draft.example === "string") activeExample = draft.example;
  } catch {
    element("storage").textContent =
      "Saved drafts could not be loaded. The maintained project is open; storage may be unavailable.";
  }
}
function openFile(name: string) {
  if (!files[name]) return;
  if (!textFile(name)) {
    status(
      `${name} · ${files[name].length.toLocaleString()} bytes. Replace binary assets by importing an edited project ZIP.`,
    );
    return;
  }
  try {
    editor.open(name, files[name]);
  } catch (error) {
    status(`Cannot edit ${name}: ${error}`);
    return;
  }
  element("filename").textContent = name;
  for (const child of element("files").querySelectorAll("button"))
    child.setAttribute("aria-current", String(child.dataset.path === name));
  editor.diagnostics(diagnostics);
}
function refreshFiles() {
  const panel = element("files");
  panel.replaceChildren();
  for (const name of Object.keys(files).filter(editableFile).sort()) {
    const item = document.createElement("button");
    item.textContent = name;
    item.dataset.path = name;
    item.addEventListener("click", () => openFile(name));
    panel.append(item);
  }
}
function refreshTemplates() {
  templateSelect.replaceChildren();
  for (const name of Object.keys(files)
    .filter((name) => /^templates\/[^/]+\.(en|fr)\.typ$/.test(name))
    .sort()) {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name
      .replace("templates/", "")
      .replace(".en.typ", " · English")
      .replace(".fr.typ", " · Français");
    templateSelect.append(option);
  }
  templateSelect.value = activeTemplate;
}
function refreshClients() {
  examples = bundle.examples.filter(
    (example) => example.payloads[activeTemplate.replace("templates/", "")],
  );
  if (!examples.some((example) => example.id === activeExample))
    activeExample = examples[0]?.id ?? "";
  clientSelect.replaceChildren();
  for (const example of examples) {
    const option = document.createElement("option");
    option.value = example.id;
    option.textContent = example.label;
    clientSelect.append(option);
  }
  clientSelect.value = activeExample;
  const index = examples.findIndex((example) => example.id === activeExample);
  element("position").textContent = examples.length
    ? `${index + 1} of ${examples.length}`
    : "No compatible examples";
  element("scenario").textContent =
    examples[index]?.description ??
    "Use a maintained notice identity to test these fixtures. Register custom notice versions explicitly in your production catalog.";
  button("previous").disabled = index <= 0;
  button("next").disabled = index >= examples.length - 1;
  clientSelect.disabled = !examples.length;
}
function markStale() {
  button("pdf").disabled = true;
  element("preview-caption").classList.add("stale");
  element("preview-caption").textContent = currentPDF
    ? `Stale preview: ${currentPDF.template.split("/").pop()} / ${currentPDF.example}`
    : "Waiting for a document";
}
function requestCompile() {
  markStale();
  if (!compiler || !bundle) return;
  const example = examples.find((item) => item.id === activeExample);
  if (!example) {
    compiler.invalidate();
    status("No prepared example matches this notice identity.");
    return;
  }
  try {
    validateFiles(files);
    compiler.submit({
      template: activeTemplate,
      example: activeExample,
      files: runtimeFiles(files, defaults),
      notice: example.payloads[activeTemplate.replace("templates/", "")],
    });
  } catch (error) {
    compiler.invalidate();
    status(String(error));
  }
}
function showDiagnostics(items: Diagnostic[]) {
  diagnostics = items;
  const list = element("diagnostics");
  list.replaceChildren();
  for (const diagnostic of items) {
    const item = document.createElement("li");
    item.className = diagnostic.severity;
    const path = diagnostic.path.replace(/^\//, "");
    if (files[path] && textFile(path)) {
      const link = document.createElement("button");
      link.textContent = `${path}${diagnostic.range ? `:${diagnostic.range}` : ""}`;
      link.addEventListener("click", () => {
        openFile(path);
        editor.jump(Number(diagnostic.range.split(":")[0]) || 1);
      });
      item.append(link);
    }
    item.append(document.createTextNode(diagnostic.message));
    list.append(item);
  }
  editor.diagnostics(items);
}
function changeClient(delta: number) {
  const index = examples.findIndex((item) => item.id === activeExample);
  activeExample = examples[index + delta]?.id ?? activeExample;
  refreshClients();
  scheduleSave();
  requestCompile();
}

async function initialize() {
  const response = await fetch(`${import.meta.env.BASE_URL}generated/project.json`);
  if (!response.ok) throw new Error("Project assets are missing. Run the synthetic example build.");
  bundle = await response.json();
  if (bundle.schemaVersion !== 1 || !bundle.synthetic || bundle.compilerVersion !== "0.15.1")
    throw new Error("Unsupported project bundle.");
  defaults = decodeFiles(bundle);
  files = { ...defaults };
  restore();
  refreshTemplates();
  refreshClients();
  refreshFiles();
  openFile(activeTemplate);
  for (const id of ["source", "export", "reset", "clear"]) button(id).disabled = false;
  templateSelect.disabled = false;
  compiler = new Compiler(
    (message) => {
      markStale();
      status(message);
    },
    (reply) => {
      showDiagnostics(reply.diagnostics);
      if (!reply.pdf) {
        status("Compilation failed. The previous preview is stale.");
        return;
      }
      const pdf = reply.pdf;
      const revision = reply.revision,
        template = activeTemplate,
        example = activeExample;
      status("Rendering PDF…");
      void viewer
        .open(pdf)
        .then(() => {
          if (compiler.revision !== revision) return;
          currentPDF = { revision, bytes: pdf, template, example };
          button("pdf").disabled = false;
          element("preview-caption").classList.remove("stale");
          element("preview-caption").textContent =
            `${template.split("/").pop()} / ${example} · revision ${revision}`;
          const warning = viewer.layoutWarning();
          const findings = warning
            ? [
                ...reply.diagnostics,
                { path: template, range: "", severity: "warning", message: warning },
              ]
            : reply.diagnostics;
          showDiagnostics(findings);
          status(
            findings.some((item) => item.severity === "warning") ? "Ready with warnings" : "Ready",
          );
        })
        .catch((error) => {
          if (compiler.revision === revision) {
            markStale();
            status(`PDF preview failed: ${error}`);
          }
        });
    },
  );
  requestCompile();
}

templateSelect.addEventListener("change", () => {
  activeTemplate = templateSelect.value;
  refreshClients();
  openFile(activeTemplate);
  scheduleSave();
  requestCompile();
});
clientSelect.addEventListener("change", () => {
  activeExample = clientSelect.value;
  refreshClients();
  scheduleSave();
  requestCompile();
});
button("previous").onclick = () => changeClient(-1);
button("next").onclick = () => changeClient(1);
button("files-toggle").onclick = () => {
  const panel = element("files");
  panel.hidden = !panel.hidden;
  button("files-toggle").setAttribute("aria-expanded", String(!panel.hidden));
};
button("source").onclick = () =>
  download(
    activeTemplate.slice(activeTemplate.lastIndexOf("/") + 1),
    files[activeTemplate],
    "text/plain;charset=utf-8",
  );
button("pdf").onclick = () => {
  if (
    currentPDF?.revision === compiler.revision &&
    currentPDF.template === activeTemplate &&
    currentPDF.example === activeExample
  )
    download(
      `${activeTemplate.slice(activeTemplate.lastIndexOf("/") + 1).replace(".typ", "")}-${activeExample}.pdf`,
      currentPDF.bytes,
      "application/pdf",
    );
};
button("restart").onclick = () => {
  if (compiler) {
    compiler.restart();
    requestCompile();
  }
};
button("reset").onclick = () => {
  if (!defaults[editor.file]) {
    status(
      "This imported file has no maintained original. Import a replacement project to reset it.",
    );
    return;
  }
  if (!confirm(`Reset ${editor.file} to the maintained version?`)) return;
  const name = editor.file;
  files[name] = defaults[name];
  editor.resetFile(name);
  openFile(name);
  scheduleSave();
  requestCompile();
};
button("clear").onclick = () => {
  if (
    !confirm(
      "Clear every draft and restore the maintained project? Download a project first if you want to keep your edits.",
    )
  )
    return;
  clearTimeout(saveTimer);
  try {
    localStorage.removeItem(storageKey);
  } catch {
    /* Session reset still works without storage. */
  }
  files = { ...defaults };
  activeTemplate = "templates/overdue_diseases_v1.en.typ";
  activeExample = "short";
  editor.clear();
  refreshTemplates();
  refreshClients();
  refreshFiles();
  openFile(activeTemplate);
  save();
  requestCompile();
};
button("export").onclick = async () => {
  button("export").disabled = true;
  try {
    download(
      "immuknow-template-project.zip",
      await archiveJob({ action: "export", files, template: activeTemplate }),
      "application/zip",
    );
  } catch (error) {
    status(String(error));
  } finally {
    button("export").disabled = false;
  }
};
button("import").onclick = () => element<HTMLInputElement>("archive").click();
element<HTMLInputElement>("archive").onchange = async (event) => {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  if (file.size > MAX_PROJECT) {
    status("Project archive exceeds 24 MB.");
    return;
  }
  status("Checking project archive…");
  try {
    const project = await archiveJob({
      action: "import",
      bytes: new Uint8Array(await file.arrayBuffer()),
    });
    if (
      !confirm(
        "Replace the current project with this imported draft? Existing edits are replaced; export first if you need a copy.",
      )
    )
      return;
    files = project.files;
    activeTemplate = project.template;
    editor.clear();
    refreshTemplates();
    refreshClients();
    refreshFiles();
    openFile(activeTemplate);
    scheduleSave();
    requestCompile();
  } catch (error) {
    status(`Import rejected: ${error}`);
  }
};
button("page-prev").onclick = () => void viewer.go(-1);
button("page-next").onclick = () => void viewer.go(1);
element<HTMLSelectElement>("zoom").onchange = (event) => {
  const value = (event.target as HTMLSelectElement).value;
  viewer.zoom = value === "fit" ? "fit" : Number(value);
  void viewer.render();
};
element<HTMLInputElement>("guide").onchange = (event) =>
  viewer.setGuide((event.target as HTMLInputElement).checked);
const divider = element("divider");
let split = 50;
function resize(value: number) {
  split = Math.max(25, Math.min(75, value));
  element("workspace").style.setProperty("--split", `${split}%`);
  divider.setAttribute("aria-valuenow", String(Math.round(split)));
}
divider.onkeydown = (event) => {
  if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
    event.preventDefault();
    resize(split + (event.key === "ArrowLeft" ? -2 : 2));
  }
};
divider.onpointerdown = (event) => {
  divider.setPointerCapture(event.pointerId);
  divider.onpointermove = (move) => {
    const rect = element("workspace").getBoundingClientRect();
    resize(((move.clientX - rect.left) / rect.width) * 100);
  };
  divider.onpointerup = () => {
    divider.onpointermove = null;
  };
};
window.addEventListener("pagehide", () => {
  clearTimeout(saveTimer);
  save();
  compiler?.destroy();
});
void initialize().catch((error) => status(`Unable to start playground: ${error}`));
