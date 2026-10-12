import manifest from "../assets/fonts/manifest.json";
import families from "../assets/fonts/families.json";
import { sameBytes } from "./compiler-inputs";
import { decoder } from "./project";
import type { Files } from "./types";

export const fontManifest: Record<string, string> = manifest;
export const fontFamilies = Object.keys(families);

// The resolver always uses the shipped bytes. Imported copies must match them;
// project-provided hashes cannot authorize a different or partial font set.
export class FontInputs {
  constructor(private bundled: Files) {}

  validate(files: Files): void {
    const allowed = new Set([
      ...Object.keys(this.bundled),
      ...["manifest.json", "families.json", "LICENSE", "UPSTREAM.json"].map((name) => `/templates/fonts/${name}`),
    ]);
    if (Object.keys(files).some((path) => path.startsWith("/templates/fonts/") && !allowed.has(path)))
      throw new Error("Use only the supplied files in the fonts directory.");
    const fonts = Object.fromEntries(
      Object.entries(files).filter(([path]) => /\.(ttf|otf|ttc|otc|woff2?)$/i.test(path)),
    );
    const names = Object.keys(fonts);
    if (names.length && (
      names.length !== Object.keys(this.bundled).length ||
      names.some((path) => !this.bundled[path])
    ))
      throw new Error("Use the complete supplied FreeSans and FreeSerif font files.");
    for (const [path, bytes] of Object.entries(fonts))
      if (!sameBytes(this.bundled[path], bytes))
        throw new Error(`Font file differs from the supplied version: ${path}`);
    for (const [name, expected] of Object.entries({ "manifest.json": manifest, "families.json": families })) {
      const bytes = files[`/templates/fonts/${name}`];
      if (!bytes) continue;
      const declared: unknown = JSON.parse(decoder.decode(bytes));
      if (
        !declared || typeof declared !== "object" || Array.isArray(declared) ||
        Object.keys(declared).length !== Object.keys(expected).length ||
        Object.entries(expected).some(([key, value]) =>
          JSON.stringify((declared as Record<string, unknown>)[key]) !== JSON.stringify(value))
      )
        throw new Error(`Use the supplied fonts/${name}; its contents have changed.`);
    }
  }
}
