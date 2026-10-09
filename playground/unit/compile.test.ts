import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { Compiler } from "../src/compile";
import type { CompileRequest, WorkerReply } from "../src/types";

class FakeWorker {
  static instances: FakeWorker[] = [];
  onmessage?: (event: { data: WorkerReply }) => void;
  onerror?: (event: { message: string }) => void;
  sent: CompileRequest[] = [];
  terminated = false;
  constructor() {
    FakeWorker.instances.push(this);
  }
  postMessage(request: CompileRequest) {
    this.sent.push(request);
  }
  terminate() {
    this.terminated = true;
  }
  reply(data: WorkerReply) {
    this.onmessage?.({ data });
  }
}
const job = {
  template: "templates/a.en.typ",
  example: "short",
  files: {},
  notice: {
    client_id: "0000000001",
    version_id: "a",
    language: "en",
    client_data: { name: "Synthetic" },
  },
};
beforeEach(() => {
  vi.useFakeTimers();
  FakeWorker.instances = [];
  vi.stubGlobal("Worker", FakeWorker);
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
it("coalesces edits and drops a late result for an older client", () => {
  const result = vi.fn();
  const compiler = new Compiler(vi.fn(), result);
  const worker = FakeWorker.instances[0];
  worker.reply({ type: "ready" });
  compiler.submit(job);
  vi.advanceTimersByTime(250);
  compiler.submit({ ...job, example: "second" });
  compiler.submit({ ...job, example: "third" });
  vi.advanceTimersByTime(250);
  expect(worker.sent).toHaveLength(1);
  worker.reply({ type: "result", revision: 1, diagnostics: [], pdf: new Uint8Array([1]) });
  expect(result).not.toHaveBeenCalled();
  expect(worker.sent).toHaveLength(2);
  expect(worker.sent[1].example).toBe("third");
  worker.reply({ type: "result", revision: 3, diagnostics: [], pdf: new Uint8Array([3]) });
  expect(result).toHaveBeenCalledOnce();
  compiler.destroy();
});
it("invalidating an incompatible template cannot accept the previous output", () => {
  const result = vi.fn();
  const compiler = new Compiler(vi.fn(), result);
  const worker = FakeWorker.instances[0];
  worker.reply({ type: "ready" });
  compiler.submit(job);
  vi.advanceTimersByTime(250);
  compiler.invalidate();
  worker.reply({ type: "result", revision: 1, diagnostics: [], pdf: new Uint8Array([1]) });
  expect(result).not.toHaveBeenCalled();
  compiler.destroy();
});
it("terminates a stuck compiler and supports a fresh worker", () => {
  const status = vi.fn();
  const compiler = new Compiler(status, vi.fn());
  const worker = FakeWorker.instances[0];
  worker.reply({ type: "ready" });
  compiler.submit(job);
  vi.advanceTimersByTime(20_250);
  expect(worker.terminated).toBe(true);
  expect(status).toHaveBeenLastCalledWith(expect.stringContaining("exceeded 20 seconds"));
  compiler.restart();
  compiler.submit(job);
  const next = FakeWorker.instances[1];
  next.reply({ type: "ready" });
  expect(next.sent).toHaveLength(1);
  compiler.destroy();
});
