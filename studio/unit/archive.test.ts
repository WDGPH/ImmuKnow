import { unzipSync, zipSync } from "fflate";
import { describe, expect, it } from "vitest";
import { exportProject, importProject } from "../src/archive-core";
import { encoder, MAX_FILE, sha256 } from "../src/project";
import type { BuildInfo, Files } from "../src/types";
import pins from "../compiler-pins.json";

const build: BuildInfo = {
  ...pins,
  application_version: "1.1.0",
  rendering_schema_version: 1,
  native_typst_version: "0.15.1",
  compiler_build_sha256: "c".repeat(64),
  shared_resources: {
    sha256: "d".repeat(64),
    files: [
      {
        path: "templates/lib/immuknow/lib.typ",
        sha256: await sha256(encoder.encode("// Supplied components\n")),
      },
    ],
  },
  source_revision: null,
  source_modified: null,
};
const template = "templates/edited.en.typ";
const files: Files = {
  "templates/lib/immuknow/lib.typ": encoder.encode("// Supplied components\n"),
  [template]: encoder.encode(
    '\ufeff// @immuknow-settings: settings.typ\r\n#import "settings.typ": *\r\nAuthored words\r\n',
  ),
  "templates/settings.typ": encoder.encode(
    "#let logo = none\n#let show-history = false\n#let width = 12.345678mm\n",
  ),
  "templates/assets/authored.png": new Uint8Array([0, 1, 255, 2, 3]),
};

describe("current project archives", () => {
  it("round-trips authored bytes and checks declared integrity", async () => {
    const archive = await exportProject(files, template, build);
    expect(await importProject(archive, build)).toEqual({ files, template });
    const changed = unzipSync(archive);
    changed[template] = encoder.encode("Changed without refreshing the manifest");
    await expect(importProject(zipSync(changed), build)).rejects.toThrow("integrity check");
    delete changed[template];
    await expect(importProject(zipSync(changed), build)).rejects.toThrow("entry point");
  });

  it("rejects unsafe, duplicate, and oversized entries before using their content", async () => {
    for (const name of ["../escape.typ", "/absolute.typ", "templates/../escape.typ"]) {
      await expect(
        importProject(zipSync({ [name]: encoder.encode("text") }), build),
      ).rejects.toThrow("Unsafe project path");
    }
    await expect(
      importProject(
        zipSync({
          "templates/a.en.typ": encoder.encode("one"),
          "templates/A.en.typ": encoder.encode("two"),
        }),
        build,
      ),
    ).rejects.toThrow("Duplicate project paths");
    await expect(
      importProject(zipSync({ "large.bin": new Uint8Array(MAX_FILE + 1) }), build),
    ).rejects.toThrow("expanded size");
  });

  it("requires the current runtime without rewriting an older project", async () => {
    const archive = await exportProject(files, template, build);
    await expect(
      importProject(archive, { ...build, compiler_build_sha256: "unsupported" }),
    ).rejects.toThrow("different ImmuKnow format or compiler");
    await expect(
      importProject(archive, {
        ...build,
        shared_resources: { ...build.shared_resources, sha256: "changed" },
      }),
    ).rejects.toThrow("different ImmuKnow format or compiler");
    await expect(
      importProject(archive, { ...build, native_typst_version: "unsupported" }),
    ).rejects.toThrow("different ImmuKnow format or compiler");
    await expect(
      importProject(archive, {
        ...build,
        application_version: "another-release",
        source_revision: "another-checkout",
        source_modified: !build.source_modified,
      }),
    ).resolves.toEqual({ files, template });
  });

  it("requires the same English/French filename contract for selected entries", async () => {
    for (const name of [
      "config/edited.en.typ",
      "templates/.en.typ",
      "templates/has.dots.en.typ",
      "templates/edited.es.typ",
    ]) {
      await expect(
        exportProject({ ...files, [name]: encoder.encode("text") }, name, build),
      ).rejects.toThrow("entry point");
    }
  });

  it("checks library bytes against the app even when project hashes and file lists are rewritten", async () => {
    const original = await exportProject(files, template, build);
    const library = "templates/lib/immuknow/lib.typ";
    for (const change of ["changed", "missing", "extra", "renamed"]) {
      const changed = { ...files };
      if (change === "changed") changed[library] = encoder.encode("// Changed components\n");
      if (change === "extra" || change === "renamed")
        changed["templates/lib/immuknow/extra.typ"] = files[library];
      if (change === "missing" || change === "renamed") delete changed[library];
      await expect(exportProject(changed, template, build)).rejects.toThrow(/supplied/);
      const archive = unzipSync(original);
      const manifest = JSON.parse(new TextDecoder().decode(archive["immuknow-project.json"]));
      manifest.hashes = Object.fromEntries(
        await Promise.all(
          Object.entries(changed).map(async ([path, bytes]) => [path, await sha256(bytes)]),
        ),
      );
      manifest.build.shared_resources.files = Object.entries(manifest.hashes).map(
        ([path, sha256]) => ({ path, sha256 }),
      );
      await expect(
        importProject(
          zipSync({
            ...changed,
            "immuknow-project.json": encoder.encode(JSON.stringify(manifest)),
          }),
          build,
        ),
      ).rejects.toThrow(/supplied/);
    }
  });
});
