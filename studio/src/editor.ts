import { json } from "@codemirror/lang-json";
import {
  foldedRanges,
  HighlightStyle,
  syntaxHighlighting,
  unfoldEffect,
} from "@codemirror/language";
import { setDiagnostics } from "@codemirror/lint";
import { EditorState, StateEffect, StateField } from "@codemirror/state";
import { Decoration, type DecorationSet, EditorView, keymap } from "@codemirror/view";
import { tags } from "@lezer/highlight";
import { basicSetup } from "codemirror";
import { decoder, editableFile, encoder } from "./project";
import type { Diagnostic } from "./types";
import { typstHelp } from "./typst-help";
import { typst } from "./typst-language";

const typstColours = HighlightStyle.define([
  { tag: tags.function(tags.variableName), color: "var(--syntax-function)" },
  { tag: tags.namespace, color: "var(--syntax-namespace)" },
  { tag: tags.variableName, color: "var(--syntax-variable)" },
  { tag: tags.keyword, color: "var(--syntax-keyword)" },
  { tag: tags.number, color: "var(--syntax-number)" },
  { tag: tags.string, color: "var(--syntax-string)" },
  { tag: tags.comment, color: "var(--syntax-comment)", fontStyle: "italic" },
]);

const sourceTarget = StateEffect.define<{ from: number; to: number }>();
const sourceHighlight = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(value, transaction) {
    if (transaction.docChanged || transaction.selection) value = Decoration.none;
    for (const effect of transaction.effects) {
      if (effect.is(sourceTarget) && effect.value.to > effect.value.from) {
        value = Decoration.set([
          Decoration.mark({ class: "source-target" }).range(effect.value.from, effect.value.to),
        ]);
      }
    }
    return value;
  },
  provide: (field) => EditorView.decorations.from(field),
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
          EditorState.readOnly.of(!editableFile(name)),
          EditorView.editable.of(editableFile(name)),
          keymap.of([
            { key: "Mod-/", run: (view) => this.editLines(view, "comment") },
            { key: "Mod-[", run: (view) => this.editLines(view, "outdent") },
            { key: "Mod-]", run: (view) => this.editLines(view, "indent") },
          ]),
          EditorView.lineWrapping,
          sourceHighlight,
          name.endsWith(".json") ? json() : [typst, typstHelp, syntaxHighlighting(typstColours)],
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
  private editLines(view: EditorView, action: "comment" | "outdent" | "indent"): boolean {
    if (view.state.readOnly) return false;
    const selected = view.state.selection.main;
    const first = view.state.doc.lineAt(selected.from);
    const last = view.state.doc.lineAt(selected.to > selected.from ? selected.to - 1 : selected.to);
    const lines = [];
    for (let number = first.number; number <= last.number; number++)
      lines.push(view.state.doc.line(number));
    const uncomment = action === "comment" && lines.every((line) => /^\s*\/\//.test(line.text));
    view.dispatch({
      changes: lines.map((line) => {
        if (action === "indent") return { from: line.from, insert: "  " };
        if (action === "outdent")
          return {
            from: line.from,
            to: line.from + (line.text.match(/^(?: {2}| |\t)/)?.[0].length ?? 0),
            insert: "",
          };
        const indent = line.text.match(/^[ \t]*/)?.[0].length ?? 0;
        return {
          from: line.from + indent,
          to:
            line.from +
            indent +
            (uncomment ? (line.text.slice(indent).startsWith("// ") ? 3 : 2) : 0),
          insert: uncomment ? "" : "// ",
        };
      }),
    });
    return true;
  }
  replaceFile(name: string, original: Uint8Array, bytes: Uint8Array) {
    if (!editableFile(name)) return;
    const previous = this.file;
    const previousState = this.view.state;
    this.open(name, original);
    this.view.dispatch({
      changes: { from: 0, to: this.view.state.doc.length, insert: decoder.decode(bytes) },
    });
    if (previous !== name && previous)
      this.open(previous, encoder.encode(previousState.sliceDoc()));
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
        const line = doc.line(Math.min(doc.lines, Math.max(1, Number(match?.[1] ?? 0) + 1)));
        const from = Math.min(line.to, line.from + Math.max(0, Number(match?.[2] ?? 0)));
        return {
          from,
          to: Math.min(doc.length, from + 1),
          severity: item.severity === "warning" ? ("warning" as const) : ("error" as const),
          message: item.message,
        };
      });
    this.view.dispatch(setDiagnostics(this.view.state, mapped));
  }
  highlight(from: number, to: number) {
    const effects: ReturnType<typeof unfoldEffect.of>[] = [];
    foldedRanges(this.view.state).between(from, to, (start, end) => {
      effects.push(unfoldEffect.of({ from: start, to: end }));
    });
    this.view.dispatch({
      effects: [...effects, sourceTarget.of({ from, to })],
      selection: { anchor: from, head: to },
      scrollIntoView: true,
    });
    this.view.focus();
  }
  jump(line: number) {
    const from = this.view.state.doc.line(
      Math.max(1, Math.min(line, this.view.state.doc.lines)),
    ).from;
    this.highlight(from, from);
  }
}
