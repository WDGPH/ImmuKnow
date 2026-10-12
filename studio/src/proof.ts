import "./style.css";
import { type CompileInput, Compiler } from "./compile";
import { decodeFiles, runtimeFiles } from "./project";
import type { Bundle, CompileResult } from "./types";
import { Viewer } from "./viewer";

const results: CompileResult[] = [];
let latestJob: CompileInput | undefined;
let latestRevision = 0;
const container = document.createElement("div");
container.id = "preview-scroll";
container.style.cssText = "width:800px;height:700px;flex:none";
document.body.append(container);
const viewer = new Viewer(
  container,
  () => {},
  () => false,
);
const compiler = new Compiler(
  (message) => {
    const status = document.body.querySelector("p");
    if (status) status.textContent = message;
  },
  (reply) => {
    results.push(reply);
    if (reply.preview) {
      void viewer.open(
        reply.preview,
        [...(reply.summary?.checks ?? []), ...reply.checks],
        reply.timing,
      );
    }
  },
);
const bundle: Bundle = await fetch(new URL("../generated/project.json", import.meta.url)).then(
  (response) => response.json(),
);
const files = await decodeFiles(bundle);
const template = "templates/overdue_diseases_v1.en.typ";
const filename = template.slice(template.lastIndexOf("/") + 1);
const example = bundle.examples.find((item) => item.payloads[filename]);
if (!example) throw new Error("Compiler proof needs an English disease example");
const job: CompileInput = {
  template,
  example: example.id,
  files: runtimeFiles(files),
  notice: example.payloads[filename],
  creationTimestamp: bundle.creationTimestamp,
};

declare global {
  interface Window {
    proof: {
      compiler: Compiler;
      viewer: Viewer;
      job: typeof job;
      examples: Bundle["examples"];
      results: CompileResult[];
      submit: (jobs: (typeof job)[]) => number;
      exportPdf: (revision: number) => Promise<Uint8Array>;
    };
  }
}
window.proof = {
  compiler,
  viewer,
  job,
  examples: bundle.examples,
  results,
  submit: (jobs) => {
    let revision = compiler.revision;
    for (const request of jobs) {
      latestJob = request;
      revision = compiler.submit(request);
      latestRevision = revision;
    }
    return revision;
  },
  exportPdf: async (revision) => {
    const result = results.find((item) => item.revision === revision);
    if (
      !latestJob ||
      revision !== latestRevision ||
      !result?.preview ||
      result.context !== compiler.context
    ) {
      throw new Error("Export requires the current successful preview");
    }
    return (await compiler.exportPdf(latestJob, revision, result.context)).pdf;
  },
};
