import "./style.css";
import { archiveJob } from "./archive";
import { imageBytes, imagePath, relativeImage } from "./branding";
import { Compiler, type CompileInput } from "./compile";
import { claimEditingTab, DraftStore, type SaveState } from "./drafts";
import { SourceEditor } from "./editor";
import { withProjectFonts } from "./fonts";
import { fontFamilies } from "./font-resources";
import { healthUnits, themedSettings } from "./health-units";
import { initializeHelp } from "./help";
import {
  decodeFiles,
  download,
  MAX_PROJECT,
  runtimeFiles,
  settingsPath,
  validateFiles,
} from "./project";
import { sourceLocation } from "./source-location";
import { initializeTheme } from "./theme";
import { settingValue, updateThemeSettings } from "./theme-settings";
import type { Bundle, CheckResult, CompileResult, Diagnostic, Example, Files } from "./types";
import { Viewer } from "./viewer";

const byId = <T extends HTMLElement = HTMLElement>(id: string): T => {
  const element = document.getElementById(id);
  if (!element) throw new Error(`Missing interface element: ${id}`);
  return element as T;
};
const button = (id: string) => byId<HTMLButtonElement>(id);
const select = (id: string) => byId<HTMLSelectElement>(id);
const basename = (path: string) => path.split("/").at(-1) ?? path;
const message = (error: unknown) => (error instanceof Error ? error.message : String(error));

initializeTheme();
let bundle: Bundle;
let originals: Files;
let files: Files = {};
let template = "";
let example: Example | undefined;
let tab: "template" | "settings" | "theme" = "template";
let compiler: Compiler;
let revision = 0;
let exporting = false;
let displayedRevision = 0;
let displayedContext = -1;
let diagnosticRevision = 0;
let currentChecks: CheckResult[] = [];
let pending = false;
let diagnostics: Diagnostic[] = [];
let resultChecks: CheckResult[] = [];
let actionError: string | undefined;
let compilerError: string | undefined;
let draftStore: DraftStore | undefined;
let draftRevision = 0;
let canSave = false;
let unsaved = false;
let themeUndo: Files | undefined;
const imageURLs = new Map<string, string>();

function storageError(error: unknown) {
  const target = byId("storage");
  target.textContent = message(error);
  target.hidden = false;
  byId("save-state").hidden = true;
}
function saveState(state: SaveState) {
  unsaved = !["saved", "cleared"].includes(state);
  const target = byId("save-state");
  target.dataset.state = state;
  target.textContent = {
    saving: "Saving…",
    saved: "Saved",
    clearing: "Clearing…",
    cleared: "Draft cleared",
    error: "",
  }[state];
  target.hidden = false;
  byId("storage").hidden = state !== "error";
  if (state === "error") storageError("Not saved. Download your project to keep your work.");
}
function persist() {
  unsaved = true;
  if (!draftStore || !canSave) {
    saveState("error");
    return;
  }
  try {
    draftStore.save({
      schemaVersion: 2,
      revision: ++draftRevision,
      build: bundle.build,
      files,
      baseline: originals,
      template,
      example: example?.id ?? "",
    });
  } catch (error) {
    saveState("error");
    storageError(error);
  }
}
window.addEventListener("beforeunload", (event) => {
  if (!unsaved) return;
  event.preventDefault();
  event.returnValue = "";
});

const editor = new SourceEditor(byId("editor"), (name, bytes) => {
  files = { ...files, [name]: bytes };
  themeUndo = undefined;
  button("health-unit-undo").hidden = true;
  persist();
  compile();
});
const viewer = new Viewer(
  byId("preview-scroll"),
  () => {
    byId("pages").textContent = viewer.pages ? `${viewer.page} / ${viewer.pages}` : "—";
  },
  (text) => {
    if (displayedRevision !== revision || displayedContext !== compiler.context) return false;
    const location = sourceLocation(files, template, text);
    if (!location) return false;
    openSource(location.path);
    editor.highlight(location.from, location.to);
    return true;
  },
);

