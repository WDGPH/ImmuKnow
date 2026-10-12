import type { ExportRequest, ExportReply } from "./export-types";
import { ShadowFiles, validateSnapshot } from "./compiler-inputs";
import { verifyComponents } from "./component-resources";
import { validateNotice, validateSummary } from "./render-contract";
import { FontInputs, fontManifest } from "./font-resources";
import * as wrapper from "../vendor/compiler/typst_ts_web_compiler.js";
import wasmUrl from "../vendor/compiler/typst_ts_web_compiler_bg.wasm?url";
import type {
  BuildInfo,
  CheckResult,
  CompileRequest,
  CompileResult,
  Diagnostic,
  RenderSummary,
  PreviewPage,
  WorkerReply,
} from "./types";

// Both /src/ (Vite) and /assets/ (built site) sit one level below
// the app root. Use the running worker URL so Vite does not rewrite a
// directory-only import.meta.url asset reference into a filesystem URL.
const base = new URL("../", self.location.href);
const send = (reply: WorkerReply | ExportReply) => {
  const bytes =
    reply.type === "result"
      ? reply.preview?.artifact
      : reply.type === "export-result"
        ? reply.pdf
        : undefined;
  postMessage(reply, bytes ? { transfer: [bytes.buffer] } : {});
};
const encoder = new TextEncoder();
const missingPackages = new Set<string>();
const object = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);
const hex = (buffer: ArrayBuffer) =>
  Array.from(new Uint8Array(buffer), (byte) => byte.toString(16).padStart(2, "0")).join("");

async function asset(path: string): Promise<Response> {
  const response = await fetch(new URL(path, base));
  if (!response.ok) throw new Error(`Local compiler resource unavailable: ${path}`);
  return response;
}

async function fontResolver(fonts: Uint8Array[]): Promise<wrapper.TypstFontResolver> {
  const builder = new wrapper.TypstFontResolverBuilder();
  try {
    for (const bytes of fonts) {
      // The pinned add_raw_font silently accepts bytes with zero font faces.
      // Check its metadata API before replacing a usable resolver.
      const info: unknown = builder.get_font_info(bytes);
      if (!object(info) || !Array.isArray(info.info) || info.info.length === 0)
        throw new Error("Font bytes contain no supported font faces");
      builder.add_raw_font(bytes);
    }
  } catch (error) {
    builder.free();
    throw error;
  }
  // build() consumes the WASM builder; freeing it afterwards would double-free.
  return builder.build();
}

function summaryFromQuery(raw: string, notice: CompileRequest["notice"]): RenderSummary {
  const results: unknown = JSON.parse(raw);
  if (!Array.isArray(results) || results.length !== 1)
    throw new Error("Expected exactly one immuknow-report document summary");
  const summary: unknown = results[0];
  validateSummary(summary, notice);
  return summary;
}

function compilerChecks(diagnostics: Diagnostic[]): CheckResult[] {
  return diagnostics
    .filter((diagnostic) => diagnostic.severity === "warning")
    .map((diagnostic) => ({
      code: diagnostic.message.includes("unknown font family")
        ? "compiler.font_substitution"
        : diagnostic.message.includes("did not converge")
          ? "compiler.layout_nonconvergent"
          : "compiler.warning",
      stage: "render",
      status: "warn",
      message: diagnostic.message,
    }));
}

