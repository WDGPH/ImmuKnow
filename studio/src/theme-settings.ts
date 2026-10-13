import { decoder, encoder } from "./project";

type Range = { from: number; to: number };
interface SettingsSource {
  source: string;
  code: string;
  comments: Range[];
  pairs: Map<number, number>;
  lineDepth: Map<number, number>;
}

// Locate supported top-level settings, retaining offsets into the authored
// source so replacements preserve surrounding text.
// Raw text, math, escapes outside strings and incomplete groups need source editing.
function settingsSource(source: string): SettingsSource | undefined {
  const code = source.split("");
  const comments: Range[] = [];
  const hide = (from: number, to: number) => {
    for (let i = from; i < to; i++) if (!/[\r\n]/.test(code[i])) code[i] = " ";
  };
  for (let i = 0; i < source.length; ) {
    const start = i;
    if (source.startsWith("//", i)) {
      while (i < source.length && !/[\r\n]/.test(source[i])) i++;
      comments.push({ from: start, to: i });
      hide(start, i);
    } else if (source.startsWith("/*", i)) {
      let depth = 1;
      i += 2;
      while (i < source.length && depth) {
        if (source.startsWith("/*", i)) {
          depth++;
          i += 2;
        } else if (source.startsWith("*/", i)) {
          depth--;
          i += 2;
        } else i++;
      }
      if (depth) return;
      comments.push({ from: start, to: i });
      hide(start, i);
    } else if (source[i] === '"') {
      i++;
      while (i < source.length && source[i] !== '"') i += source[i] === "\\" ? 2 : 1;
      if (i >= source.length) return;
      hide(start + 1, i);
      i++;
    } else {
      if (/[`$\\]/.test(source[i])) return;
      i++;
    }
  }
  const pairs = new Map<number, number>();
  const lineDepth = new Map<number, number>([[0, 0]]);
  const stack: number[] = [];
  for (let i = 0; i < code.length; i++) {
    const char = code[i];
    if ("([{".includes(char)) stack.push(i);
    else if (")]}".includes(char)) {
      const start = stack.pop();
      if (start === undefined || "([{".indexOf(code[start]) !== ")]}".indexOf(char)) return;
      pairs.set(start, i);
    }
    if (/[\r\n]/.test(char)) lineDepth.set(i + 1, stack.length);
  }
  if (stack.length) return;
  return { source, code: code.join(""), comments, pairs, lineDepth };
}

function binding(input: SettingsSource, name: string): Range | undefined {
  const matches = [...input.code.matchAll(/^[ \t\ufeff]*#let ([\w-]+)[ \t]*=[ \t]*/gm)].filter(
    (match) => match[1] === name && input.lineDepth.get(match.index) === 0,
  );
  if (matches.length !== 1) return;
  const match = matches[0];
  return lineValue(input, match.index + match[0].length);
}

function lineValue(input: SettingsSource, from: number): Range {
  const line = input.code.slice(from).match(/^[^\r\n]*/)?.[0] ?? "";
  return { from, to: from + line.trimEnd().length };
}

function supportedValue(input: SettingsSource, range: Range): string | undefined {
  const { from, to } = range;
  if (from === to || input.comments.some((part) => part.from < to && part.to > from)) return;
  const value = input.source.slice(from, to);
  if (value.startsWith('"')) {
    try {
      if (typeof JSON.parse(value) === "string") return value;
    } catch {
      return;
    }
  }
  if (["black", "white"].includes(value)) return value;
  const call = value.match(/^(image|rgb)\(/);
  if (call?.[1] === "image" && !/^image\("[^"\\\r\n]+"[ \t]*(?:,|\))/.test(value)) return;
  if (call?.[1] === "rgb" && !/^rgb\("#[\da-f]{6}"\)$/i.test(value)) return;
  if (call && input.pairs.get(from + call[0].length - 1) === to - 1) return value;
}

function manualEdit(name: string): Error {
  return new Error(
    `Edit ${name} in Settings. This control needs one supported value on its own line.`,
  );
}

export function settingValue(bytes: Uint8Array, name: string): string | undefined {
  const input = settingsSource(decoder.decode(bytes));
  const range = input && binding(input, name);
  return input && range ? supportedValue(input, range) : undefined;
}

function replaceValues(source: string, changes: (Range & { value: string })[]): Uint8Array {
  for (const { from, to, value } of changes.sort((a, b) => b.from - a.from))
    source = source.slice(0, from) + value + source.slice(to);
  return encoder.encode(source);
}

export function updateThemeSettings(bytes: Uint8Array, values: Record<string, string>): Uint8Array {
  const source = decoder.decode(bytes);
  const input = settingsSource(source);
  const changes = Object.entries(values).map(([name, value]) => {
    const range = input && binding(input, name);
    const replacement = settingsSource(value);
    if (
      !input ||
      !range ||
      supportedValue(input, range) === undefined ||
      !replacement ||
      supportedValue(replacement, { from: 0, to: value.length }) === undefined
    )
      throw manualEdit(name);
    return { ...range, value };
  });
  return replaceValues(source, changes);
}

export function updateQRStyle(bytes: Uint8Array, shape: string): Uint8Array {
  const source = decoder.decode(bytes);
  const input = settingsSource(source);
  const qr = input && binding(input, "qr");
  const end = qr && input?.pairs.get(qr.from);
  if (
    !input ||
    !qr ||
    input.code[qr.from] !== "(" ||
    end === undefined ||
    input.code.slice(end + 1, lineValue(input, end + 1).to).trim()
  )
    throw manualEdit("qr");
  // A spread may replace these fields after the edit; leave such dictionaries alone.
  for (let i = qr.from + 1; i < end; i++) {
    if (input.code.startsWith("..", i)) throw manualEdit("qr");
    i = input.pairs.get(i) ?? i;
  }
  const changes = [
    ["module-shape", shape],
    ["corner-style", "rounded"],
  ].map(([name, value]) => {
    const matches = [...input.code.matchAll(/^[ \t]*([\w-]+):[ \t]*/gm)].filter(
      (match) =>
        match[1] === name &&
        match.index > qr.from &&
        match.index < end &&
        input.lineDepth.get(match.index) === 1,
    );
    if (matches.length !== 1) throw manualEdit(`qr ${name}`);
    const match = matches[0];
    const range = lineValue(input, match.index + match[0].length);
    if (input.code[range.to - 1] !== ",") throw manualEdit(`qr ${name}`);
    range.to--;
    while (/\s/.test(input.code[range.to - 1] ?? "") && range.to > range.from) range.to--;
    const previous = supportedValue(input, range);
    if (!previous?.startsWith('"')) throw manualEdit(`qr ${name}`);
    return { ...range, value: JSON.stringify(value) };
  });
  return replaceValues(source, changes);
}