function compatibleExamples(): Example[] {
  return bundle.examples.filter((item) => Object.hasOwn(item.payloads, basename(template)));
}
function refreshNavigation() {
  const available = compatibleExamples();
  const index = available.findIndex((item) => item.id === example?.id);
  byId("position").textContent = index < 0 ? "—" : `${index + 1} of ${available.length}`;
  byId("position").title = example
    ? `${example.label}: ${example.description}`
    : "No prepared example for this entry";
  button("previous").disabled = index <= 0;
  button("next").disabled = index < 0 || index >= available.length - 1;
}
function refreshDownloads() {
  button("export").disabled = exporting || !files[template];
  button("reset").disabled = !originals?.[editor.file];
}
function findings() {
  const target = byId("diagnostics");
  target.replaceChildren();
  function item(
    text: string,
    error: boolean,
    navigate?: () => void,
    measurements?: Record<string, unknown>,
  ) {
    const line = document.createElement("li");
    line.className = error ? "error" : "warning";
    if (navigate) {
      const link = document.createElement("button");
      link.textContent = text;
      link.onclick = navigate;
      line.append(link);
    } else line.textContent = text;
    if (measurements) {
      const detail = document.createElement("details"),
        label = document.createElement("summary"),
        value = document.createElement("pre");
      label.textContent = "Measurements";
      value.textContent = Object.entries(measurements)
        .map(([key, value]) => {
          const label = key.replace(/_pt$/, "").replaceAll("_", " ");
          return `${label}: ${typeof value === "number" && key.endsWith("_pt") ? `${((value * 25.4) / 72).toFixed(1)} mm` : JSON.stringify(value)}`;
        })
        .join("\n");
      detail.append(label, value);
      line.append(detail);
    }
    target.append(line);
  }
  if (compilerError) item(compilerError, true);
  if (actionError) item(actionError, true);
  for (const diagnostic of diagnostics) {
    const path = diagnostic.path.replace(/^\//, "");
    item(
      `Current source · ${diagnostic.path}:${diagnostic.range} · ${diagnostic.message}`,
      diagnostic.severity !== "warning",
      files[path]
        ? () => {
            openSource(path);
            editor.jump(Number(diagnostic.range.match(/^(\d+):/)?.[1] ?? 0) + 1);
          }
        : undefined,
    );
  }
  const checks = [
    ...(example?.preparationChecks[basename(template)] ?? []).map((check) => ({
      check,
      prefix: "",
    })),
    ...currentChecks.map((check) => ({ check, prefix: "Current edits · " })),
    ...resultChecks.map((check) => ({
      check,
      prefix: displayedRevision !== revision ? "Last successful preview · " : "",
    })),
  ];
  for (const { check, prefix } of checks) {
    if (!["warn", "fail"].includes(check.status)) continue;
    item(
      `${prefix}${check.message}${check.page ? ` · Page ${check.page}` : ""} (${check.code})`,
      check.status === "fail",
      undefined,
      check.measurements,
    );
  }
  byId("feedback").hidden = !target.childElementCount;
  editor.diagnostics(diagnosticRevision === revision ? diagnostics : []);
}
function previewStatus() {
  const target = byId("preview-state");
  const stale = displayedRevision > 0 && displayedRevision !== revision;
  target.dataset.state = pending ? "updating" : stale ? "stale" : "ready";
  target.dataset.context = String(compiler?.context ?? 0);
  target.dataset.requestedRevision = String(revision);
  target.dataset.displayedRevision = String(displayedRevision);
  target.dataset.displayedContext = String(displayedContext);
  const text = pending
    ? displayedRevision
      ? "Updating… Preview shows the last successful version."
      : "Preparing preview…"
    : stale
      ? "Preview shows the last successful version; current edits contain errors."
      : !displayedRevision
        ? "No current preview available."
        : "Preview is current.";
  target.setAttribute("aria-label", text);
  target.title = text;
}
function newContext() {
  compiler?.invalidate();
  displayedContext = -1;
  displayedRevision = 0;
  resultChecks = [];
  viewer.clear();
}
function compile(replace = false) {
  if (replace) newContext();
  diagnostics = [];
  diagnosticRevision = 0;
  currentChecks = [];
  actionError = undefined;
  compilerError = undefined;
  pending = true;
  refreshNavigation();
  const notice = example?.payloads[basename(template)];
  if (!example || !notice) {
    revision = compiler.revision;
    actionError =
      "This entry has no prepared example. Your project is preserved; choose a template starter to preview an authored example.";
    pending = false;
  } else {
    try {
      const requestedInput: CompileInput = {
        template,
        example: example.id,
        files: runtimeFiles(files),
        notice,
        creationTimestamp: bundle.creationTimestamp,
      };
      revision = compiler.submit(requestedInput, replace);
    } catch (error) {
      // Failed request preparation invalidates the previous preview.
      compiler.invalidate();
      revision = compiler.revision;
      actionError = message(error);
      pending = false;
    }
  }
  previewStatus();
  refreshDownloads();
  findings();
}
async function compiled(result: CompileResult) {
  if (result.context !== compiler.context) return;
  if (result.revision === revision) {
    diagnosticRevision = result.revision;
    diagnostics = result.diagnostics;
    currentChecks = result.preview ? [] : result.checks;
    if (!result.preview) pending = false;
    findings();
    previewStatus();
  }
  if (!result.preview || result.revision <= displayedRevision) return;
  const checks = [...(result.summary?.checks ?? []), ...result.checks];
  try {
    const committed = await viewer.open(result.preview, checks, result.timing);
    if (!committed || result.context !== compiler.context || result.revision <= displayedRevision)
      return;
    displayedContext = result.context;
    displayedRevision = result.revision;
    resultChecks = checks;
    if (result.revision === revision) {
      pending = false;
    }
    previewStatus();
    findings();
    refreshDownloads();
  } catch (error) {
    if (result.context !== compiler.context || result.revision !== revision) return;
    actionError = `Could not display the compiled notice: ${message(error)}`;
    pending = false;
    previewStatus();
    findings();
  }
}

function openSource(path: string) {
  if (!files[path]) return;
  tab = path === settingsPath(files, template) ? "settings" : "template";
  updateTabs();
  editor.open(path, files[path]);
  editor.diagnostics(diagnosticRevision === revision ? diagnostics : []);
  refreshDownloads();
}
function updateTabs() {
  for (const name of ["theme", "template", "settings"] as const) {
    const target = button(`${name}-tab`);
    target.setAttribute("aria-selected", String(tab === name));
    target.tabIndex = tab === name ? 0 : -1;
  }
  byId("editor-panel").hidden = tab === "theme";
  byId("editor-panel").setAttribute("aria-labelledby", `${tab}-tab`);
  byId("theme-panel").hidden = tab !== "theme";
  byId("settings-controls").hidden = tab !== "settings";
}
function showTab(next: typeof tab) {
  tab = next;
  updateTabs();
  if (next === "theme") refreshTheme();
  else {
    const path = next === "template" ? template : settingsPath(files, template);
    if (path) openSource(path);
  }
}
function refreshProject() {
  select("template").replaceChildren();
  for (const name of Object.keys(files)
    .filter((name) => /^templates\/.+\.(en|fr)\.typ$/.test(name))
    .sort()) {
    const filename = basename(name);
    const title = filename
      .replace(/\.(en|fr)\.typ$/, "")
      .replace(/_v\d+$/, "")
      .replaceAll("_", " ");
    const language = filename.endsWith(".fr.typ") ? "Français" : "English";
    const directory = name.split("/").slice(1, -1).join("/");
    const label = `${title.charAt(0).toUpperCase()}${title.slice(1)} · ${language}${directory ? ` · ${directory}` : ""}`;
    const option = new Option(label, name);
    option.title = name;
    select("template").add(option);
  }
  select("template").value = template;
  const hasSettings = Boolean(settingsPath(files, template));
  button("settings-tab").disabled = !hasSettings;
  if (tab === "settings" && !hasSettings) tab = "template";
  editor.clear();
  showTab(tab);
  refreshDownloads();
  refreshNavigation();
}
function refreshTheme() {
  const path = settingsPath(files, template);
  const bytes = path ? files[path] : undefined;
  select("health-unit-preset").disabled = !bytes;
  const fontValue = bytes ? settingValue(bytes, "body-font") : undefined;
  const family: string | undefined = fontValue?.startsWith('"') ? JSON.parse(fontValue) : undefined;
  const picker = select("body-font-picker");
  picker.replaceChildren();
  const families = fontFamilies;
  if (family && !families.includes(family)) families.unshift(family);
  for (const name of families) picker.add(new Option(name, name));
  if (family) picker.value = family;
  else {
    picker.add(new Option("Edit in Settings", ""));
    picker.value = "";
  }
  picker.disabled = !bytes || !family;
  picker.title = family ? "" : "Edit the typeface in Settings.";
  for (const name of ["heading", "link", "accent"]) {
    const input = byId<HTMLInputElement>(`${name}-color-picker`);
    const value = bytes ? settingValue(bytes, `${name}-color`) : undefined;
    const color =
      value === "black"
        ? "#000000"
        : value === "white"
          ? "#ffffff"
          : value?.match(/^rgb\("(#[\da-f]{6})"\)$/i)?.[1];
    input.disabled = !bytes || !color;
    input.title = color ? "" : "Edit this colour in Settings.";
    if (color) input.value = color;
  }
  const signatory = byId<HTMLInputElement>("signature-name-picker");
  const signatureName = bytes ? settingValue(bytes, "signature-name") : undefined;
  signatory.disabled = !signatureName?.startsWith('"');
  signatory.value = signatory.disabled ? "" : JSON.parse(signatureName as string);
  signatory.title = signatory.disabled ? "Edit the printed name in Settings." : "";
  for (const kind of ["logo", "signature", "extra"]) {
    const expression = kind === "extra" ? undefined : bytes ? settingValue(bytes, kind) : undefined;
    const relative = expression?.match(/^image\("([^"\r\n]+)"/)?.[1];
    const asset =
      kind === "extra"
        ? Object.keys(files).find((name) => /^templates\/assets\/studio-extra\./.test(name))
        : relative && path
          ? imagePath(path, relative)
          : undefined;
    if (imageURLs.has(kind)) URL.revokeObjectURL(imageURLs.get(kind) as string);
    const image = byId<HTMLImageElement>(`${kind}-preview`);
    image.hidden = !asset || !files[asset];
    const empty = byId(`${kind}-empty`);
    empty.hidden = !image.hidden;
    empty.textContent = kind !== "extra" && bytes && !relative ? "Edit in Settings" : "No image";
    if (asset && files[asset]) {
      const type = asset.endsWith(".svg")
        ? "image/svg+xml"
        : asset.endsWith(".jpg")
          ? "image/jpeg"
          : asset.endsWith(".webp")
            ? "image/webp"
            : "image/png";
      const url = URL.createObjectURL(new Blob([files[asset].slice().buffer], { type }));
      imageURLs.set(kind, url);
      image.src = url;
    }
    const upload = byId<HTMLInputElement>(`${kind}-upload`);
    upload.disabled = kind !== "extra" && (!bytes || !relative);
    upload.title = upload.disabled ? "Edit this image in Settings." : "";
    if (kind === "extra")
      byId("extra-path").textContent = asset
        ? `#image("${asset.replace(/^templates\//, "")}")`
        : "";
  }
}
function changeSettings(values: Record<string, string>) {
  const path = settingsPath(files, template);
  if (!path) throw new Error("This template has no companion Settings file.");
  const bytes = updateThemeSettings(files[path], values);
  editor.replaceFile(path, files[path], bytes);
  refreshTheme();
}
async function action(operation: () => void | Promise<void>) {
  try {
    actionError = undefined;
    await operation();
  } catch (error) {
    actionError = message(error);
  }
  findings();
}

for (const name of ["theme", "template", "settings"] as const)
  button(`${name}-tab`).onclick = () => showTab(name);
document.querySelector(".editor-tabs")?.addEventListener("keydown", (event) => {
  const keyboard = event as KeyboardEvent;
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(keyboard.key)) return;
  keyboard.preventDefault();
  const available = ["theme", "template", "settings"].filter(
    (name) => !button(`${name}-tab`).disabled,
  ) as (typeof tab)[];
  const direction = keyboard.key === "ArrowLeft" ? -1 : 1;
  const index =
    keyboard.key === "Home"
      ? 0
      : keyboard.key === "End"
        ? available.length - 1
        : (available.indexOf(tab) + direction + available.length) % available.length;
  showTab(available[index]);
  button(`${tab}-tab`).focus();
});
for (const [id, direction] of [
  ["previous", -1],
  ["next", 1],
] as const)
  button(id).onclick = () => {
    const available = compatibleExamples();
    example = available[available.findIndex((item) => item.id === example?.id) + direction];
    persist();
    compile(true);
  };
