import { expect, test } from "vitest";
import { sourceLocation } from "../src/source-location";
import type { Files } from "../src/types";

const template = "templates/notice.en.typ";
const files = (sources: Record<string, string>): Files =>
  Object.fromEntries(
    Object.entries(sources).map(([path, source]) => [path, new TextEncoder().encode(source)]),
  );

test("navigates a unique source match with its original text offsets", () => {
  const source = "#let title = [Unique marker]";
  expect(sourceLocation(files({ [template]: source }), template, "Unique marker")).toEqual({
    path: template,
    from: source.indexOf("Unique"),
    to: source.indexOf("marker") + "marker".length,
  });
});

test("refuses repeated matches within a file even when another file has one match", () => {
  expect(
    sourceLocation(
      files({
        [template]: "[Repeated marker] [Repeated marker]",
        "templates/other.en.typ": "[Repeated marker]",
      }),
      template,
      "Repeated marker",
    ),
  ).toBeUndefined();
});

test("refuses matches in multiple candidate files", () => {
  expect(
    sourceLocation(
      files({
        [template]: "[Shared marker]",
        "templates/other.en.typ": "[Shared marker]",
      }),
      template,
      "Shared marker",
    ),
  ).toBeUndefined();
});

test("ignores comments when deciding whether a source match is unique", () => {
  const source = "// Unique marker\n[Unique marker] /* Unique marker */";
  expect(sourceLocation(files({ [template]: source }), template, "Unique marker")).toEqual({
    path: template,
    from: source.indexOf("Unique", source.indexOf("\n")),
    to: source.indexOf("marker", source.indexOf("\n")) + "marker".length,
  });
});
