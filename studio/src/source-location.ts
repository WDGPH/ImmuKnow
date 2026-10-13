import { decoder } from "./project";
import type { Files } from "./types";

type Location = { path: string; from: number; to: number };
function normalized(source: string) {
  let text = "";
  const offsets: number[] = [];
  for (let i = 0; i < source.length; i++) {
    const char = source[i].normalize("NFKC").toLowerCase();
    for (const c of char) {
      if (!/[\p{L}\p{N}]/u.test(c)) continue;
      text += c;
      offsets.push(i);
    }
  }
  return { text, offsets };
}

export function sourceLocation(files: Files, template: string, text: string): Location | undefined {
  const needle = normalized(text).text;
  if (needle.length < 5) return;
  const paths = [
    template,
    ...Object.keys(files).filter(
      (p) =>
        p !== template &&
        p.startsWith("templates/") &&
        !p.startsWith("templates/lib/") &&
        p.endsWith(".typ"),
    ),
  ];
  let location: Location | undefined;
  for (const path of paths) {
    const bytes = files[path];
    if (!bytes) continue;
    const source = decoder.decode(bytes);
    // Preserve offsets while excluding comments from matching.
    const visible = source.replace(/"(?:\\.|[^"\\])*"|\/\*[\s\S]*?\*\/|\/\/[^\n]*/g, (part) =>
      part.startsWith('"') ? part : " ".repeat(part.length),
    );
    const haystack = normalized(visible);
    const at = haystack.text.indexOf(needle);
    if (at < 0) continue;
    if (location || haystack.text.indexOf(needle, at + 1) >= 0) return;
    location = { path, from: haystack.offsets[at], to: haystack.offsets[at + needle.length - 1] + 1 };
  }
  return location;
}
