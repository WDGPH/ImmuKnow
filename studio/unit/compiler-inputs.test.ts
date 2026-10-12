import { expect, test, vi } from "vitest";
import { sameBytes, ShadowFiles } from "../src/compiler-inputs";
const bytes = (s: string) => new TextEncoder().encode(s);

test("authoritative snapshots reconcile additions, replacement and deletion, including skipped edits", () => {
  const compiler = {
    reset_shadow: vi.fn(),
    map_shadow: vi.fn(() => true),
    unmap_shadow: vi.fn(() => true),
  };
  const files = new ShadowFiles(compiler);
  expect(files.reconcile(1, { "/a": bytes("a"), "/b": bytes("b") })).toMatchObject({
    mappedFiles: 2,
  });
  expect(files.reconcile(1, { "/a": bytes("a"), "/b": bytes("b") })).toMatchObject({
    mappedFiles: 0,
  });
  expect(
    files.reconcile(1, { "/a": bytes("changed while busy"), "/c": bytes("latest edit") }),
  ).toMatchObject({ mappedFiles: 2, removedFiles: 1 });
  expect(compiler.unmap_shadow).toHaveBeenCalledWith("/b");
  expect(files.reconcile(2, { "/a": bytes("changed while busy") })).toMatchObject({
    mappedFiles: 1,
  });
  expect(compiler.reset_shadow).toHaveBeenCalledTimes(2);
  compiler.map_shadow.mockReturnValueOnce(false);
  expect(() => files.reconcile(2, { "/a": bytes("failure") })).toThrow("Could not map");
  expect(files.reconcile(2, { "/a": bytes("recover") })).toMatchObject({ mappedFiles: 1 });
});

test("byte reconciliation detects changed tails and handles unaligned imported views", () => {
  const a = new Uint8Array([0, 1, 2, 3, 4, 5, 6]);
  expect(sameBytes(a, a.slice())).toBe(true);
  expect(sameBytes(a, new Uint8Array([0, 1, 2, 3, 4, 5, 7]))).toBe(false);
  expect(sameBytes(a.subarray(1), a.slice(1))).toBe(true);
  expect(sameBytes(a.subarray(1), new Uint8Array([1, 2, 3, 4, 5, 7]))).toBe(false);
});
