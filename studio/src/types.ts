export type Files = Record<string, Uint8Array>;
export type CheckStatus = "pass" | "warn" | "fail" | "not_applicable" | "not_run";
export interface CheckResult {
  code: string;
  stage: string;
  status: CheckStatus;
  message: string;
  component?: string;
  page?: number;
  measurements?: Record<string, unknown>;
}
export interface Notice {
  schema_version: 1;
  row_key: string;
  template: string;
  client_id: string;
  version_id: string;
  language: "en" | "fr";
  client_data: { name: string; [key: string]: unknown };
  [key: string]: unknown;
}
export interface RenderSummary {
  notice: Notice;
  schema_version: 2;
  identity: {
    row_key: string;
    template: string;
    client_id: string;
    version_id: string;
    language: string;
  };
  page_count: number;
  components: Record<string, boolean>;
  checks: CheckResult[];
  qr_urls: string[];
  measurements: Record<string, Record<string, unknown>[]>;
}
export interface BuildInfo {
  application_version: string;
  rendering_schema_version: number;
  native_typst_version: string;
  browser_compiler: {
    crate_version: string;
    source_revision: string;
    rust_version: string;
    wasm_bindgen_version: string;
    features: string[];
    cache_patch_sha256: string;
    preview_patch_sha256: string;
  };
  browser_renderer: {
    crate_version: string;
    source_revision: string;
    rust_version: string;
    wasm_bindgen_version: string;
    features: string[];
    canvas_patch_sha256: string;
  };
  compiler_build_sha256: string;
  shared_resources: { sha256: string; files: { path: string; sha256: string }[] };
  source_revision: string | null;
  source_modified: boolean | null;
}
export interface Example {
  id: string;
  label: string;
  description: string;
  payloads: Record<string, Notice>;
  preparationChecks: Record<string, CheckResult[]>;
  inputs: Record<string, { csv: string; assignments: string }>;
}
export interface Bundle {
  schemaVersion: 1;
  synthetic: true;
  creationTimestamp: number;
  build: BuildInfo;
  examples: Example[];
  files: Record<string, string>;
  hashes: Record<string, string>;
}
export interface Diagnostic {
  path: string;
  severity: string;
  range: string;
  message: string;
  package?: string;
}
export interface CompileRequest {
  context: number;
  revision: number;
  timing?: Record<string, number>;
  template: string;
  example: string;
  files: Files;
  notice: Notice;
  creationTimestamp: number;
}
export interface PreviewText {
  text: string;
  x: number;
  y: number;
  width: number;
  height: number;
}
export interface PreviewPage {
  width: number;
  height: number;
  text: PreviewText[];
  plainText: string;
}
export interface Preview {
  artifact: Uint8Array;
  pages: PreviewPage[];
}
export type CompileResult = {
  type: "result";
  context: number;
  revision: number;
  timing?: Record<string, number>;
  preview?: Preview;
  summary?: RenderSummary;
  checks: CheckResult[];
  diagnostics: Diagnostic[];
};
export type WorkerReply =
  | { type: "ready"; compilerVersion: string }
  | { type: "fatal"; message: string }
  | CompileResult;
