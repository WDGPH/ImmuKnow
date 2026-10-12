import { safePath, sha256 } from "./project";
import type { BuildInfo, Files } from "./types";

const root = "templates/lib/immuknow/";

// Use the running app's file list, never hashes supplied by an imported project.
export async function verifyComponents(
  files: Files,
  build: BuildInfo,
  prefix: "" | "/" = "",
): Promise<void> {
  const expected = build.shared_resources.files.filter((item) => item.path.startsWith(root));
  if (!expected.some((item) => item.path === `${root}lib.typ`))
    throw new Error("The app's ImmuKnow library file list is missing.");
  const actual = Object.keys(files).filter((path) => path.startsWith(prefix + root));
  if (actual.length !== expected.length)
    throw new Error("Use the complete supplied lib/immuknow directory.");
  for (const item of expected) {
    const bytes = files[prefix + safePath(item.path)];
    if (!bytes || (await sha256(bytes)) !== item.sha256)
      throw new Error(`ImmuKnow library file differs from the supplied version: ${item.path}`);
  }
}
