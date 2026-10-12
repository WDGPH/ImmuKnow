import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { expect, type Page, test } from "@playwright/test";
import type { CompileResult, PreviewPage } from "../src/types";

type Evidence = Omit<CompileResult, "preview"> & {
  preview?: { artifact: number[]; pages: PreviewPage[] };
};
const root = resolve("..");
const clockSource = `#import "lib/immuknow/lib.typ" as immuknow
#let notice = json(sys.inputs.at("data"))
#immuknow.check-notice(notice, version: sys.inputs.at("notice-version"), language: sys.inputs.at("notice-language"))
#show: immuknow.notice-style.with(notice: notice)
Today: #datetime.today().display("[year]-[month]-[day]")
`;

async function evidence(page: Page, revision: number): Promise<Evidence> {
  await page.waitForFunction(
    (revision) => window.proof.results.some((result) => result.revision === revision),
    revision,
  );
  return page.evaluate((revision) => {
    const result = window.proof.results.find((result) => result.revision === revision);
    if (!result) throw new Error("Compiler result not available");
    return {
      ...result,
      preview: result.preview
        ? { ...result.preview, artifact: Array.from(result.preview.artifact) }
        : undefined,
    };
  }, revision);
}

async function exportPdf(page: Page, revision: number): Promise<number[]> {
  await page.waitForFunction((revision) => {
    const result = window.proof.results.find((item) => item.revision === revision);
    return Boolean(result?.timing?.committed);
  }, revision);
  return page.evaluate(
    async (revision) => Array.from(await window.proof.exportPdf(revision)),
    revision,
  );
}

