import { unzipSync, zipSync } from "fflate";
import {
  decoder,
  encoder,
  MAX_FILE,
  MAX_FILES,
  MAX_PROJECT,
  safePath,
  validateFiles,
} from "./project";
import type { Files } from "./types";

const manifestName = "immuknow-project.json";
const table = Uint32Array.from({ length: 256 }, (_, n) => {
  for (let i = 0; i < 8; i++) n = n & 1 ? 0xedb88320 ^ (n >>> 1) : n >>> 1;
  return n >>> 0;
});
function crc(bytes: Uint8Array) {
  let value = 0xffffffff;
  for (const byte of bytes) value = table[(value ^ byte) & 255] ^ (value >>> 8);
  return (value ^ 0xffffffff) >>> 0;
}

export function importProject(bytes: Uint8Array): { files: Files; template: string } {
  if (bytes.length > MAX_PROJECT || bytes.length < 22)
    throw new Error("Invalid archive or compressed project exceeds 24 MB.");
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  let end = bytes.length - 22;
  while (end >= Math.max(0, bytes.length - 65557) && view.getUint32(end, true) !== 0x06054b50)
    end--;
  if (
    end < 0 ||
    view.getUint32(end, true) !== 0x06054b50 ||
    end + 22 + view.getUint16(end + 20, true) !== bytes.length
  )
    throw new Error("Invalid ZIP directory.");
  const count = view.getUint16(end + 10, true),
    start = view.getUint32(end + 16, true);
  if (
    view.getUint16(end + 4, true) ||
    view.getUint16(end + 6, true) ||
    view.getUint16(end + 8, true) !== count ||
    count > MAX_FILES ||
    start + view.getUint32(end + 12, true) !== end
  )
    throw new Error("Multipart, ZIP64, or oversized archives are not supported.");
  const entries = new Map<string, { length: number; crc: number }>();
  const names = new Set<string>();
  const ranges: [number, number][] = [];
  let position = start,
    expanded = 0;
  for (let i = 0; i < count; i++) {
    if (position + 46 > end || view.getUint32(position, true) !== 0x02014b50)
      throw new Error("Invalid ZIP entry.");
    const flags = view.getUint16(position + 8, true),
      method = view.getUint16(position + 10, true);
    const compressed = view.getUint32(position + 20, true),
      length = view.getUint32(position + 24, true);
    const nameLength = view.getUint16(position + 28, true),
      extra = view.getUint16(position + 30, true),
      comment = view.getUint16(position + 32, true);
    const local = view.getUint32(position + 42, true),
      mode = view.getUint32(position + 38, true) >>> 16;
    if (
      flags & ~0x808 ||
      ![0, 8].includes(method) ||
      view.getUint16(position + 34, true) ||
      ![0, 0x8000, 0x4000].includes(mode & 0xf000)
    )
      throw new Error("Encrypted, linked, or unsupported ZIP entries are not allowed.");
    if (position + 46 + nameLength + extra + comment > end) throw new Error("Truncated ZIP entry.");
    const name = decoder.decode(bytes.subarray(position + 46, position + 46 + nameLength));
    const directory = name.endsWith("/");
    safePath(directory ? name.slice(0, -1) : name);
    const normalized = name.normalize("NFC").toLowerCase();
    if (names.has(normalized)) throw new Error("Duplicate project paths are not allowed.");
    names.add(normalized);
    expanded += length;
    if (length > MAX_FILE || expanded > MAX_PROJECT)
      throw new Error("Archive expanded size exceeds the project limits.");
    if (
      local + 30 > start ||
      view.getUint32(local, true) !== 0x04034b50 ||
      view.getUint16(local + 6, true) !== flags ||
      view.getUint16(local + 8, true) !== method
    )
      throw new Error("Inconsistent ZIP local header.");
    const localNameLength = view.getUint16(local + 26, true),
      dataStart = local + 30 + localNameLength + view.getUint16(local + 28, true);
    if (
      dataStart + compressed > start ||
      decoder.decode(bytes.subarray(local + 30, local + 30 + localNameLength)) !== name
    )
      throw new Error("Invalid ZIP file extent or path.");
    ranges.push([local, dataStart + compressed]);
    if (!directory) entries.set(name, { length, crc: view.getUint32(position + 16, true) });
    position += 46 + nameLength + extra + comment;
  }
  if (position !== end) throw new Error("Invalid ZIP directory size.");
  ranges.sort((a, b) => a[0] - b[0]);
  if (ranges.some((range, i) => i > 0 && range[0] < ranges[i - 1][1]))
    throw new Error("Overlapping ZIP entries are not allowed.");
  const decoded = unzipSync(bytes, { filter: (file) => entries.has(file.name) });
  const files: Files = {};
  for (const [name, entry] of entries) {
    const value = decoded[name];
    if (!value || value.length !== entry.length || crc(value) !== entry.crc)
      throw new Error(`Corrupt ZIP entry: ${name}`);
    files[name] = value;
  }
  validateFiles(files);
  if (!files[manifestName])
    throw new Error("Import a complete ImmuKnow project ZIP with immuknow-project.json.");
  const manifest = JSON.parse(decoder.decode(files[manifestName]));
  if (
    manifest.schemaVersion !== 1 ||
    manifest.compilerVersion !== "0.15.1" ||
    manifest.packageVersion !== "0.1.0"
  )
    throw new Error("Unsupported project, package, or compiler version.");
  const template = safePath(manifest.template);
  if (!template.startsWith("templates/") || !template.endsWith(".typ") || !files[template])
    throw new Error("The project entry point is missing.");
  for (const name of Object.keys(files))
    if (name.startsWith("data/") || name.startsWith("translations/"))
      throw new Error("Runtime data and translation aliases are not editable project inputs.");
  delete files[manifestName];
  return { files, template };
}
export async function exportProject(files: Files, template: string): Promise<Uint8Array> {
  validateFiles(files);
  safePath(template);
  const project: Files = {};
  for (const [name, value] of Object.entries(files))
    if (!name.startsWith("translations/") && !name.startsWith("data/")) project[name] = value;
  const hashes = Object.fromEntries(
    await Promise.all(
      Object.entries(project).map(async ([name, value]) => [
        name,
        Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", value.slice().buffer)))
          .map((b) => b.toString(16).padStart(2, "0"))
          .join(""),
      ]),
    ),
  );
  project[manifestName] = encoder.encode(
    `${JSON.stringify({ schemaVersion: 1, compilerVersion: "0.15.1", packageVersion: "0.1.0", template, hashes }, null, 2)}\n`,
  );
  return zipSync(project, { level: 6 });
}
