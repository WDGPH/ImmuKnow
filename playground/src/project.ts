import type { Bundle, Files } from "./types";

export const MAX_FILE = 8 * 1024 * 1024;
export const MAX_PROJECT = 24 * 1024 * 1024;
export const MAX_FILES = 400;
export const decoder = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true });
export const encoder = new TextEncoder();
export const textFile = (name: string) => /\.(typ|json|yaml|yml|toml|md|txt)$/i.test(name);
export const editableFile = (name: string) =>
  name.startsWith("templates/") || name.startsWith("config/");
export function safePath(name: string): string {
  if (
    typeof name !== "string" ||
    !name ||
    name.length > 240 ||
    name.startsWith("/") ||
    /[\\:]/.test(name) ||
    Array.from(name).some((c) => c.charCodeAt(0) < 32 || c.charCodeAt(0) === 127) ||
    name
      .split("/")
      .some(
        (p) =>
          !p || p === "." || p === ".." || ["__proto__", "constructor", "prototype"].includes(p),
      )
  )
    throw new Error(`Unsafe project path: ${name}`);
  return name;
}
export function validateFiles(files: Files): void {
  let total = 0;
  if (Object.keys(files).length > MAX_FILES)
    throw new Error(`Projects are limited to ${MAX_FILES} files.`);
  for (const [name, bytes] of Object.entries(files)) {
    safePath(name);
    if (bytes.length > MAX_FILE) throw new Error(`${name} exceeds the 8 MB file limit.`);
    total += bytes.length;
  }
  if (total > MAX_PROJECT) throw new Error("Project exceeds the 24 MB expanded size limit.");
}
export function decodeFiles(bundle: Bundle): Files {
  const files = Object.fromEntries(
    Object.entries(bundle.files).map(([name, value]) => [
      safePath(name),
      Uint8Array.from(atob(value), (c) => c.charCodeAt(0)),
    ]),
  );
  validateFiles(files);
  return files;
}
export function runtimeFiles(files: Files, defaults: Files): Files {
  // Production stages PHU overrides at /translations. There is one editable
  // override per domain; the runtime aliases are never independent drafts.
  const result: Files = {};
  for (const [name, data] of Object.entries(files))
    if (!name.startsWith("translations/")) result[`/${name}`] = data;
  for (const lang of ["en", "fr"])
    for (const domain of ["chart", "overdue"]) {
      const name = `${lang}_diseases_${domain}.json`;
      const value =
        files[`config/translations/${name}`] ?? defaults[`templates/lib/immuknow/locales/${name}`];
      if (value) result[`/translations/${name}`] = value;
    }
  return result;
}
export function base64(bytes: Uint8Array): string {
  let text = "";
  for (let start = 0; start < bytes.length; start += 8192)
    text += String.fromCharCode(...bytes.subarray(start, start + 8192));
  return btoa(text);
}
export function download(name: string, bytes: Uint8Array, type: string): void {
  const url = URL.createObjectURL(new Blob([bytes.slice().buffer], { type }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
