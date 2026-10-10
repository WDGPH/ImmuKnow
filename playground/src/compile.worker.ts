import { createTypstCompiler } from "@myriaddreamin/typst.ts/compiler";
import {
  loadFonts,
  withAccessModel,
  withPackageRegistry,
} from "@myriaddreamin/typst.ts/options.init";
import * as wrapper from "../vendor/compiler/typst_ts_web_compiler.js";
import wasmUrl from "../vendor/compiler/typst_ts_web_compiler_bg.wasm?url";
import type { CompileRequest, Diagnostic, WorkerReply } from "./types";

const send = (message: WorkerReply, transfer: Transferable[] = []) =>
  postMessage(message, { transfer });
const compiler = createTypstCompiler();
const missingPackages = new Set<string>();
try {
  const base = import.meta.env.BASE_URL;
  const response = await fetch(`${base}generated/fonts/manifest.json`);
  if (!response.ok) throw new Error("Pinned fonts are unavailable. Rebuild the static assets.");
  const fonts = await response.json();
  await compiler.init({
    getWrapper: async () => wrapper,
    getModule: () => wasmUrl,
    beforeBuild: [
      loadFonts(
        Object.keys(fonts).map((name) => `${base}generated/fonts/${name}`),
        { assets: false },
      ),
      // No fallback HTTP filesystem or runtime package/CDN downloads.
      withAccessModel({
        getMTime: () => undefined,
        isFile: () => false,
        getRealPath: (path) => path,
        readAll: () => undefined,
      }),
      withPackageRegistry({
        resolve: (spec) => {
          missingPackages.add(`@${spec.namespace}/${spec.name}:${spec.version}`);
          return undefined;
        },
      }),
    ],
  });
  compiler.addSource(
    "/version.typ",
    '#assert(sys.version == version(0, 15, 1), message: "Browser compiler must be Typst 0.15.1")',
  );
  const version = await compiler.compile({
    mainFilePath: "/version.typ",
    format: 1,
    diagnostics: "full",
  });
  if (!version.result)
    throw new Error("The browser compiler did not pass its Typst 0.15.1 runtime check.");
  globalThis.onmessage = async (event: MessageEvent<CompileRequest>) => {
    const request = event.data;
    try {
      missingPackages.clear();
      compiler.resetShadow();
      for (const [path, data] of Object.entries(request.files)) compiler.mapShadow(path, data);
      compiler.addSource("/data/notice.json", JSON.stringify(request.notice));
      const result = await compiler.compile({
        mainFilePath: `/${request.template}`,
        inputs: { data: "/data/notice.json" },
        format: 1,
        diagnostics: "full",
      });
      const diagnostics: Diagnostic[] = result.diagnostics ?? [];
      for (const name of missingPackages)
        diagnostics.push({
          path: request.template,
          range: "",
          severity: "error",
          message: `${name}: runtime package downloads are disabled. Vendor the dependency into this project and use a relative import.`,
        });
      send(
        { type: "result", revision: request.revision, pdf: result.result, diagnostics },
        result.result ? [result.result.buffer as ArrayBuffer] : [],
      );
    } catch (error) {
      send({
        type: "result",
        revision: request.revision,
        diagnostics: [
          { path: request.template, range: "", severity: "error", message: String(error) },
        ],
      });
    }
  };
  send({ type: "ready" });
} catch (error) {
  send({ type: "fatal", message: String(error) });
}
