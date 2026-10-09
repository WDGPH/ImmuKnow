import { basicSetup } from "codemirror";
import { EditorState } from "@codemirror/state";
import { EditorView } from "@codemirror/view";
import { StreamLanguage } from "@codemirror/language";
import { json } from "@codemirror/lang-json";
import { setDiagnostics } from "@codemirror/lint";
import type { Diagnostic } from "./types";
import { decoder, encoder } from "./project";

const typst = StreamLanguage.define({
  startState: () => ({ comment: false }),
  token(stream, state) {
    if (state.comment) {
      if (stream.skipTo("*/")) {
        stream.match("*/");
        state.comment = false;
      } else stream.skipToEnd();
      return "comment";
    }
    if (stream.match("//")) {
      stream.skipToEnd();
      return "comment";
    }
    if (stream.match("/*")) {
      state.comment = true;
      return "comment";
    }
    if (stream.match(/"(?:[^"\\]|\\.)*"/)) return "string";
    if (stream.match(/#[\w-]+/)) return "keyword";
    if (stream.match(/\b(?:let|if|else|for|in|true|false|auto|none|import|as|set|show)\b/))
      return "keyword";
    if (stream.match(/\b\d+(?:\.\d+)?(?:pt|cm|mm|in|em|fr|%)?/)) return "number";
    if (stream.match(/[()[\]{}]/)) return "bracket";
    stream.next();
    return null;
  },
});
export class SourceEditor {
  view: EditorView;
  file = "";
  private states = new Map<string, EditorState>();
  constructor(
    parent: HTMLElement,
    private changed: (name: string, bytes: Uint8Array) => void,
  ) {
    this.view = new EditorView({ parent, state: EditorState.create() });
  }
  open(name: string, bytes: Uint8Array) {
    if (this.file) this.states.set(this.file, this.view.state);
    this.file = name;
    let state = this.states.get(name);
    if (!state) {
      const text = decoder.decode(bytes);
      state = EditorState.create({
        doc: text,
        extensions: [
          basicSetup,
          name.endsWith(".json") ? json() : typst,
          EditorState.lineSeparator.of(text.includes("\r\n") ? "\r\n" : "\n"),
          EditorView.contentAttributes.of({ "aria-label": "Source editor", spellcheck: "false" }),
          EditorView.updateListener.of((update) => {
            if (update.docChanged) this.changed(this.file, encoder.encode(update.state.sliceDoc()));
          }),
          EditorView.theme({
            "&": { height: "100%", fontSize: "13px" },
            ".cm-scroller": { overflow: "auto", fontFamily: "ui-monospace, monospace" },
            ".cm-content": { paddingBottom: "8rem" },
          }),
        ],
      });
    }
    this.view.setState(state);
  }
  resetFile(name: string) {
    this.states.delete(name);
    if (this.file === name) this.file = "";
  }
  clear() {
    this.states.clear();
    this.file = "";
  }
  diagnostics(items: Diagnostic[]) {
    const doc = this.view.state.doc;
    const mapped = items
      .filter((d) => d.path.replace(/^\//, "") === this.file)
      .map((item) => {
        const match = /^(\d+):(\d+)(?:-(\d+):(\d+))?/.exec(item.range);
        const line = doc.line(Math.min(doc.lines, Math.max(1, Number(match?.[1] ?? 1))));
        const from = Math.min(line.to, line.from + Math.max(0, Number(match?.[2] ?? 1) - 1));
        return {
          from,
          to: Math.min(doc.length, from + 1),
          severity: item.severity === "warning" ? ("warning" as const) : ("error" as const),
          message: item.message,
        };
      });
    this.view.dispatch(setDiagnostics(this.view.state, mapped));
  }
  jump(line: number) {
    const from = this.view.state.doc.line(
      Math.max(1, Math.min(line, this.view.state.doc.lines)),
    ).from;
    this.view.dispatch({ selection: { anchor: from }, scrollIntoView: true });
    this.view.focus();
  }
}
