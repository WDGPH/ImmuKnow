export type Files = Record<string, Uint8Array>;
export type Notice = {
  client_id: string;
  version_id: string;
  language: string;
  client_data: { name: string };
  [key: string]: unknown;
};
export interface Example {
  id: string;
  label: string;
  description: string;
  payloads: Record<string, Notice>;
}
export interface Bundle {
  schemaVersion: number;
  synthetic: boolean;
  examples: Example[];
  files: Record<string, string>;
  hashes: Record<string, string>;
  compilerVersion: string;
  packageVersion: string;
}
export interface Diagnostic {
  path: string;
  severity: string;
  range: string;
  message: string;
  package?: string;
}
export interface CompileRequest {
  revision: number;
  template: string;
  example: string;
  files: Files;
  notice: Notice;
}
export type WorkerReply =
  | { type: "ready" }
  | { type: "fatal"; message: string }
  | { type: "result"; revision: number; pdf?: Uint8Array; diagnostics: Diagnostic[] };
