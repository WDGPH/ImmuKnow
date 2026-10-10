import { describe, expect, it } from "vitest";
import { inlineTemplate, typstLiteral } from "../src/inline-template";
import { decoder, encoder } from "../src/project";

const path = "templates/test.typ";
const source =
  '// @immuknow-settings: settings/test.typ\n#import "settings/test.typ": body-size\n#let layout = ik.project-layout(json("layout-settings.json"), "test", window: envelope-window)\nHello';
const files = {
  [path]: encoder.encode(source),
  "templates/settings/test.typ": encoder.encode("#let body-size = 12pt\n"),
  "templates/layout-settings.json": encoder.encode('{"notices":{"test":{"paper":"us-legal"}}}'),
};
describe("source download settings", () => {
  it("inlines both settings without changing the editable project", () => {
    const output = decoder.decode(inlineTemplate(files, path));
    expect(output).toContain("#let body-size = 12pt");
    expect(output).toContain('"paper": "us-legal"');
    expect(output).not.toContain('json("layout-settings.json")');
    expect(output).not.toContain('#import "settings/');
    expect(decoder.decode(files[path])).toBe(source);
  });
  it("preserves older custom source", () => {
    const bytes = encoder.encode("Hello");
    expect(inlineTemplate({ [path]: bytes }, path)).toBe(bytes);
  });
  it("rejects missing, ambiguous and unsafe settings imports", () => {
    for (const changed of [
      `${source}\n${source}`,
      source.replace("settings/test.typ", "../test.typ"),
      source.replace(": body-size", ": missing"),
    ])
      expect(() => inlineTemplate({ ...files, [path]: encoder.encode(changed) }, path)).toThrow();
    expect(() => inlineTemplate({ [path]: files[path] }, path)).toThrow();
  });
  it("quotes source-like strings and handles empty collections", () => {
    expect(typstLiteral('"\\\n#panic("x")')).toBe('"\\"\\\\\\u{a}#panic(\\"x\\")"');
    expect(typstLiteral({})).toBe("(:)");
    expect(typstLiteral([])).toBe("()");
    expect(typstLiteral([false, null, 1])).toBe("(false,none,1,)");
    expect(() => typstLiteral(Number.NaN)).toThrow();
  });
});
