import type { CompileRequest, WorkerReply } from "./types";
import type { ExportReply, ExportRequest, ExportResult } from "./export-types";

export type CompileInput = Omit<CompileRequest, "revision" | "context" | "timing">;
type ExportTask = {
  request: ExportRequest;
  resolve: (result: ExportResult) => void;
  reject: (error: Error) => void;
  settled: boolean;
};
// A quiet burst waits 75 ms; continuous typing gets a snapshot at least every
// 150 ms when the worker is available. Completion/readiness obey the same deadline.
export class Compiler {
  revision = 0;
  context = 0;
  compilerVersion?: string;
  private worker?: Worker;
  private ready = false;
  private active?: CompileRequest | ExportRequest;
  private pending?: CompileRequest;
  private exportTask?: ExportTask;
  private nextOperationId = 0;
  private timer?: ReturnType<typeof setTimeout>;
  private debounce?: ReturnType<typeof setTimeout>;
  private burstStart = 0;
  private due = 0;
  constructor(
    private status: (message: string, blocking?: boolean) => void,
    private result: (reply: Extract<WorkerReply, { type: "result" }>) => void,
  ) {
    this.start();
  }
  private start() {
    const worker = new Worker(new URL("./compile.worker.ts", import.meta.url), { type: "module" });
    this.worker = worker;
    this.compilerVersion = undefined;
    this.ready = false;
    this.active = undefined;
    this.status("Loading compiler and fonts…");
    this.timer = setTimeout(
      () => this.fail("Compiler loading timed out. Use Restart compiler to retry."),
      45_000,
    );
    worker.onmessage = (event: MessageEvent<WorkerReply | ExportReply>) => {
      if (this.worker !== worker) return;
      const reply = event.data;
      if (reply.type === "ready") {
        if (this.ready) return;
        clearTimeout(this.timer);
        this.compilerVersion = reply.compilerVersion;
        this.ready = true;
        this.flush();
      } else if (reply.type === "fatal") this.fail(reply.message);
      else {
        const active = this.active;
        if (!active || reply.revision !== active.revision || reply.context !== active.context)
          return;
        if (reply.type === "export-result") {
          if (!("operationId" in active) || reply.operationId !== active.operationId) return;
          clearTimeout(this.timer);
          this.active = undefined;
          const task = this.exportTask;
          this.exportTask = undefined;
          if (task && !task.settled) {
            if (reply.context !== this.context || reply.revision !== this.revision)
              task.reject(new Error("The notice changed before its PDF was ready. Download again."));
            else if (reply.error || !reply.pdf)
              task.reject(new Error(reply.error || "The PDF export did not return a file."));
            else
              task.resolve({
                operationId: reply.operationId,
                context: reply.context,
                revision: reply.revision,
                timing: reply.timing,
                pdf: reply.pdf,
              });
          }
          this.flush();
          return;
        }
        if ("operationId" in active) return;
        clearTimeout(this.timer);
        this.active = undefined;
        // Same-document successes may advance the preview during continuous
        // typing. The UI decides freshness independently of display eligibility.
        if (reply.context === this.context) this.result(reply);
        this.flush();
      }
    };
    worker.onerror = (event) => {
      if (this.worker === worker) {
        const detail = event.message ? `: ${event.message}` : "";
        this.fail(`Compiler worker failed${detail}. Use Restart compiler.`);
      }
    };
  }
  submit(job: CompileInput, immediate = false): number {
    if (!this.worker) throw new Error("Compiler is stopped. Use Restart compiler to retry.");
    const now = performance.now();
    if (!this.pending) this.burstStart = now;
    this.pending = {
      ...job,
      context: this.context,
      revision: ++this.revision,
      timing: { requested: performance.timeOrigin + now },
    };
    this.rejectStaleExport();
    this.due = immediate ? now : Math.min(now + 75, this.burstStart + 150);
    this.status("Updating…");
    this.flush();
    return this.revision;
  }
  exportPdf(job: CompileInput, revision: number, context: number): Promise<ExportResult> {
    if (!this.worker) return Promise.reject(new Error("Compiler is stopped. Restart it to export."));
    if (this.exportTask) return Promise.reject(new Error("A PDF export is already in progress."));
    if (context !== this.context || revision !== this.revision)
      return Promise.reject(new Error("The notice changed. Wait for the current preview and download again."));
    const request: ExportRequest = {
      ...structuredClone(job),
      type: "export",
      operationId: ++this.nextOperationId,
      context,
      revision,
      timing: { requested: performance.timeOrigin + performance.now() },
    };
    return new Promise((resolve, reject) => {
      this.exportTask = { request, resolve, reject, settled: false };
      this.flush();
    });
  }
  private rejectStaleExport() {
    const task = this.exportTask;
    if (!task || task.settled) return;
    if (task.request.context === this.context && task.request.revision === this.revision) return;
    task.settled = true;
    task.reject(new Error("The notice changed before its PDF was ready. Download again."));
    if (this.active !== task.request) this.exportTask = undefined;
  }
  private flush() {
    clearTimeout(this.debounce);
    if (!this.worker) return;
    if (!this.ready || this.active) return;
    if (this.exportTask && !this.exportTask.settled) {
      const task = this.exportTask;
      this.active = task.request;
      this.status("Exporting PDF…");
      this.timer = setTimeout(
        () => this.fail("PDF export exceeded 20 seconds. Restart the compiler to retry."),
        20_000,
      );
      if (task.request.timing)
        task.request.timing.sent = performance.timeOrigin + performance.now();
      this.worker.postMessage(task.request);
      return;
    }
    if (!this.pending) return;
    const delay = this.due - performance.now();
    if (delay > 0) {
      this.debounce = setTimeout(() => this.flush(), delay);
      return;
    }
    const job = this.pending;
    this.pending = undefined;
    this.active = job;
    this.status("Compiling…");
    this.timer = setTimeout(
      () =>
        this.fail(
          "Compilation exceeded 20 seconds. The worker was stopped. Edit the source and restart.",
        ),
      20_000,
    );
    if (job.timing) job.timing.sent = performance.timeOrigin + performance.now();
    this.worker.postMessage(job);
  }
  private fail(message: string) {
    clearTimeout(this.timer);
    clearTimeout(this.debounce);
    this.worker?.terminate();
    this.worker = undefined;
    this.ready = false;
    this.active = undefined;
    this.exportTask?.reject(new Error(message));
    this.exportTask = undefined;
    this.status(message, true);
  }
  invalidate() {
    this.context++;
    this.revision++;
    this.pending = undefined;
    this.rejectStaleExport();
    clearTimeout(this.debounce);
  }
  restart() {
    this.invalidate();
    clearTimeout(this.timer);
    this.worker?.terminate();
    this.exportTask = undefined;
    this.start();
  }
  destroy() {
    this.invalidate();
    clearTimeout(this.timer);
    this.worker?.terminate();
    this.exportTask = undefined;
    this.worker = undefined;
  }
}
