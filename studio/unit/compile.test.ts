import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { Compiler, type CompileInput } from "../src/compile";
import type { ExportReply, ExportRequest } from "../src/export-types";
import type { CompileRequest, WorkerReply } from "../src/types";

class WorkerMock {
  static all: WorkerMock[] = [];
  onmessage?: (event: { data: WorkerReply | ExportReply }) => void;
  onerror?: (event: { message?: string }) => void;
  jobs: (CompileRequest | ExportRequest)[] = [];
  terminate = vi.fn();
  constructor() {
    WorkerMock.all.push(this);
  }
  postMessage(job: CompileRequest | ExportRequest) {
    this.jobs.push(job);
  }
  ready() {
    this.onmessage?.({ data: { type: "ready", compilerVersion: "0.15.1" } });
  }
  finish(job = this.jobs.at(-1) as CompileRequest) {
    this.onmessage?.({
      data: {
        type: "result",
        context: job.context,
        revision: job.revision,
        checks: [],
        diagnostics: [],
        pdf: new Uint8Array([1]),
      },
    });
  }
  finishExport(job: ExportRequest, pdf?: Uint8Array, error?: string) {
    this.onmessage?.({
      data: {
        type: "export-result",
        operationId: job.operationId,
        context: job.context,
        revision: job.revision,
        pdf,
        error,
      },
    });
  }
}
const job = {
  template: "templates/test.en.typ",
  example: "short",
  files: {},
  notice: {},
  creationTimestamp: 0,
} as CompileInput;
beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("Worker", WorkerMock);
  WorkerMock.all = [];
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

test("readiness and completion obey burst deadlines, with one newest complete pending snapshot", () => {
  const replies = vi.fn(),
    compiler = new Compiler(vi.fn(), replies),
    worker = WorkerMock.all[0];
  compiler.submit(job);
  vi.advanceTimersByTime(20);
  worker.ready();
  expect(worker.jobs).toHaveLength(0);
  vi.advanceTimersByTime(55);
  expect(worker.jobs).toHaveLength(1);
  compiler.submit({ ...job, files: { a: new Uint8Array([2]) } });
  vi.advanceTimersByTime(30);
  compiler.submit({ ...job, files: { a: new Uint8Array([2]), b: new Uint8Array([3]) } });
  worker.finish();
  expect(replies).toHaveBeenCalledTimes(1);
  expect(worker.jobs).toHaveLength(1);
  vi.advanceTimersByTime(75);
  expect(worker.jobs).toHaveLength(2);
  expect(worker.jobs[1].files).toEqual({ a: new Uint8Array([2]), b: new Uint8Array([3]) });
  compiler.destroy();
});

test("continuous typing advances intermediate previews and cannot starve the worker", () => {
  const replies = vi.fn(),
    compiler = new Compiler(vi.fn(), replies),
    worker = WorkerMock.all[0];
  worker.ready();
  for (let i = 0; i < 30; i++) {
    compiler.submit(job);
    vi.advanceTimersByTime(25);
    if (worker.jobs.length > replies.mock.calls.length) worker.finish();
  }
  expect(worker.jobs.length).toBeGreaterThanOrEqual(4);
  expect(worker.jobs.length).toBeLessThanOrEqual(6);
  expect(WorkerMock.all).toHaveLength(1);
  compiler.destroy();
});

test("context switches, late duplicates and terminated workers cannot publish or release newer jobs", () => {
  const replies = vi.fn(),
    compiler = new Compiler(vi.fn(), replies),
    worker = WorkerMock.all[0];
  worker.ready();
  compiler.submit(job, true);
  const old = worker.jobs[0];
  compiler.invalidate();
  compiler.submit(job, true);
  worker.finish(old);
  expect(replies).not.toHaveBeenCalled();
  expect(worker.jobs).toHaveLength(2);
  worker.finish(old);
  expect(replies).not.toHaveBeenCalled();
  compiler.restart();
  compiler.submit(job, true);
  worker.finish();
  const restarted = WorkerMock.all[1];
  restarted.ready();
  restarted.finish();
  expect(replies).toHaveBeenCalledTimes(1);
  expect(worker.terminate).toHaveBeenCalledOnce();
  compiler.destroy();
});

test("timeouts stop the worker and explicit changes bypass the typing delay", () => {
  const status = vi.fn(),
    compiler = new Compiler(status, vi.fn()),
    worker = WorkerMock.all[0];
  worker.ready();
  compiler.submit(job, true);
  expect(worker.jobs).toHaveLength(1);
  vi.advanceTimersByTime(20000);
  expect(worker.terminate).toHaveBeenCalledOnce();
  expect(status).toHaveBeenLastCalledWith(expect.stringContaining("20 seconds"), true);
  compiler.destroy();
});

test.each([undefined, "", "Script failed"])("worker errors stop compilation with a useful message: %s", (message) => {
  const status = vi.fn(),
    compiler = new Compiler(status, vi.fn()),
    worker = WorkerMock.all[0];
  worker.onerror?.({ message });
  expect(status).toHaveBeenLastCalledWith(
    `Compiler worker failed${message ? `: ${message}` : ""}. Use Restart compiler.`,
    true,
  );
  expect(worker.terminate).toHaveBeenCalledOnce();
  compiler.destroy();
});