test("browser snapshots retain native findings, frozen dates and recover from errors", async ({
  page,
}, info) => {
  const externalRequests: string[] = [];
  await page.context().route("**/*", (route) => {
    if (
      new URL(route.request().url()).origin !== new URL(info.project.use.baseURL as string).origin
    ) {
      externalRequests.push(route.request().url());
      return route.abort();
    }
    return route.continue();
  });
  await page.goto("proof.html");
  await page.waitForFunction(() => Boolean(window.proof?.compiler.compilerVersion));
  const build = JSON.parse(
    readFileSync(resolve(root, "studio/public/generated/build.json"), "utf8"),
  );
  expect(await page.evaluate(() => window.proof.compiler.compilerVersion)).toBe(
    build.native_typst_version,
  );

  const revision = await page.evaluate(() => window.proof.submit([window.proof.job]));
  const ordinary = await evidence(page, revision);
  expect(ordinary.preview?.artifact.length).toBeGreaterThan(1000);
  expect(ordinary.preview?.pages.length).toBe(ordinary.summary?.page_count);
  expect(ordinary.preview?.pages[0].text.length).toBeGreaterThan(0);
  expect(ordinary.checks).toEqual([]);
  expect(ordinary.diagnostics).toEqual([]);
  const job = await page.evaluate(() => ({
    ...window.proof.job,
    files: Object.fromEntries(
      Object.entries(window.proof.job.files).map(([path, bytes]) => [path, Array.from(bytes)]),
    ),
  }));
  const staged = info.outputPath("native-project");
  mkdirSync(staged, { recursive: true });
  for (const [path, bytes] of Object.entries(job.files)) {
    const target = resolve(staged, path.slice(1));
    mkdirSync(dirname(target), { recursive: true });
    writeFileSync(target, Buffer.from(bytes));
  }
  mkdirSync(resolve(staged, "data"), { recursive: true });
  writeFileSync(resolve(staged, "data/notice.json"), JSON.stringify(job.notice));
  const nativeOptions = [
    "--root",
    staged,
    "--creation-timestamp",
    String(job.creationTimestamp),
    "--input",
    "data=/data/notice.json",
    "--input",
    `notice-template=${job.notice.template}`,
    "--input",
    `notice-version=${job.notice.version_id}`,
    "--input",
    `notice-language=${job.notice.language}`,
  ];
  const typst = process.env.TYPST_BIN || "typst";
  const nativePdf = info.outputPath("ordinary.native.pdf");
  const browserPdf = info.outputPath("ordinary.browser.pdf");
  writeFileSync(browserPdf, Buffer.from(await exportPdf(page, revision)));
  execFileSync(typst, ["compile", ...nativeOptions, resolve(staged, job.template), nativePdf]);
  const summaries = JSON.parse(
    execFileSync(
      typst,
      [
        "eval",
        ...nativeOptions,
        "--in",
        resolve(staged, job.template),
        "query(<immuknow-report>).map(it => it.value)",
        "--format",
        "json",
      ],
      { encoding: "utf8" },
    ),
  );
  expect(ordinary.summary).toEqual(summaries[0]);
  const inspectPdf = (path: string) =>
    JSON.parse(
      execFileSync(
        "uv",
        [
          "run",
          "python",
          "-c",
          "import json,sys; from pypdf import PdfReader; r=PdfReader(sys.argv[1]); print(json.dumps({'date':str(r.metadata.creation_date), 'text':[''.join(p.extract_text().split()) for p in r.pages]}))",
          path,
        ],
        { cwd: root, encoding: "utf8" },
      ),
    );
  expect(inspectPdf(browserPdf)).toEqual(inspectPdf(nativePdf));

  for (const timestamp of [job.creationTimestamp, job.creationTimestamp + 86400]) {
    const clockRevision = await page.evaluate(
      ({ source, timestamp }) => {
        const job = window.proof.job;
        return window.proof.submit([
          {
            ...job,
            creationTimestamp: timestamp,
            files: { ...job.files, [`/${job.template}`]: new TextEncoder().encode(source) },
          },
        ]);
      },
      { source: clockSource, timestamp },
    );
    const clock = await evidence(page, clockRevision);
    expect(clock.checks).toEqual([]);
    const browserClockPdf = info.outputPath(`clock-${timestamp}.browser.pdf`);
    const nativeClockPdf = info.outputPath(`clock-${timestamp}.native.pdf`);
    writeFileSync(browserClockPdf, Buffer.from(await exportPdf(page, clockRevision)));
    writeFileSync(resolve(staged, job.template), clockSource);
    const options = nativeOptions.slice();
    options[options.indexOf("--creation-timestamp") + 1] = String(timestamp);
    execFileSync(typst, ["compile", ...options, resolve(staged, job.template), nativeClockPdf]);
    expect(inspectPdf(browserClockPdf)).toEqual(inspectPdf(nativeClockPdf));
    expect(inspectPdf(browserClockPdf).text.join(" ")).toContain(
      new Date(timestamp * 1000).toISOString().slice(0, 10),
    );
  }

  const warningRevision = await page.evaluate(() => {
    const job = window.proof.job;
    const source = `#import "lib/immuknow/lib.typ" as immuknow
#let notice = json(sys.inputs.at("data"))
#show: immuknow.notice-style.with(notice: notice)
#immuknow.notice-section("Long section")[#for _ in range(75) [Extra paragraph. #parbreak()]]`;
    return window.proof.submit([
      { ...job, files: { ...job.files, [`/${job.template}`]: new TextEncoder().encode(source) } },
    ]);
  });
  const warning = await evidence(page, warningRevision);
  expect(warning.preview?.artifact.length).toBeGreaterThan(1000);
  expect(
    warning.summary?.checks.some(
      (check) => check.code === "layout.section_pages" && check.status === "warn",
    ),
  ).toBe(true);
  expect(warning.diagnostics).toEqual([]);
  const sourceWarningRevision = await page.evaluate(() => {
    const job = window.proof.job;
    const filename = job.template.slice(job.template.lastIndexOf("/") + 1);
    const example = window.proof.examples.find((example) => example.id === "source-warnings");
    if (!example) throw new Error("Source warning example is missing");
    return window.proof.submit([
      { ...job, example: example.id, notice: example.payloads[filename] },
    ]);
  });
  const sourceWarning = await evidence(page, sourceWarningRevision);
  expect(sourceWarning.preview?.artifact.length).toBeGreaterThan(1000);
  expect(
    sourceWarning.summary?.checks.some(
      (check) => check.code === "content.address_age_unknown" && check.status === "warn",
    ),
  ).toBe(true);
  expect(
    sourceWarning.summary?.checks.some(
      (check) => check.code === "content.birth_date_unknown" && check.status === "warn",
    ),
  ).toBe(true);
  const missingRevision = await page.evaluate(() => {
    const job = window.proof.job;
    return window.proof.submit([
      {
        ...job,
        files: {
          ...job.files,
          [`/${job.template}`]: new TextEncoder().encode("Evidence intentionally omitted."),
        },
      },
    ]);
  });
  const missing = await evidence(page, missingRevision);
  expect(missing.preview?.artifact.length).toBeGreaterThan(1000);
  expect(missing.summary).toBeUndefined();
  expect(missing.checks.map((check) => check.code)).toEqual(["render.evidence_failed"]);
  const errorRevision = await page.evaluate(() => {
    const job = window.proof.job;
    return window.proof.submit([
      {
        ...job,
        files: { ...job.files, [`/${job.template}`]: new TextEncoder().encode("#let = ]") },
      },
    ]);
  });
  const error = await evidence(page, errorRevision);
  expect(error.preview).toBeUndefined();
  expect(error.diagnostics.some((diagnostic) => diagnostic.severity === "error")).toBe(true);
  const recoverRevision = await page.evaluate(() => {
    const job = window.proof.job;
    return window.proof.submit([
      {
        ...job,
        files: { ...job.files, [`/${job.template}`]: new TextEncoder().encode("#let = ]") },
      },
      job,
      job,
    ]);
  });
  const recovered = await evidence(page, recoverRevision);
  expect(recovered.summary).toEqual(ordinary.summary);
  expect(recovered.checks).toEqual([]);
  expect(
    await page.evaluate(
      (revision) =>
        window.proof.results.some(
          (result) => result.revision === revision - 1 || result.revision === revision - 2,
        ),
      recoverRevision,
    ),
  ).toBe(false);
  const fontManifest = JSON.parse(
    readFileSync(resolve(root, "studio/assets/fonts/manifest.json"), "utf8"),
  );
  const authoredRevision = await page.evaluate((source) => {
    const job = window.proof.job;
    return window.proof.submit([
      {
        ...job,
        files: {
          ...job.files,
          [`/${job.template}`]: new TextEncoder().encode(
            source.replace("notice: notice)", 'notice: notice, font: "FreeSerif")'),
          ),
        },
      },
    ]);
  }, clockSource);
  const authored = await evidence(page, authoredRevision);
  expect(authored.preview?.artifact.length).toBeGreaterThan(1000);
  expect(authored.checks.some((check) => check.code === "compiler.font_substitution")).toBe(false);
  const authoredPdf = info.outputPath("serif.browser.pdf");
  writeFileSync(authoredPdf, Buffer.from(await exportPdf(page, authoredRevision)));
  const fontNames = execFileSync(
    "uv",
    [
      "run",
      "python",
      "-c",
      "import sys; from pypdf import PdfReader; r=PdfReader(sys.argv[1]); print([str(v.get_object().get('/BaseFont')) for p in r.pages for v in p['/Resources']['/Font'].values()])",
      authoredPdf,
    ],
    { cwd: root, encoding: "utf8" },
  );
  expect(fontNames).toContain("FreeSerif");
  expect(fontNames).not.toContain("FreeSans");
  const missingFontRevision = await page.evaluate((digest) => {
    const job = window.proof.job;
    return window.proof.submit([
      {
        ...job,
        files: {
          ...job.files,
          "/templates/fonts/manifest.json": new TextEncoder().encode(
            JSON.stringify({ "missing.ttf": digest }),
          ),
        },
      },
    ]);
  }, fontManifest["FreeSerif.ttf"]);
  const missingFont = await evidence(page, missingFontRevision);
  expect(missingFont.preview).toBeUndefined();
  expect(
    missingFont.checks.some(
      (check) =>
        check.status === "fail" && check.message.includes("Use the supplied fonts/manifest.json"),
    ),
  ).toBe(true);
  const finalRevision = await page.evaluate(() => window.proof.submit([window.proof.job]));
  expect((await evidence(page, finalRevision)).summary).toEqual(ordinary.summary);
  expect(externalRequests).toEqual([]);
});

