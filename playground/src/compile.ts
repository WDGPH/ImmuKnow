import type { CompileRequest, WorkerReply } from "./types";

export class Compiler {
  revision = 0;
  private worker?: Worker;
  private ready = false;
  private busy = false;
  private pending?: CompileRequest;
  private timer?: ReturnType<typeof setTimeout>;
  private debounce?: ReturnType<typeof setTimeout>;
  constructor(
    private status: (message: string) => void,
    private result: (reply: Extract<WorkerReply, { type: "result" }>) => void,
  ) {
    this.start();
  }
  private start() {
    const worker = new Worker(new URL("./compile.worker.ts", import.meta.url), { type: "module" });
    this.worker = worker;
    this.ready = false;
    this.busy = false;
    this.status("Loading pinned compiler and fonts…");
    this.timer = setTimeout(
      () => this.fail("Compiler loading timed out. Use Restart compiler to retry."),
      45_000,
    );
    worker.onmessage = (event: MessageEvent<WorkerReply>) => {
      if (this.worker !== worker) return;
      const reply = event.data;
      clearTimeout(this.timer);
      if (reply.type === "ready") {
        this.ready = true;
        this.flush();
      } else if (reply.type === "fatal") this.fail(reply.message);
      else {
        this.busy = false;
        if (reply.revision === this.revision) this.result(reply);
        this.flush();
      }
    };
    worker.onerror = (event) => {
      if (this.worker === worker)
        this.fail(`Compiler worker failed: ${event.message}. Use Restart compiler.`);
    };
  }
  submit(job: Omit<CompileRequest, "revision">): number {
    this.pending = { ...job, revision: ++this.revision };
    clearTimeout(this.debounce);
    this.status(this.busy ? "Waiting for the latest edit…" : "Queued…");
    this.debounce = setTimeout(() => this.flush(), 250);
    return this.revision;
  }
  private flush() {
    if (!this.ready || this.busy || !this.pending || !this.worker) return;
    const job = this.pending;
    this.pending = undefined;
    this.busy = true;
    this.status("Compiling…");
    this.timer = setTimeout(
      () =>
        this.fail(
          "Compilation exceeded 20 seconds. The worker was stopped. Edit the source and restart.",
        ),
      20_000,
    );
    this.worker.postMessage(job);
  }
  private fail(message: string) {
    clearTimeout(this.timer);
    this.worker?.terminate();
    this.worker = undefined;
    this.ready = false;
    this.busy = false;
    this.status(message);
  }
  invalidate() {
    this.revision++;
    this.pending = undefined;
    clearTimeout(this.debounce);
  }
  restart() {
    clearTimeout(this.timer);
    this.worker?.terminate();
    this.start();
  }
  destroy() {
    clearTimeout(this.timer);
    clearTimeout(this.debounce);
    this.worker?.terminate();
  }
}