try {
  const build: BuildInfo = await (await asset("generated/build.json")).json();
  const defaultFonts = await Promise.all(
    Object.entries(fontManifest).map(async ([name, digest]) => {
      const bytes = await (await asset(`generated/fonts/${name}`)).arrayBuffer();
      if (hex(await crypto.subtle.digest("SHA-256", bytes)) !== digest)
        throw new Error(`Font checksum mismatch: ${name}`);
      return [name, new Uint8Array(bytes)] as const;
    }),
  );
  const wasm = await wrapper.default({ module_or_path: wasmUrl });
  const builder = new wrapper.TypstCompilerBuilder();
  try {
    await builder.set_access_model(
      {},
      () => 0,
      () => false,
      (path: string) => path,
      () => undefined,
    );
    await builder.set_package_registry(
      {},
      (spec: { namespace: string; name: string; version: string }) => {
        missingPackages.add(`@${spec.namespace}/${spec.name}:${spec.version}`);
        return undefined;
      },
    );
  } catch (error) {
    builder.free();
    throw error;
  }
  const compiler = await builder.build();
  const defaultResolver = await fontResolver(defaultFonts.map(([, bytes]) => bytes));
  compiler.set_fonts(defaultResolver);
  compiler.add_source("/compiler-version.typ", "#metadata(str(sys.version)) <compiler-version>");
  const versionWorld = compiler.snapshot("/", "/compiler-version.typ", []);
  let compilerVersion: string;
  try {
    const compiled = versionWorld.compile(0, 3);
    if (compiled.hasError) throw new Error("Browser compiler version check failed");
    [compilerVersion] = JSON.parse(versionWorld.query(0, "<compiler-version>", "value"));
    if (compilerVersion !== build.native_typst_version)
      throw new Error(
        `Browser compiler ${compilerVersion} differs from native ${build.native_typst_version}`,
      );
  } finally {
    versionWorld.free();
  }

  const shadows = new ShadowFiles(compiler);
  const bundledFonts = Object.fromEntries(
    defaultFonts.map(([name, bytes]) => [`/templates/fonts/${name}`, bytes]),
  );
  const fonts = new FontInputs(bundledFonts);

  globalThis.onmessage = async (event: MessageEvent<CompileRequest | ExportRequest>) => {
    const request = event.data;
    const exporting = "type" in request && request.type === "export";
    let pdf: Uint8Array | undefined;
    missingPackages.clear();
    const started = performance.now();
    const timing = {
      ...request.timing,
      received: performance.timeOrigin + started,
      mappedFiles: 0,
      mappedBytes: 0,
      fontRebuilds: 0,
    } as Record<string, number>;
    const reply: CompileResult = {
      type: "result",
      context: request.context,
      revision: request.revision,
      timing,
      checks: [],
      diagnostics: [],
    };
    try {
      if (!Number.isInteger(request.creationTimestamp) || request.creationTimestamp < 0)
        throw new Error("Creation timestamp must be nonnegative integer seconds");
      const filename = request.template.slice(request.template.lastIndexOf("/") + 1);
      const identity = filename.match(/^([A-Za-z0-9][A-Za-z0-9_-]*)\.(en|fr)\.typ$/);
      if (
        !request.template.startsWith("templates/") ||
        request.template.split("/").some((part) => part === "" || part === "." || part === "..") ||
        request.template.includes("\\") ||
        !identity ||
        identity[1] !== request.notice.version_id ||
        identity[2] !== request.notice.language
      )
        throw new Error("Notice filename identity differs from prepared facts");
      validateNotice(request.notice);
      validateSnapshot(request.files);
      await verifyComponents(request.files, build, "/");
      // The pinned wrapper plus our recorded cache patch ages VFS, source
      // history and Typst memoization without clearing current shadows.
      compiler.reset();
      const fontsStart = performance.now();
      fonts.validate(request.files);
      timing.fonts = performance.now() - fontsStart;
      const filesystemStart = performance.now();
      const desired = {
        ...request.files,
        ...bundledFonts,
        "/data/notice.json": encoder.encode(JSON.stringify(request.notice)),
      };
      Object.assign(timing, shadows.reconcile(request.context, desired));
      timing.filesystem = performance.now() - filesystemStart;
      timing.reconcile = performance.now() - started;
      // This pinned WASM's world clock reads Date.now(); no timestamp setter is exposed.
      const actualNow = Date.now;
      Date.now = () => request.creationTimestamp * 1000;
      try {
        const world = compiler.snapshot(
          "/",
          `/${request.template}`,
          Object.entries({
            data: "/data/notice.json",
            "notice-template": filename,
            "notice-version": request.notice.version_id,
            "notice-language": request.notice.language,
          }),
        );
        try {
          const compileStart = performance.now();
          const compiled = world.compile(0, 3);
          timing.compile = performance.now() - compileStart;
          reply.diagnostics = compiled.diagnostics ?? [];
          reply.checks.push(...compilerChecks(reply.diagnostics));
          if (compiled.hasError) throw new Error("Notice compilation failed");
          const artifactStart = performance.now();
          if (exporting) {
            world.set_pdf_opts({ creation_timestamp: request.creationTimestamp });
            pdf = world.get_artifact(1, 3).result;
            timing.pdf = performance.now() - artifactStart;
            if (!pdf?.length) throw new Error("Compiler did not produce a PDF");
          } else {
            const artifact: Uint8Array = world.get_artifact(0, 3).result;
            if (!artifact?.length) throw new Error("Compiler did not produce a preview");
            const info = JSON.parse(world.preview_info()) as { pages: PreviewPage[] };
            if (
              !info.pages.length ||
              info.pages.some(
                (page) =>
                  !Number.isFinite(page.width) ||
                  !Number.isFinite(page.height) ||
                  page.width <= 0 ||
                  page.height <= 0,
              )
            )
              throw new Error("Compiler returned invalid page geometry");
            reply.preview = { artifact, pages: info.pages };
            timing.artifact = performance.now() - artifactStart;
          }
          const evidenceStart = performance.now();
          try {
            const summary = summaryFromQuery(
              world.query(0, "<immuknow-report>", "value"),
              request.notice,
            );
            const pageCount =
              reply.preview?.pages.length ?? JSON.parse(world.preview_info()).pages.length;
            if (summary.page_count !== pageCount)
              throw new Error("Render evidence page count differs from the compiled notice");
            reply.summary = summary;
          } catch (error) {
            reply.checks.push({
              code: "render.evidence_failed",
              stage: "render",
              status: "fail",
              message: String(error),
            });
          }
          timing.evidence = performance.now() - evidenceStart;
        } finally {
          world.free();
        }
      } finally {
        Date.now = actualNow;
      }
    } catch (error) {
      reply.checks.push({
        code: "rendering.failed",
        stage: "render",
        status: "fail",
        message: String(error),
      });
      if (!reply.diagnostics.some((diagnostic) => diagnostic.severity === "error"))
        reply.diagnostics.push({
          path: request.template,
          severity: "error",
          range: "",
          message: String(error),
        });
    }
    // Cached Typst failures may not call the registry again. Recover the
    // rejected spec from the pinned diagnostic, without retaining old errors.
    for (const diagnostic of reply.diagnostics) {
      const spec = diagnostic.message.match(/package not found \(searched for (@[^)]+)\)/)?.[1];
      if (spec) missingPackages.add(spec);
    }
    for (const name of missingPackages)
      reply.diagnostics.push({
        path: request.template,
        severity: "error",
        range: "",
        message: `${name}: runtime package downloads are disabled. Vendor the dependency and use a relative import.`,
      });
    timing.wasmBytes = wasm.memory.buffer.byteLength;
    timing.worker = performance.now() - started;
    if (exporting) {
      send({
        type: "export-result",
        operationId: request.operationId,
        context: request.context,
        revision: request.revision,
        pdf,
        timing,
        error: pdf
          ? undefined
          : reply.diagnostics.map((item) => item.message).join("\n") || "PDF export failed",
      });
    } else send(reply);
  };
  send({ type: "ready", compilerVersion });
} catch (error) {
  send({ type: "fatal", message: String(error) });
}