test("warm snapshots match a restarted compiler after multi-file, data, asset and import changes", async ({
  page,
}) => {
  await page.goto("proof.html");
  await page.waitForFunction(() => Boolean(window.proof?.compiler.compilerVersion));
  const comparisons = await page.evaluate(async () => {
    const proof = window.proof,
      original = proof.job;
    const encode = (text: string) => new TextEncoder().encode(text);
    async function result(revision: number) {
      return await new Promise<CompileResult>((resolve, reject) => {
        const start = performance.now();
        const poll = () => {
          const reply = proof.results.find((r) => r.revision === revision);
          if (reply) resolve(reply);
          else if (performance.now() - start > 30000) reject(Error("Compiler timeout"));
          else setTimeout(poll, 5);
        };
        poll();
      });
    }
    async function painted(reply: CompileResult) {
      if (!reply.preview) return undefined;
      await new Promise<void>((resolve, reject) => {
        const start = performance.now();
        const poll = () => {
          if (reply.timing?.committed) resolve();
          else if (performance.now() - start > 30000) reject(Error("Preview paint timeout"));
          else setTimeout(poll, 5);
        };
        poll();
      });
      return Array.from(
        document.querySelectorAll<HTMLCanvasElement>("#preview-scroll canvas"),
        (canvas) => canvas.toDataURL("image/png"),
      );
    }
    function sameOutput(
      left: CompileResult & { pixels?: string[] },
      right: CompileResult & { pixels?: string[] },
    ) {
      return Boolean(
        left.preview?.artifact.length &&
          right.preview?.artifact.length &&
          left.pixels?.length === left.preview.pages.length &&
          right.pixels?.length === right.preview.pages.length &&
          JSON.stringify(left.preview.pages) === JSON.stringify(right.preview.pages) &&
          JSON.stringify(left.pixels) === JSON.stringify(right.pixels),
      );
    }
    async function compile(job: typeof original, cold = false) {
      if (cold) {
        proof.compiler.restart();
        await new Promise<void>((resolve) => {
          const poll = () => {
            if (proof.compiler.compilerVersion) resolve();
            else setTimeout(poll, 5);
          };
          poll();
        });
      }
      const reply = await result(proof.compiler.submit(job, true));
      return Object.assign(reply, { pixels: await painted(reply) });
    }
    const source = `#import "part.typ": title\n#let n = json(sys.inputs.at("data"))\n#title #n.client_data.name\n#image("assets/live.svg")\n#datetime.today().display("[year]-[month]-[day]")`;
    const image = (color: string) =>
      encode(
        `<svg xmlns="http://www.w3.org/2000/svg" width="30" height="20"><rect width="30" height="20" fill="${color}"/></svg>`,
      );
    const a = {
      ...original,
      files: {
        ...original.files,
        [`/${original.template}`]: encode(source),
        "/templates/part.typ": encode('#let title = "A"'),
        "/templates/assets/live.svg": image("red"),
      },
    };
    // A is already active; B is superseded by C. C must retain B's file edit.
    const active = proof.compiler.submit(a, true);
    const b = { ...a, files: { ...a.files, "/templates/part.typ": encode('#let title = "B"') } };
    proof.compiler.submit(b);
    const c = { ...b, files: { ...b.files, "/templates/assets/live.svg": image("blue") } };
    const latest = proof.compiler.submit(c);
    await result(active);
    const warmReply = await result(latest);
    const warm = Object.assign(warmReply, { pixels: await painted(warmReply) });
    const cold = await compile(c, true);
    const checks = [sameOutput(warm, cold)];
    let last = c;
    for (const path of ["/templates/part.typ", "/templates/assets/live.svg"]) {
      const files: Record<string, Uint8Array> = { ...last.files };
      delete files[path];
      const missing = { ...last, files };
      checks.push(!(await compile(missing)).preview && !(await compile(missing, true)).preview);
      const recovered = await compile(last),
        fresh = await compile(last, true);
      checks.push(sameOutput(recovered, fresh));
    }
    last = {
      ...c,
      creationTimestamp: c.creationTimestamp + 86400,
      notice: {
        ...c.notice,
        client_data: { ...c.notice.client_data, name: "Updated example name" },
      },
    };
    const changed = await compile(last),
      fresh = await compile(last, true);
    checks.push(sameOutput(changed, fresh));
    const manifest = await (await fetch("generated/fonts/manifest.json")).json();
    const supplied = Object.fromEntries(
      await Promise.all(
        Object.keys(manifest).map(async (name) => [
          `/templates/fonts/${name}`,
          new Uint8Array(await (await fetch(`generated/fonts/${name}`)).arrayBuffer()),
        ]),
      ),
    );
    const complete = { ...original, files: { ...original.files, ...supplied } };
    const suppliedWarm = await compile(complete),
      suppliedCold = await compile(complete, true);
    checks.push(sameOutput(suppliedWarm, suppliedCold));
    const badFiles = [
      { ...complete.files, "/templates/fonts/FreeSans.ttf": encode("changed font") },
      {
        ...complete.files,
        "/templates/assets/extra.otf": supplied["/templates/fonts/FreeSans.ttf"],
      },
      {
        ...original.files,
        "/templates/fonts/FreeSans.ttf": supplied["/templates/fonts/FreeSans.ttf"],
      },
      {
        ...complete.files,
        "/templates/fonts/manifest.json": encode(
          JSON.stringify({ ...manifest, "FreeSans.ttf": "changed" }),
        ),
      },
    ];
    for (const files of badFiles) {
      const bad = { ...original, files };
      checks.push(!(await compile(bad)).preview && !(await compile(bad, true)).preview);
      const recovered = await compile(complete);
      checks.push(sameOutput(recovered, suppliedCold));
    }
    const remote = {
      ...original,
      files: {
        ...original.files,
        [`/${original.template}`]: encode('#import "@preview/definitely-unavailable:0.0.1": *'),
      },
    };
    for (let i = 0; i < 2; i++) {
      const denied = await compile(remote);
      checks.push(
        !denied.preview &&
          denied.diagnostics.some((diagnostic) =>
            diagnostic.message.includes("runtime package downloads are disabled"),
          ),
      );
    }
    const invalidDate = await compile({ ...original, creationTimestamp: -1 });
    checks.push(
      !invalidDate.preview &&
        invalidDate.diagnostics.every((diagnostic) => !diagnostic.message.includes("@preview")),
    );
    const restored = await compile(original),
      clean = await compile(original, true);
    checks.push(JSON.stringify(restored.summary) === JSON.stringify(clean.summary));
    checks.push(sameOutput(restored, clean));
    return checks;
  });
  expect(comparisons).toEqual(comparisons.map(() => true));
});