select("template").onchange = () => {
  template = select("template").value;
  const available = compatibleExamples();
  example = available.find((item) => item.id === example?.id) ?? available[0];
  themeUndo = undefined;
  button("health-unit-undo").hidden = true;
  refreshProject();
  persist();
  compile(true);
};
select("body-font-picker").onchange = () =>
  void action(() =>
    changeSettings({ "body-font": JSON.stringify(select("body-font-picker").value) }),
  );
for (const name of ["heading", "link", "accent"])
  byId<HTMLInputElement>(`${name}-color-picker`).onchange = () =>
    void action(() =>
      changeSettings({
        [`${name}-color`]: `rgb("${byId<HTMLInputElement>(`${name}-color-picker`).value}")`,
      }),
    );
byId<HTMLInputElement>("signature-name-picker").onchange = () =>
  void action(() =>
    changeSettings({
      "signature-name": JSON.stringify(byId<HTMLInputElement>("signature-name-picker").value),
    }),
  );
for (const unit of healthUnits) select("health-unit-preset").add(new Option(unit.name, unit.id));
select("health-unit-preset").onchange = () =>
  void action(async () => {
    const unit = healthUnits.find((unit) => unit.id === select("health-unit-preset").value);
    if (!unit) return;
    const path = settingsPath(files, template);
    if (!path) throw new Error("This template has no companion Settings file.");
    const selectedTemplate = template;
    const previous = files;
    let settings = themedSettings(files[path], unit);
    for (const kind of ["logo", "signature"]) {
      const expression = settingValue(settings, kind) as string;
      settings = updateThemeSettings(settings, {
        [kind]: expression.replace(
          /^image\("[^"\r\n]+"/,
          `image(${JSON.stringify(relativeImage(path, `templates/assets/${kind}.png`))}`,
        ),
      });
    }
    const [logo, signature] = await Promise.all(
      [unit.logo, unit.signature].map(async (url) => {
        const response = await fetch(url);
        if (!response.ok) throw new Error("Could not load the selected theme image.");
        return new Uint8Array(await response.arrayBuffer());
      }),
    );
    if (files !== previous || template !== selectedTemplate)
      throw new Error("The project changed while the theme loaded. Select the theme again.");
    const next = {
      ...files,
      [path]: settings,
      "templates/assets/logo.png": logo,
      "templates/assets/signature.png": signature,
    };
    validateFiles(next);
    files = next;
    themeUndo = previous;
    button("health-unit-undo").hidden = false;
    editor.clear();
    refreshTheme();
    persist();
    compile();
  });
