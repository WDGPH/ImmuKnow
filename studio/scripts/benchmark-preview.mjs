// Measure one built artifact. Run the same script before and after a preview change.
import { chromium } from "@playwright/test";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";

const base = process.env.IMMUKNOW_BASE_URL ?? "http://127.0.0.1:4173/studio/";
const samples = Number(process.env.SAMPLES ?? 30);
if (!Number.isInteger(samples) || samples < 1) {
  throw Error("SAMPLES must be a positive integer");
}
const scenarios = (
  process.env.CASES ??
  "one-page,two-page-en,two-page-fr,five-page,serif-font,wrap-layout,asset-settings"
).split(",");
const viewport = { width: 1280, height: 900 };
const reportPath = process.argv[2] ?? "/tmp/preview-benchmark.json";
const screenshotDir = reportPath.replace(/\.json$/, "") + "-screenshots";
await mkdir(screenshotDir, { recursive: true });
const browser = await chromium.launch({ headless: true });
const report = {
  browser: browser.version(),
  hardware: {
    cpu: os.cpus()[0].model,
    cores: os.cpus().length,
    memory: os.totalmem(),
    cpuQuota: await readFile("/sys/fs/cgroup/cpu.max", "utf8").catch(() => "unavailable"),
  },
  viewport,
  samples,
  cases: [],
};

function stats(values) {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (!sorted.length) return null;
  return {
    median: (sorted[Math.floor((sorted.length - 1) / 2)] +
      sorted[Math.ceil((sorted.length - 1) / 2)]) / 2,
    p95: sorted[Math.ceil(sorted.length * 0.95) - 1],
  };
}

