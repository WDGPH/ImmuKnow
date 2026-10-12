import { FontInputs, fontManifest } from "./font-resources";
import { safePath, sha256, validateFiles } from "./project";
import type { Files } from "./types";

const fontRoot = "templates/fonts/";

// Preview fonts are optional in the downloaded project.
export async function withProjectFonts(files: Files, include: boolean): Promise<Files> {
  validateFiles(files);
  const result = Object.fromEntries(
    Object.entries(files).filter(([path]) => !path.startsWith(fontRoot)),
  );
  if (!include) return result;
  const base = `${import.meta.env.BASE_URL}generated/fonts/`;
  async function resource(name: string): Promise<Uint8Array> {
    safePath(name);
    const response = await fetch(base + name);
    if (!response.ok) throw new Error(`Could not include project font resource: ${name}`);
    return new Uint8Array(await response.arrayBuffer());
  }
  const bundled: Files = Object.fromEntries(
    await Promise.all(
      Object.entries(fontManifest).map(async ([name, hash]) => {
        const bytes = await resource(name);
        if ((await sha256(bytes)) !== hash) throw new Error(`Font integrity check failed: ${name}`);
        return [`/${fontRoot}${name}`, bytes];
      }),
    ),
  );
  new FontInputs(bundled).validate(
    Object.fromEntries(Object.entries(files).map(([path, bytes]) => [`/${path}`, bytes])),
  );
  for (const [path, bytes] of Object.entries(bundled)) result[path.slice(1)] ??= bytes;
  for (const name of ["manifest.json", "families.json", "LICENSE", "UPSTREAM.json"])
    result[`${fontRoot}${name}`] ??= await resource(name);
  validateFiles(result);
  return result;
}