button("health-unit-undo").onclick = () => {
  if (!themeUndo) return;
  files = themeUndo;
  themeUndo = undefined;
  button("health-unit-undo").hidden = true;
  editor.clear();
  refreshTheme();
  persist();
  compile();
};
for (const kind of ["logo", "signature", "extra"])
  byId<HTMLInputElement>(`${kind}-upload`).onchange = () =>
    void action(async () => {
      const input = byId<HTMLInputElement>(`${kind}-upload`);
      const file = input.files?.[0];
      if (!file) return;
      const previous = files;
      const path = settingsPath(files, template);
      const bytes = await imageBytes(file);
      if (previous !== files)
        throw new Error("The project changed while the image loaded. Choose it again.");
      const extension = {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/webp": "webp",
        "image/svg+xml": "svg",
      }[file.type];
      const asset = `templates/assets/studio-${kind}.${extension}`;
      const next = { ...files, [asset]: bytes };
      if (kind === "extra") {
        for (const name of Object.keys(next)) {
          if (name !== asset && /^templates\/assets\/studio-extra\./.test(name)) delete next[name];
        }
      }
      if (kind !== "extra") {
        if (!path) throw new Error("This template has no companion Settings file.");
        const expression = settingValue(files[path], kind);
        if (!expression || !/^image\("[^"\r\n]+"/.test(expression))
          throw new Error(`Edit ${kind} in Settings to use your image.`);
        next[path] = updateThemeSettings(files[path], {
          [kind]: expression.replace(
            /^image\("[^"\r\n]+"/,
            `image(${JSON.stringify(relativeImage(path, asset))}`,
          ),
        });
      }
      validateFiles(next);
      files = next;
      editor.clear();
      themeUndo = undefined;
      button("health-unit-undo").hidden = true;
      refreshTheme();
      persist();
      compile();
      input.value = "";
    });
byId<HTMLInputElement>("guide").onchange = () =>
  viewer.setGuide(byId<HTMLInputElement>("guide").checked);
button("zoom-in").onclick = () => void action(() => viewer.zoomBy(1.2));
button("zoom-out").onclick = () => void action(() => viewer.zoomBy(1 / 1.2));
button("export").onclick = () =>
  void action(async () => {
    if (exporting) return;
    const snapshot = {
      files,
      template,
      example,
      revision,
      context: compiler.context,
      includeFonts: byId<HTMLInputElement>("include-fonts").checked,
    };
    exporting = true;
    refreshDownloads();
    try {
      const bytes = await archiveJob({
        action: "export",
        files: await withProjectFonts(snapshot.files, snapshot.includeFonts),
        template: snapshot.template,
        build: bundle.build,
      });
      if (
        files !== snapshot.files ||
        template !== snapshot.template ||
        example !== snapshot.example ||
        revision !== snapshot.revision ||
        compiler.context !== snapshot.context
      )
        throw new Error("The project changed during download. Download it again.");
      download("immuknow-project.zip", bytes, "application/zip");
    } finally {
      exporting = false;
      refreshDownloads();
    }
  });
button("import").onclick = () => byId<HTMLInputElement>("archive").click();
byId<HTMLInputElement>("archive").onchange = () =>
  void action(async () => {
    const input = byId<HTMLInputElement>("archive");
    const archive = input.files?.[0];
    if (!archive) return;
    if (archive.size > MAX_PROJECT) throw new Error("Compressed project exceeds 32 MB.");
    const previous = files;
    const project = await archiveJob({
      action: "import",
      bytes: new Uint8Array(await archive.arrayBuffer()),
      build: bundle.build,
    });
    if (previous !== files)
      throw new Error("The project changed during import. Import the archive again.");
    originals = project.files;
    files = { ...originals };
    template = project.template;
    canSave = Boolean(draftStore);
    themeUndo = undefined;
    button("health-unit-undo").hidden = true;
    select("health-unit-preset").value = "";
    const available = compatibleExamples();
    example = available.find((item) => item.id === example?.id) ?? available[0];
    refreshProject();
    persist();
    compile(true);
    input.value = "";
  });
button("reset").onclick = () =>
  void action(() => {
    if (originals[editor.file]) {
      newContext();
      editor.replaceFile(editor.file, files[editor.file], originals[editor.file]);
    }
    refreshTheme();
  });
button("clear").onclick = () =>
  void action(() => {
    if (!draftStore)
      throw new Error("Draft storage is unavailable. Download your project to keep your work.");
    canSave = true;
    draftStore.clear();
  });
button("restart").onclick = () => {
  compilerError = undefined;
  compiler.restart();
  compile(true);
};

const divider = byId("divider");
function resizeSplit(value: number) {
  const percent = Math.max(25, Math.min(75, value));
  byId("workspace").style.setProperty("--split", `${percent}%`);
  divider.setAttribute("aria-valuenow", String(Math.round(percent)));
}
divider.onpointerdown = (event) => {
  divider.setPointerCapture(event.pointerId);
  divider.onpointermove = (move) => {
    const bounds = byId("workspace").getBoundingClientRect();
    resizeSplit(((move.clientX - bounds.left) / bounds.width) * 100);
  };
};
divider.onpointerup = divider.onpointercancel = () => {
  divider.onpointermove = null;
};
divider.onkeydown = (event) => {
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
  event.preventDefault();
  resizeSplit(Number(divider.getAttribute("aria-valuenow")) + (event.key === "ArrowLeft" ? -3 : 3));
};
initializeHelp((next) => {
  const original = tab;
  showTab(next ?? "settings");
  return () => showTab(original);
});

async function start() {
  byId("workspace").inert = true;
  const projectMenu = document.querySelector<HTMLElement>(".project-actions");
  if (projectMenu) projectMenu.inert = true;
  try {
    if (!(await claimEditingTab())) {
      storageError("Studio is open in another tab. Close that tab, then reload this one.");
      return;
    }
  } catch (error) {
    storageError(error);
    return;
  }
  const response = await fetch(`${import.meta.env.BASE_URL}generated/project.json`);
  if (!response.ok) throw new Error("Could not load the starter project. Reload Studio to retry.");
  bundle = await response.json();
  originals = await decodeFiles(bundle);
  files = { ...originals };
  template = "templates/overdue_diseases_v1.en.typ";
  example = bundle.examples.find((item) => item.payloads[basename(template)]);
  try {
    draftStore = await DraftStore.open(bundle.build, saveState);
    const saved = await draftStore.load();
    canSave = true;
    if (saved) {
      files = saved.files;
      originals = saved.baseline;
      draftRevision = saved.revision;
      template = saved.template;
      const available = compatibleExamples();
      example = available.find((item) => item.id === saved.example) ?? available[0];
      saveState("saved");
    }
  } catch (error) {
    storageError(error);
  }
  compiler = new Compiler(
    (status: string, blocking?: boolean) => {
      if (blocking) {
        compilerError = status;
        pending = false;
        previewStatus();
        findings();
      }
    },
    (result) => void compiled(result),
  );
  for (const id of [
    "template-tab",
    "theme-tab",
    "template",
    "import",
    "clear",
    "restart",
    "zoom-in",
    "zoom-out",
  ])
    buttonOrSelect(id).disabled = false;
  refreshProject();
  byId("workspace").inert = false;
  if (projectMenu) projectMenu.inert = false;
  compile(true);
}
function buttonOrSelect(id: string) {
  return byId<HTMLButtonElement | HTMLSelectElement>(id);
}
void start().catch((error) => {
  actionError = message(error);
  pending = false;
  previewStatus();
  findings();
});