test("invalid report evidence retains the readable preview and cannot claim a clean result", async ({
  page,
}) => {
  await page.goto("proof.html");
  await page.waitForFunction(() => Boolean(window.proof?.compiler.compilerVersion));
  const original = await page.evaluate(() => window.proof.submit([window.proof.job]));
  const clean = await evidence(page, original);
  expect(clean.summary).toBeDefined();
  for (const damage of ["row", "stage", "component", "page_count"]) {
    const revision = await page.evaluate(
      ({ report, damage }) => {
        if (!report) throw new Error("Missing report for test");
        if (damage === "row") report.identity.row_key = "row-000002";
        else if (damage === "stage") report.checks[0].stage = "output";
        else if (damage === "component") report.components.unknown = true;
        else report.page_count = 3;
        const job = window.proof.job;
        const encode = (value: string) => new TextEncoder().encode(value);
        return window.proof.submit([
          {
            ...job,
            files: {
              ...job.files,
              "/templates/damaged-report.json": encode(JSON.stringify(report)),
              [`/${job.template}`]: encode(
                '#metadata(json("damaged-report.json")) <immuknow-report>\nReadable first page\n#pagebreak()\nReadable second page',
              ),
            },
          },
        ]);
      },
      { report: clean.summary, damage },
    );
    const result = await evidence(page, revision);
    expect(result.preview?.pages.length).toBe(2);
    expect(result.summary).toBeUndefined();
    expect(result.checks.map((check) => check.code)).toContain("render.evidence_failed");
  }
});

