import type { BuildInfo, Bundle, Files } from "./types";

// Project archives retain authored files and may include optional fonts.
export const MAX_FILE = 12 * 1024 * 1024;
export const MAX_PROJECT = 32 * 1024 * 1024;
export const MAX_FILES = 400;
export const decoder = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true });
export const encoder = new TextEncoder();
export const textFile = (name: string) => /\.(typ|json|yaml|yml|toml|md|txt)$/i.test(name);
export const editableFile = (name: string) =>
  (name.startsWith("templates/") || name.startsWith("config/")) &&
  !name.startsWith("templates/lib/immuknow/") &&
  !name.startsWith("templates/fonts/");

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
        (part) =>
          !part ||
          part === "." ||
          part === ".." ||
          ["__proto__", "constructor", "prototype"].includes(part),
      )
  )
    throw new Error(`Unsafe project path: ${name}`);
  return name;
}

export function validateFiles(files: Files): void {
  let total = 0;
  const paths = new Set<string>();
  if (Object.keys(files).length > MAX_FILES)
    throw new Error(`Projects are limited to ${MAX_FILES} files.`);
  for (const [name, bytes] of Object.entries(files)) {
    safePath(name);
    const normalized = name.normalize("NFC").toLowerCase();
    if (paths.has(normalized)) throw new Error(`Duplicate project path: ${name}`);
    paths.add(normalized);
    if (!(bytes instanceof Uint8Array) || bytes.length > MAX_FILE)
      throw new Error(`${name} exceeds the 12 MB file limit or is not a byte array.`);
    total += bytes.length;
  }
  for (const name of paths) {
    const parts = name.split("/");
    for (let end = 1; end < parts.length; end++)
      if (paths.has(parts.slice(0, end).join("/")))
        throw new Error(`A project file also names a directory: ${name}`);
  }
  if (total > MAX_PROJECT) throw new Error("Project exceeds the 32 MB expanded size limit.");
}

export async function sha256(bytes: Uint8Array): Promise<string> {
  return Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes.slice().buffer)))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

export async function verifyHashes(files: Files, hashes: Record<string, string>): Promise<void> {
  if (
    !hashes ||
    typeof hashes !== "object" ||
    Array.isArray(hashes) ||
    Object.keys(hashes).length !== Object.keys(files).length
  )
    throw new Error("Project hashes do not match its files.");
  for (const [name, bytes] of Object.entries(files)) {
    if (!Object.hasOwn(hashes, name) || hashes[name] !== (await sha256(bytes)))
      throw new Error(`Project file failed its integrity check: ${name}`);
  }
}

export async function decodeFiles(bundle: Bundle): Promise<Files> {
  if (bundle.schemaVersion !== 1 || bundle.synthetic !== true)
    throw new Error("Unsupported starter project format.");
  const files = Object.fromEntries(
    Object.entries(bundle.files).map(([name, value]) => [
      safePath(name),
      Uint8Array.from(atob(value), (character) => character.charCodeAt(0)),
    ]),
  );
  validateFiles(files);
  await verifyHashes(files, bundle.hashes);
  return files;
}

export function runtimeFiles(files: Files): Files {
  validateFiles(files);
  return Object.fromEntries(Object.entries(files).map(([name, bytes]) => [`/${name}`, bytes]));
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

export function settingsPath(files: Files, template: string): string | undefined {
  const source = files[template] ? decoder.decode(files[template]) : "";
  const relative = source.match(/^\ufeff?\/\/ @immuknow-settings: (.+)\r?$/m)?.[1].trim();
  if (!relative) return undefined;
  if (relative.startsWith("/")) throw new Error("The Settings marker must use a relative path.");
  const parts = template.split("/").slice(0, -1);
  for (const part of relative.split("/")) {
    if (part === ".") continue;
    if (part === "..") {
      if (!parts.length) throw new Error("The Settings marker leaves the project.");
      parts.pop();
    } else parts.push(part);
  }
  const path = safePath(parts.join("/"));
  return files[path] && editableFile(path) ? path : undefined;
}

export function verifyProjectBuild(value: BuildInfo | undefined, build: BuildInfo): void {
  if (
    !/^[0-9a-f]{64}$/.test(build.compiler_build_sha256) ||
    !/^[0-9a-f]{64}$/.test(build.shared_resources?.sha256) ||
    value?.rendering_schema_version !== build.rendering_schema_version ||
    value?.native_typst_version !== build.native_typst_version ||
    value?.compiler_build_sha256 !== build.compiler_build_sha256 ||
    value?.shared_resources?.sha256 !== build.shared_resources.sha256
  )
    throw new Error("This project requires a different ImmuKnow format or compiler build.");
}

export function validateTemplate(files: Files, template: string): string {
  const path = safePath(template);
  if (
    !/^templates\/(?:[^/]+\/)*[A-Za-z0-9][A-Za-z0-9_-]*\.(en|fr)\.typ$/.test(path) ||
    !files[path]
  )
    throw new Error("The project's named English/French entry point is missing.");
  return path;
}