test("PDF export captures its input and identity, and never displaces the latest preview", async () => {
  const replies = vi.fn(),
    compiler = new Compiler(vi.fn(), replies),
    worker = WorkerMock.all[0];
  worker.ready();
  const files = { "notice.typ": new Uint8Array([1]) };
  const notice = { nested: { label: "first" } };
  const input = { ...job, files, notice } as CompileInput;
  const revision = compiler.submit(input, true);
  const exported = compiler.exportPdf(input, revision, compiler.context);
  files["notice.typ"][0] = 9;
  notice.nested.label = "changed";
  expect(worker.jobs).toHaveLength(1);
  worker.finish(worker.jobs[0] as CompileRequest);
  expect(replies).toHaveBeenCalledOnce();
  const request = worker.jobs[1] as ExportRequest;
  expect(request.type).toBe("export");
  expect(request.operationId).toBeGreaterThan(0);
  expect(request.files["notice.typ"]).toEqual(new Uint8Array([1]));
  expect((request.notice as unknown as typeof notice).nested.label).toBe("first");
  await expect(compiler.exportPdf(input, revision, compiler.context)).rejects.toThrow(
    "already in progress",
  );
  worker.finishExport({ ...request, operationId: request.operationId + 1 }, new Uint8Array([5]));
  expect(worker.jobs).toHaveLength(2);
  const pdf = new Uint8Array([4, 2]);
  worker.finishExport(request, pdf);
  await expect(exported).resolves.toMatchObject({
    operationId: request.operationId,
    context: request.context,
    revision,
    pdf,
  });
  compiler.submit({ ...job, files: { next: new Uint8Array([3]) } }, true);
  expect(worker.jobs).toHaveLength(3);
  expect(worker.jobs[2].files).toEqual({ next: new Uint8Array([3]) });
  compiler.destroy();
});

test("edits and context changes reject obsolete exports without dropping preview work", async () => {
  const replies = vi.fn(),
    compiler = new Compiler(vi.fn(), replies),
    worker = WorkerMock.all[0];
  worker.ready();
  const first = compiler.submit(job, true);
  const queued = compiler.exportPdf(job, first, compiler.context);
  compiler.submit({ ...job, files: { newer: new Uint8Array([2]) } }, true);
  await expect(queued).rejects.toThrow("notice changed");
  worker.finish(worker.jobs[0] as CompileRequest);
  expect(worker.jobs).toHaveLength(2);
  expect(worker.jobs[1]).not.toHaveProperty("type", "export");
  worker.finish(worker.jobs[1] as CompileRequest);
  expect(replies).toHaveBeenCalledTimes(2);

  const current = compiler.exportPdf(job, compiler.revision, compiler.context);
  const active = worker.jobs[2] as ExportRequest;
  compiler.invalidate();
  await expect(current).rejects.toThrow("notice changed");
  compiler.submit(job, true);
  worker.finishExport(active, new Uint8Array([1]));
  expect(worker.jobs).toHaveLength(4);
  worker.finish(worker.jobs[3] as CompileRequest);
  expect(replies).toHaveBeenCalledTimes(3);
  compiler.destroy();
});

test("PDF export errors and timeouts reject the download and keep successful previews", async () => {
  const replies = vi.fn(),
    status = vi.fn(),
    compiler = new Compiler(status, replies),
    worker = WorkerMock.all[0];
  worker.ready();
  const revision = compiler.submit(job, true);
  worker.finish(worker.jobs[0] as CompileRequest);
  const failed = compiler.exportPdf(job, revision, compiler.context);
  worker.finishExport(worker.jobs[1] as ExportRequest, undefined, "PDF generation failed");
  await expect(failed).rejects.toThrow("PDF generation failed");
  expect(replies).toHaveBeenCalledOnce();
  const timedOut = compiler.exportPdf(job, revision, compiler.context);
  vi.advanceTimersByTime(20_000);
  await expect(timedOut).rejects.toThrow("20 seconds");
  expect(worker.terminate).toHaveBeenCalledOnce();
  expect(replies).toHaveBeenCalledOnce();
  compiler.destroy();
});

test("restart rejects an active export and permits a fresh export on the new worker", async () => {
  const compiler = new Compiler(vi.fn(), vi.fn());
  const oldWorker = WorkerMock.all[0];
  oldWorker.ready();
  const firstRevision = compiler.submit(job, true);
  oldWorker.finish(oldWorker.jobs[0] as CompileRequest);
  const obsolete = compiler.exportPdf(job, firstRevision, compiler.context);
  compiler.restart();
  await expect(obsolete).rejects.toThrow("notice changed");
  oldWorker.finishExport(oldWorker.jobs[1] as ExportRequest, new Uint8Array([1]));
  const newWorker = WorkerMock.all[1];
  newWorker.ready();
  const currentRevision = compiler.submit(job, true);
  newWorker.finish(newWorker.jobs[0] as CompileRequest);
  const current = compiler.exportPdf(job, currentRevision, compiler.context);
  newWorker.finishExport(newWorker.jobs[1] as ExportRequest, new Uint8Array([2]));
  await expect(current).resolves.toMatchObject({ pdf: new Uint8Array([2]) });
  compiler.destroy();
});
