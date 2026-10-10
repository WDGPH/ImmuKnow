import { decoder, encoder } from "./project";
import type { Files } from "./types";

export function typstLiteral(value: unknown): string {
  if (value === null) return "none";
  if (typeof value === "string")
    // biome-ignore lint/suspicious/noControlCharactersInRegex: Escape control characters in Typst string literals.
    return `"${value.replace(/[\\"\x00-\x1f]/g, (c) => (c === '"' || c === "\\" ? `\\${c}` : `\\u{${c.charCodeAt(0).toString(16)}}`))}"`;
  if (typeof value === "boolean") return String(value);
  if (typeof value === "number" && Number.isFinite(value)) return String(value);
  if (Array.isArray(value))
    return `(${value.map(typstLiteral).join(",")}${value.length ? "," : ""})`;
  if (typeof value === "object" && value) {
    const entries = Object.entries(value);
    return entries.length
      ? `(${entries.map(([k, v]) => `${typstLiteral(k)}: ${typstLiteral(v)}`).join(",")},)`
      : "(:)";
  }
  throw new Error("Settings contain a value that cannot be exported to Typst.");
}

export function inlineTemplate(files: Files, path: string): Uint8Array {
  let source = decoder.decode(files[path]);
  const markers = [...source.matchAll(/^\/\/ @immuknow-settings: (.+)$/gm)];
  if (!markers.length) return files[path]; // Preserve custom and older entry points.
  if (markers.length !== 1) throw new Error("Expected one template settings marker.");
  const relative = markers[0][1];
  if (!/^settings\/[a-zA-Z0-9_.-]+\.typ$/.test(relative)) throw new Error("Invalid settings path.");
  const companion = files[`${path.slice(0, path.lastIndexOf("/") + 1)}${relative}`];
  const settings = companion ? decoder.decode(companion) : "";
  const names = [...settings.matchAll(/^#let ([\w-]+) =/gm)].map((match) => match[1]);
  const block = `${markers[0][0]}\n#import "${relative}": ${names.join(", ")}`;
  if (!source.includes(`${block}\n`) || !companion || !names.length)
    throw new Error(
      "Cannot inline template settings. Export the complete project to preserve your edits.",
    );
  source = source.replace(block, () => decoder.decode(companion));
  const layoutCall = 'ik.project-layout(json("layout-settings.json")';
  if (source.includes(layoutCall)) {
    const layout = files[`${path.slice(0, path.lastIndexOf("/") + 1)}layout-settings.json`];
    if (!layout) throw new Error("Layout settings are missing.");
    source = source.replace(
      layoutCall,
      () => `ik.project-layout(${typstLiteral(JSON.parse(decoder.decode(layout)))}`,
    );
  }
  return encoder.encode(source);
}
