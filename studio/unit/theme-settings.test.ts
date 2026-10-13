import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
import { decoder, encoder } from "../src/project";
import { settingValue, updateQRStyle, updateThemeSettings } from "../src/theme-settings";

const bytes = (source: string) => encoder.encode(source);

test("reads and edits the active value while preserving nested comments, BOM and CRLF", () => {
  const source =
    '\ufeff/*\r\n#let body-font = "Commented"\r\n/* nested */\r\n*/\r\n' +
    '// #let body-font = "Also commented"\r\n' +
    '#let body-font = "FreeSerif" /* Keep this explanation */ // And this one\r\n';
  expect(settingValue(bytes(source), "body-font")).toBe('"FreeSerif"');
  expect(updateThemeSettings(bytes(source), { "body-font": '"FreeSans"' })).toEqual(
    bytes(source.replace('= "FreeSerif"', '= "FreeSans"')),
  );
});

test("quoted comment marks and escaped quotes remain part of the value", () => {
  const value = JSON.stringify('Dr. "Annie" // /* Name */');
  const source = `#let signature-name = ${value} // Keep\n#let records-url = "https://example.org/a//b"\n`;
  expect(settingValue(bytes(source), "signature-name")).toBe(value);
  expect(settingValue(bytes(source), "records-url")).toBe('"https://example.org/a//b"');
  expect(
    decoder.decode(updateThemeSettings(bytes(source), { "signature-name": '"Dr. Next"' })),
  ).toBe(source.replace(value, '"Dr. Next"'));
});

test("nested declarations do not replace the top-level setting", () => {
  const source = '#let sample = [\n#let body-font = "Nested"\n]\n#let body-font = "FreeSans"\n';
  expect(settingValue(bytes(source), "body-font")).toBe('"FreeSans"');
  expect(decoder.decode(updateThemeSettings(bytes(source), { "body-font": '"FreeSerif"' }))).toBe(
    source.replace('= "FreeSans"', '= "FreeSerif"'),
  );
});

test("ambiguous, calculated, multiline and incomplete values require source editing", () => {
  for (const source of [
    '#let body-font = "One"\n#let body-font = "Two"\n',
    '#let body-font = if true { "One" } else { "Two" }\n',
    "#let body-font = font-name\n",
    '#let body-font = (\n "FreeSans"\n)\n',
    '#let body-font = "One" + "Two"\n',
    '#let body-font = "FreeSans\n',
    '/*\n#let body-font = "FreeSans"\n',
    '```typ\n#let body-font = "Raw example"\n```\n#let body-font = "FreeSans"\n',
    '#let body-font = "FreeSans"; #let other = true\n',
  ]) {
    const original = bytes(source);
    expect(settingValue(original, "body-font"), source).toBeUndefined();
    expect(() => updateThemeSettings(original, { "body-font": '"FreeSerif"' }), source).toThrow(
      "Edit body-font in Settings",
    );
    expect(original).toEqual(bytes(source));
  }
});

test("comments inside a value are retained by refusing an automatic replacement", () => {
  const original = bytes('#let link-color = rgb(/* brand */ "#112233")\n');
  expect(settingValue(original, "link-color")).toBeUndefined();
  expect(() => updateThemeSettings(original, { "link-color": 'rgb("#445566")' })).toThrow(
    "Edit link-color in Settings",
  );
});

test("QR changes ignore commented examples and nested dictionary fields", () => {
  const source =
    '\ufeff/*\r\n#let qr = (\r\n  module-shape: "commented",\r\n  corner-style: "commented",\r\n)\r\n*/\r\n' +
    "#let qr = (\r\n" +
    '  url: notice => link("https://example.org", (\r\n    module-shape: "nested",\r\n  )),\r\n' +
    '  /* module-shape: "ignored", */\r\n' +
    '  module-shape: "square", /* Keep this */\r\n' +
    '  corner-style: "square", // Keep too\r\n)\r\n';
  expect(updateQRStyle(bytes(source), "dots")).toEqual(
    bytes(
      source
        .replace('module-shape: "square"', 'module-shape: "dots"')
        .replace('corner-style: "square"', 'corner-style: "rounded"'),
    ),
  );
});

test("QR overrides, repeated fields and computed style values are left to source editing", () => {
  const qr = '#let qr = (\n  module-shape: "square",\n  corner-style: "square",\n)\n';
  for (const source of [
    qr + qr,
    qr.replace("  corner-style:", '  module-shape: "duplicate",\n  corner-style:'),
    qr.replace('"square",', 'if true { "square" } else { "dots" },'),
    qr.replace("\n)", "\n  ..other,\n)"),
    qr.replace("\n)", "\n  enabled: true, ..other,\n)"),
    qr.replace("#let qr = (", "#let qr = style.with("),
  ])
    expect(() => updateQRStyle(bytes(source), "dots")).toThrow("in Settings");
});

test("maintained Settings keep every byte outside the requested values", () => {
  const original = readFileSync(new URL("../../immuknow/templates/settings.typ", import.meta.url));
  const source = decoder.decode(original);
  const changes = {
    "body-font": '"FreeSerif"',
    "signature-name": '"Dr. Example"',
    "link-color": 'rgb("#123456")',
    logo: 'image("assets/edited.png", width: logo-width)',
  };
  let expected = source;
  for (const [name, value] of Object.entries(changes)) {
    const previous = settingValue(original, name);
    expect(previous, name).toBeDefined();
    expected = expected.replace(`#let ${name} = ${previous}`, `#let ${name} = ${value}`);
  }
  expect(updateThemeSettings(original, changes)).toEqual(bytes(expected));
  expect(decoder.decode(updateQRStyle(original, "dots"))).toBe(
    source
      .replace('module-shape: "square"', 'module-shape: "dots"')
      .replace('corner-style: "square"', 'corner-style: "rounded"'),
  );
});

test("image paths requiring escapes or calculations stay in source editing", () => {
  for (const value of [
    'image("a\\"b.png", width: 1cm)',
    "image(path, width: 1cm)",
    'image("assets/" + "logo.png", width: 1cm)',
    'image("assets/logo.png",\n width: 1cm)',
  ]) {
    const original = bytes(`#let logo = ${value}\n`);
    expect(settingValue(original, "logo")).toBeUndefined();
    expect(() => updateThemeSettings(original, { logo: 'image("new.png")' })).toThrow(
      "Edit logo in Settings",
    );
  }
});

test("calculated colours are not rewritten by a theme change", () => {
  const source = bytes('#let accent-color = rgb("#" + colour-code)\n');
  expect(settingValue(source, "accent-color")).toBeUndefined();
  expect(() => updateThemeSettings(source, { "accent-color": 'rgb("#001122")' })).toThrow(
    "Edit accent-color in Settings",
  );
});
