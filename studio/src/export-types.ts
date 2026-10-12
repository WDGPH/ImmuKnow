import type { CompileRequest } from "./types";

export type ExportRequest = CompileRequest & {
  type: "export";
  operationId: number;
};

export type ExportReply = {
  type: "export-result";
  operationId: number;
  context: number;
  revision: number;
  timing?: Record<string, number>;
  pdf?: Uint8Array;
  error?: string;
};

export type ExportResult = {
  operationId: number;
  context: number;
  revision: number;
  timing?: Record<string, number>;
  pdf: Uint8Array;
};