try {
  for (const scenario of scenarios) {
    const page = await browser.newPage({ viewport });
    let workerStarts = 0;
    let resourceRequests = 0;
    page.on("worker", () => workerStarts++);
    page.on("request", (request) => {
      if (/wasm|generated\/fonts\//.test(request.url())) resourceRequests++;
    });
    const start = Date.now();
    await page.goto(new URL("proof.html", base).href);
    await page.waitForFunction(() => window.proof?.compiler.compilerVersion);
    const startup = Date.now() - start;
    const build = await page.evaluate(async () =>
      (await fetch("generated/build.json")).json(),
    );
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Performance.enable");

    const setup = await page.evaluate(
      async ({ scenario }) => {
        const proof = window.proof;
        const entry =
          scenario === "one-page"
            ? ["suspension_order_v1.en.typ", "suspension"]
            : scenario === "two-page-fr"
              ? ["overdue_diseases_v1.fr.typ", "short"]
              : scenario === "five-page"
                ? ["overdue_diseases_v1.en.typ", "long-history"]
                : ["overdue_diseases_v1.en.typ", "short"];
        const [filename, exampleId] = entry;
        const template = "templates/" + filename;
        const example = proof.examples.find((item) => item.id === exampleId);
        if (!example?.payloads[filename]) throw Error("Missing benchmark example");
        const notice = structuredClone(example.payloads[filename]);
        if (scenario === "five-page") {
          // Seventy rows normally produce three pages. Expand the synthetic
          // history to exercise a roughly five-page notice.
          const history = notice.history;
          notice.history = Array.from({ length: 3 }, (_, copy) =>
            history.map((item) => ({
              ...item,
              date_given: String(Number(item.date_given.slice(0, 4)) + copy * 10) +
                item.date_given.slice(4),
            })),
          ).flat().slice(0, 175);
        }
        const job = {
          ...proof.job,
          template,
          example: exampleId,
          notice,
          files: { ...proof.job.files },
        };
        if (scenario === "serif-font") {
          const settings = new TextDecoder().decode(job.files["/templates/settings.typ"]);
          if (!settings.includes('#let body-font = "FreeSans"')) {
            throw Error("Expected default body font setting");
          }
          job.files["/templates/settings.typ"] = new TextEncoder().encode(
            settings.replace('#let body-font = "FreeSans"', '#let body-font = "FreeSerif"'),
          );
        }
        let assetVariants;
        if (scenario === "asset-settings") {
          const logo = job.files["/templates/assets/logo.png"];
          if (!logo) throw Error("Benchmark logo asset is missing");
          const bitmap = await createImageBitmap(new Blob([logo], { type: "image/png" }));
          const canvas = document.createElement("canvas");
          canvas.width = bitmap.width;
          canvas.height = bitmap.height;
          const context = canvas.getContext("2d");
          if (!context) throw Error("Canvas context is unavailable");
          assetVariants = [];
          for (const color of ["#bb4422", "#2244bb"]) {
            context.drawImage(bitmap, 0, 0);
            context.fillStyle = color;
            context.fillRect(0, 0, bitmap.width / 5, bitmap.height / 5);
            const blob = await new Promise((resolve, reject) =>
              canvas.toBlob((value) => value ? resolve(value) : reject(Error("PNG encode failed")), "image/png"),
            );
            assetVariants.push(new Uint8Array(await blob.arrayBuffer()));
          }
          bitmap.close();
        }
        const source = new TextDecoder().decode(job.files["/" + template]);
        const settings = new TextDecoder().decode(job.files["/templates/settings.typ"]);
        const setup = {
          job,
          source,
          settings,
          assetVariants,
          files: Object.keys(job.files).length,
          bytes: Object.values(job.files).reduce((sum, bytes) => sum + bytes.length, 0),
          selectedFont: scenario === "serif-font" ? "FreeSerif" : "FreeSans",
        };
        window.benchmarkSetup = setup;
        return {
          files: setup.files,
          bytes: setup.bytes,
          selectedFont: setup.selectedFont,
        };
      },
      { scenario },
    );

    const runs = [];
    const screenshots = [];
    for (let i = 0; i <= samples; i++) {
      const run = await page.evaluate(
        async ({ scenario, index }) => {
          const { proof } = window;
          const setup = window.benchmarkSetup;
          const encoder = new TextEncoder();
          const prepareStart = performance.now();
          const visibleText =
            scenario === "one-page"
              ? "Order for Suspension from Attendance at School"
              : scenario === "two-page-fr"
                ? "En date du *#date_as_of*"
                : "As of *#date_as_of*";
          if (!setup.source.includes(visibleText)) {
            throw Error("Visible benchmark text was not found");
          }
          const replacement =
            scenario === "one-page"
              ? `Order ${index} for Suspension from Attendance at School`
              : scenario === "two-page-fr"
                ? `En date du *#date_as_of* (révision ${index})`
                : scenario === "wrap-layout" && index % 2 === 0
                  ? `As of *#date_as_of* (revision ${index}, with a deliberately longer sentence that wraps within the first visible paragraph of this example notice)`
                : `As of *#date_as_of* (revision ${index})`;
          const source = setup.source.replace(visibleText, replacement);
          const files = {
            ...setup.job.files,
            ["/" + setup.job.template]: encoder.encode(source),
          };
          if (scenario === "serif-font") {
            const color = index % 2 ? "#993344" : "#005568";
            files["/templates/settings.typ"] = encoder.encode(
              setup.settings.replace("#005568", color),
            );
          }
          if (scenario === "asset-settings") {
            files["/templates/assets/logo.png"] = setup.assetVariants[index % 2];
            files["/templates/settings.typ"] = encoder.encode(
              setup.settings.replace("#005568", index % 2 ? "#993344" : "#005568"),
            );
          }
          const request = { ...setup.job, files };
          const prepare = performance.now() - prepareStart;
          window.benchmarkLastRequest = request;
          const revision = proof.submit([request]);
          const result = await new Promise((resolve, reject) => {
            const deadline = performance.now() + 60000;
            const poll = () => {
              const result = proof.results.find((item) => item.revision === revision);
              if (result?.timing?.committed) resolve(result);
              else if (result?.diagnostics?.some((item) => item.severity === "error")) {
                reject(Error(JSON.stringify(result.diagnostics)));
              } else if (performance.now() > deadline) reject(Error("Preview timeout"));
              else setTimeout(poll, 5);
            };
            poll();
          });
          if (
            scenario === "serif-font" &&
            result.checks.some((check) => check.code === "compiler.font_substitution")
          ) {
            throw Error("The supplied-font notice substituted a font");
          }
          const canvas = document.querySelector("#preview-scroll canvas");
          const corner = canvas?.getContext("2d")?.getImageData(10, 10, 1, 1).data;
          if (!corner || corner[0] < 245 || corner[1] < 245 || corner[2] < 245) {
            throw Error("The preview page background was not painted white");
          }
          const timing = result.timing;
          const run = {
            ...timing,
            revision: result.revision,
            context: result.context,
            prepare,
            schedule: timing.sent - timing.requested,
            transfer: timing.received - timing.sent,
            total: timing.committed - timing.requested + prepare,
            pages: result.preview?.pages.length ?? result.summary?.page_count,
            artifactBytes: result.preview?.artifact.length ?? 0,
            canvases: document.querySelectorAll("#preview-scroll canvas").length,
            rendererBytes: proof.viewer?.resources?.rendererBytes ?? 0,
            resources: proof.viewer?.resources,
          };
          proof.results.length = 0;
          return run;
        },
        { scenario, index: i },
      );
      runs.push(run);
      if (i === 1 || i === 2) {
        const path = `${screenshotDir}/${scenario}-${i}.png`;
        const shot = await page.locator("#preview-scroll").screenshot({ path });
        screenshots.push({
          path,
          sha256: createHash("sha256").update(shot).digest("hex"),
        });
      }
    }
    await cdp.send("HeapProfiler.collectGarbage");
    const metrics = await cdp.send("Performance.getMetrics");
    const heap = Object.fromEntries(
      metrics.metrics
        .filter((metric) => ["JSHeapUsedSize", "Nodes", "Documents"].includes(metric.name))
        .map((metric) => [metric.name, metric.value]),
    );
    const exportResult = await page.evaluate(async (last) => {
      const { proof } = window;
      if (typeof proof.compiler.exportPdf !== "function") return null;
      const started = performance.now();
      const result = await proof.compiler.exportPdf(
        window.benchmarkLastRequest,
        last.revision,
        last.context,
      );
      return {
        samples: 1,
        elapsed: performance.now() - started,
        bytes: result.pdf.length,
        timing: result.timing,
      };
    }, runs.at(-1));
    report.cases.push({
      scenario,
      build,
      startup,
      workerStarts,
      resourceRequests,
      heap,
      files: setup.files,
      bytes: setup.bytes,
      selectedFont: setup.selectedFont,
      export: exportResult,
      screenshots,
      visiblePixelsChanged: screenshots.length === 2 && screenshots[0].sha256 !== screenshots[1].sha256,
      cold: runs[0],
      warm: runs.slice(1),
    });
    await page.close();
  }
} finally {
  await browser.close();
}

await writeFile(reportPath, JSON.stringify(report, null, 2) + "\n");
for (const caseResult of report.cases) {
  const keys = [
    "prepare", "schedule", "transfer", "reconcile", "fonts", "filesystem",
    "compile", "artifact", "pdf", "evidence", "load", "render", "total",
    "mappedFiles", "mappedBytes", "fontRebuilds", "canvasBytes",
    "rendererBytes", "artifactBytes", "wasmBytes",
  ];
  const measurements = Object.fromEntries(
    keys.map((key) => [key, stats(caseResult.warm.map((run) => run[key]))]),
  );
  console.log(JSON.stringify({
    scenario: caseResult.scenario,
    pages: caseResult.warm.map((run) => run.pages).filter(Number.isFinite)[0],
    startup: caseResult.startup,
    cold: caseResult.cold.total,
    visiblePixelsChanged: caseResult.visiblePixelsChanged,
    export: caseResult.export,
    measurements,
  }));
}
