import { StreamLanguage, type StreamParser, type StringStream } from "@codemirror/language";

type Frame = { mode: "markup" | "code"; end: string; statement?: string };
type State = { frames: Frame[]; comments: number; raw: number; quoted: boolean };
const statements = new Set(["let", "set", "show", "import", "include", "if", "for", "while"]);
const keywords =
  /^(?:let|if|else|for|while|in|true|false|auto|none|import|include|as|set|show|return|break|continue)$/;

function finishExpression(stream: StringStream, state: State) {
  if (state.frames.at(-1)?.end === "inline" && !/[.([]/.test(stream.peek() ?? " "))
    state.frames.pop();
}

export const typstParser: StreamParser<State> = {
  languageData: { commentTokens: { line: "//", block: { open: "/*", close: "*/" } } },
  startState: () => ({ frames: [{ mode: "markup", end: "" }], comments: 0, raw: 0, quoted: false }),
  copyState: (state) => ({ ...state, frames: state.frames.map((frame) => ({ ...frame })) }),
  token(stream, state) {
    if (stream.sol()) {
      while (["line", "inline"].includes(state.frames.at(-1)?.end ?? "")) state.frames.pop();
    }
    if (state.raw) {
      if (stream.match("`".repeat(state.raw))) state.raw = 0;
      else stream.next();
      return "string";
    }
    if (state.comments) {
      if (stream.match("/*")) state.comments++;
      else if (stream.match("*/")) state.comments--;
      else stream.next();
      return "comment";
    }
    if (state.quoted) {
      const char = stream.next();
      if (char === "\\") stream.next();
      else if (char === '"') {
        state.quoted = false;
        finishExpression(stream, state);
      }
      return "string";
    }
    if (stream.match("//")) {
      stream.skipToEnd();
      return "comment";
    }
    if (stream.match("/*")) {
      state.comments = 1;
      return "comment";
    }
    if (stream.eatSpace()) return null;
    const frame = state.frames.at(-1) ?? { mode: "markup", end: "" };
    if (frame.end && stream.peek() === frame.end) {
      stream.next();
      state.frames.pop();
      const parent = state.frames.at(-1);
      if (
        ["]", "}"].includes(frame.end) &&
        ["if", "for", "while"].includes(parent?.statement ?? "") &&
        !stream.match(/\s*else\b/, false)
      )
        state.frames.pop();
      finishExpression(stream, state);
      return "bracket";
    }
    if (frame.mode === "markup") {
      if (stream.match("\\")) {
        stream.next();
        return null;
      }
      const raw = stream.match(/`+/);
      if (raw) {
        state.raw = (raw as RegExpMatchArray)[0].length;
        return "string";
      }
      const expression = stream.match(/#([\w-]+)/);
      if (expression) {
        const name = (expression as RegExpMatchArray)[1];
        state.frames.push({
          mode: "code",
          end: statements.has(name) ? "line" : "inline",
          statement: name,
        });
        if (!statements.has(name)) finishExpression(stream, state);
        return keywords.test(name)
          ? "keyword"
          : stream.match(/\s*[([]/, false)
            ? "variableName.function"
            : stream.match(".", false)
              ? "namespace"
              : "variableName";
      }
      if (stream.match("#", false) && /^#[({[]/.test(stream.string.slice(stream.pos))) {
        stream.next();
        state.frames.push({ mode: "code", end: "inline" });
        return "punctuation";
      }
      if (stream.match("[")) {
        state.frames.push({ mode: "markup", end: "]" });
        return "bracket";
      }
      stream.next();
      return null;
    }
    if (stream.match('"')) {
      state.quoted = true;
      return "string";
    }
    const open = stream.match(/[({[]/);
    if (open) {
      const char = (open as RegExpMatchArray)[0];
      state.frames.push({
        mode: char === "[" ? "markup" : "code",
        end: { "(": ")", "{": "}", "[": "]" }[char] ?? "",
      });
      return "bracket";
    }
    const word = stream.match(/[\w-]+/);
    if (word) {
      const value = (word as RegExpMatchArray)[0];
      finishExpression(stream, state);
      if (keywords.test(value)) return "keyword";
      if (/^\d/.test(value)) return "number";
      return stream.match(/\s*[([]/, false)
        ? "variableName.function"
        : stream.match(".", false)
          ? "namespace"
          : "variableName";
    }
    const char = stream.next();
    if (char === ";" && ["line", "inline"].includes(frame.end)) state.frames.pop();
    return null;
  },
};

export const typst = StreamLanguage.define(typstParser);
