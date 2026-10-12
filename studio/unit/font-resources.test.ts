import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
import { FontInputs, fontManifest } from "../src/font-resources";
import { encoder, sha256 } from "../src/project";
import type { Files } from "../src/types";

const bundled: Files = Object.fromEntries(Object.keys(fontManifest).map((name) => [
  `/templates/fonts/${name}`,
  new Uint8Array(readFileSync(new URL(`../assets/fonts/${name}`, import.meta.url))),
]));

test("supplied fonts match their fixed hashes and accept unchanged copies or no files", async () => {
  const fonts = new FontInputs(bundled);
  for (const [name, digest] of Object.entries(fontManifest))
    expect(await sha256(bundled[`/templates/fonts/${name}`])).toBe(digest);
  fonts.validate({});
  fonts.validate(structuredClone(bundled));
  fonts.validate({ ...bundled, "/templates/fonts/manifest.json": encoder.encode(JSON.stringify(fontManifest, null, 2)) });
});

test("changed, partial and extra font files are refused even with matching project hashes", async () => {
  const fonts = new FontInputs(bundled);
  const changed = encoder.encode("changed font");
  const copies = [
    { ...bundled, "/templates/fonts/FreeSans.ttf": changed },
    { ...bundled, "/templates/assets/extra.OTF": bundled["/templates/fonts/FreeSans.ttf"] },
    { ...bundled, "/templates/fonts/extra.bin": bundled["/templates/fonts/FreeSans.ttf"] },
    { "/templates/fonts/FreeSans.ttf": bundled["/templates/fonts/FreeSans.ttf"] },
    { ...bundled, "/templates/fonts/manifest.json": encoder.encode(JSON.stringify({ ...fontManifest, "FreeSans.ttf": await sha256(changed) })) },
    { ...bundled, "/templates/fonts/families.json": encoder.encode('{"Another family": ["FreeSans.ttf"]}') },
  ];
  for (const files of copies) expect(() => fonts.validate(files)).toThrow(/supplied/);
  fonts.validate(bundled);
});