test("library changes are refused before compilation and the next valid project recovers", async ({
  page,
}) => {
  await page.goto("proof.html");
  await page.waitForFunction(() => Boolean(window.proof?.compiler.compilerVersion));
  for (const change of ["changed", "missing", "extra", "renamed"]) {
    const revision = await page.evaluate((change) => {
      const job = window.proof.job;
      const files = { ...job.files };
      const path = "/templates/lib/immuknow/src/findings.typ";
      if (change === "changed") files[path] = new TextEncoder().encode("Changed component");
      if (change === "extra" || change === "renamed")
        files["/templates/lib/immuknow/extra.typ"] = files[path];
      if (change === "missing" || change === "renamed") delete files[path];
      return window.proof.submit([{ ...job, files }]);
    }, change);
    const denied = await evidence(page, revision);
    expect(denied.preview).toBeUndefined();
    expect(denied.timing?.compile).toBeUndefined();
    expect(denied.diagnostics.some((item) => item.message.includes("supplied"))).toBe(true);
    const restored = await page.evaluate(() => window.proof.submit([window.proof.job]));
    expect((await evidence(page, restored)).preview?.artifact.length).toBeGreaterThan(1000);
  }
});

test("repeated edits keep one compiler, bounded pages and an authoritative filesystem", async ({
  page,
}) => {
  let compilerWorkers = 0,
    pdfWorkers = 0,
    resources = 0;
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("worker", (worker) => {
    if (worker.url().includes("compile.worker")) compilerWorkers++;
    if (worker.url().includes("pdf.worker")) pdfWorkers++;
  });
  page.on("request", (request) => {
    if (/wasm|generated\/fonts\//.test(request.url())) resources++;
  });
  await page.goto("proof.html");
  await page.waitForFunction(() => Boolean(window.proof?.compiler.compilerVersion));
  const initialResources = resources;
  const samples = await page.evaluate(async () => {
    const { proof } = window,
      original = proof.job;
    const source = new TextDecoder().decode(original.files[`/${original.template}`]);
    const samples = [];
    for (let i = 0; i < 90; i++) {
      const files = {
        ...original.files,
        [`/${original.template}`]: new TextEncoder().encode(
          `${source}\n#text(size: 6pt)[Edit ${i}]`,
        ),
      };
      const revision = proof.compiler.submit({ ...original, files }, true);
      const result = await new Promise<CompileResult>((resolve, reject) => {
        const start = performance.now();
        const poll = () => {
          const result = proof.results.find((r) => r.revision === revision);
          if (result?.timing?.committed) resolve(result);
          else if (result && !result.preview) reject(Error(JSON.stringify(result.diagnostics)));
          else if (performance.now() - start > 30000) reject(Error("Preview timeout"));
          else setTimeout(poll, 5);
        };
        poll();
      });
      const resourceRequests = performance
        .getEntriesByType("resource")
        .filter((entry) => /wasm|generated\/fonts\//.test(entry.name)).length;
      samples.push({ timing: result.timing, resources: proof.viewer.resources, resourceRequests });
      proof.results.length = 0;
    }
    return samples;
  });
  expect(compilerWorkers).toBe(1);
  expect(pdfWorkers).toBe(0);
  // The renderer loads its local Wasm once on the first painted preview.
  expect(resources).toBe(initialResources + 1);
  const retained = samples[0].timing?.retainedFiles;
  for (const sample of samples.slice(1)) {
    expect(sample.resourceRequests).toBe(samples[0].resourceRequests);
    expect(sample.timing?.mappedFiles).toBe(1);
    expect(sample.timing?.retainedFiles).toBe(retained);
    expect(sample.timing?.fontRebuilds).toBe(0);
    expect(sample.timing?.pdf).toBeUndefined();
    expect(sample.timing?.artifact).toBeGreaterThan(0);
    expect(sample.resources.documents).toBe(1);
    expect(sample.resources.canvases).toBe(2);
    expect(sample.resources.pending).toBe(0);
    expect(sample.resources.preparing).toBe(0);
    expect(sample.resources.artifactBytes).toBeGreaterThan(0);
  }
  expect(Math.max(...samples.map((sample) => sample.resources.rendererBytes))).toBeLessThan(
    64 * 1024 * 1024,
  );
  expect(Math.max(...samples.map((sample) => sample.resources.canvasBytes))).toBeLessThan(
    32 * 1024 * 1024,
  );
  // Disposal releases listeners, renderer sessions, documents and every canvas.
  await page.evaluate(() => window.proof.viewer.destroy());
  await expect(page.locator("canvas")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("seven-page preview is fully painted and scrolling does not repaint", async ({ page }) => {
  await page.goto("proof.html");
  await page.waitForFunction(() => Boolean(window.proof?.compiler.compilerVersion));
  const revision = await page.evaluate(() => {
    const job = window.proof.job;
    const pages = Array.from({ length: 7 }, (_, index) => `Page ${index + 1} of seven`);
    const source = `#import "settings.typ": *\n#show: notice-style\n${pages.join("\n#pagebreak()\n")}`;
    return window.proof.submit([
      {
        ...job,
        files: { ...job.files, [`/${job.template}`]: new TextEncoder().encode(source) },
      },
    ]);
  });
  await page.waitForFunction((revision) => {
    const result = window.proof.results.find((item) => item.revision === revision);
    return Boolean(result?.timing?.committed);
  }, revision);
  await expect(page.locator(".preview-page")).toHaveCount(7);
  const result = await page.evaluate(async (revision) => {
    const { proof } = window;
    const preview = proof.results.find((item) => item.revision === revision)?.preview;
    if (!preview) throw Error("Seven-page preview missing");
    const before = proof.viewer.resources;
    const scroller = document.querySelector("#preview-scroll") as HTMLElement;
    scroller.scrollTop = scroller.scrollHeight;
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
    const after = proof.viewer.resources;
    const renderedText = Array.from(scroller.querySelectorAll(".preview-page"), (paper) =>
      paper.textContent?.trim(),
    );
    const oversized = { ...preview, pages: Array.from({ length: 300 }, () => preview.pages[0]) };
    let limitError = "";
    try {
      await proof.viewer.open(oversized);
    } catch (error) {
      limitError = String(error);
    }
    return {
      pages: proof.viewer.pages,
      before,
      after,
      renderedText,
      retainedPages: scroller.querySelectorAll(".preview-page").length,
      limitError,
    };
  }, revision);
  expect(result.pages).toBe(7);
  expect(result.before.canvases).toBe(7);
  expect(result.before.canvasesPainted).toBe(7);
  expect(result.after.canvasesPainted).toBe(result.before.canvasesPainted);
  expect(result.after.canvasBytes).toBe(result.before.canvasBytes);
  expect(result.renderedText).toHaveLength(7);
  expect(result.renderedText[6]).toContain("Page 7 of seven");
  expect(result.limitError).toContain("resource limit");
  expect(result.retainedPages).toBe(7);
});
