import { syntaxTree } from "@codemirror/language";
import type { EditorState } from "@codemirror/state";
import { hoverTooltip } from "@codemirror/view";

type Help = {
  description: string;
  parameters: [string, string][];
  example: string;
  reference?: string;
};

// Keep descriptions short; the linked Typst reference contains the complete parameter list.
const help: Record<string, Help> = {
  v: {
    description: "Adds vertical space between parts of the letter.",
    parameters: [
      ["amount", "Gap size, such as 0.3cm or 12pt. Use 1fr to share the remaining space."],
      ["weak", "Set true to omit extra space at the beginning or end. Defaults to false."],
    ],
    example: "#v(0.3cm)",
    reference: "layout/v/",
  },
  text: {
    description: "Changes the appearance of the enclosed text.",
    parameters: [
      ["size", "Text size, such as 12pt."],
      ["fill", "Text colour, such as link-color."],
      ["font", "Typeface name, such as body-font."],
      ["[content]", "The words to format."],
    ],
    example: "#text(size: 12pt)[Please update your record.]",
    reference: "text/text/",
  },
  link: {
    description: "Makes a clickable link. The template applies your link colour.",
    parameters: [
      ["destination", "A quoted website URL or a location in the document."],
      ["[content]", "Optional link text. Leave it out to display the URL."],
    ],
    example: '#link("https://example.ca/update")[Update your record]',
    reference: "model/link/",
  },
  image: {
    description: "Places an image, such as your logo or signature.",
    parameters: [
      ["source", "The image file path, such as assets/logo.png."],
      ["width / height", "Displayed size, such as 6cm."],
      ["fit", 'Use "contain" to show the whole image within the chosen size.'],
    ],
    example: '#image("assets/logo.png", width: 6cm)',
    reference: "visualize/image/",
  },
  "notice-page": {
    description:
      "Starts a named page with the logo, heading, and standard spacing. Reports a finding if it unexpectedly continues onto more pages.",
    parameters: [
      ["title", "The heading text, in quotes."],
      ["body", "The page content inside square brackets."],
      ["allow-overflow", "Set true to allow this content to continue onto more pages."],
    ],
    example: '#notice-page("Request for Immunization Record")[Your letter here.]',
  },
  "immuknow.notice-header": {
    description: "Places the logo and letter heading together.",
    parameters: [
      ["logo", "The logo image."],
      ["title", "The heading text."],
      ["title-size / fill", "Heading size and colour."],
    ],
    example: '#immuknow.notice-header(title: "Immunization Record")',
  },
  "immuknow.client-block": {
    description: "Places the mailing address and client details.",
    parameters: [
      ["notice", "This client’s data."],
      ["window", "Position and size of the envelope window."],
      ["details", 'Use "right" beside the address or "below" underneath it.'],
    ],
    example: '#immuknow.client-block(notice, details: "below")',
  },
  "immuknow.qr-code": {
    description: "Draws a QR code using the client’s authored link function or a fixed URL.",
    parameters: [
      ["notice", "This client’s prepared facts."],
      ["url", "A fixed URL, or a function that builds a link from this notice."],
      ["width", "Displayed width, such as 3cm."],
      ["enabled", "Set false to hide the code."],
    ],
    example: '#immuknow.qr-code(notice, url: "https://example.org/update", width: 3cm)',
  },
};

export function functionHelp(state: EditorState, position: number) {
  const line = state.doc.lineAt(position);
  for (const match of line.text.matchAll(/#?(?:immuknow\.)?[a-zA-Z][\w-]*(?=\s*[([])/g)) {
    const from = line.from + match.index,
      to = from + match[0].length;
    if (position < from || position > to) continue;
    const name = match[0].replace(/^#/, "");
    if (!Object.hasOwn(help, name)) continue;
    const node = syntaxTree(state).resolveInner(from + 1, 1);
    if (!/^(variableName(?:\.function)?|namespace|keyword)$/i.test(node.name)) return;
    return { from, to, name, help: help[name] };
  }
}

export const typstHelp = hoverTooltip(
  (view, position, side) => {
    const found = functionHelp(view.state, position);
    if (!found || (position === found.from && side < 0) || (position === found.to && side > 0))
      return null;
    return {
      pos: found.from,
      end: found.to,
      above: true,
      create() {
        const dom = document.createElement("div");
        dom.className = "function-help";
        dom.setAttribute("role", "tooltip");
        const title = document.createElement("code");
        title.textContent = `#${found.name}`;
        const description = document.createElement("p");
        description.textContent = found.help.description;
        dom.append(title, description);
        const parameters = document.createElement("dl");
        for (const [name, explanation] of found.help.parameters) {
          const label = document.createElement("dt"),
            detail = document.createElement("dd");
          label.textContent = name;
          detail.textContent = explanation;
          parameters.append(label, detail);
        }
        const example = document.createElement("pre");
        example.textContent = found.help.example;
        dom.append(parameters, example);
        if (found.help.reference) {
          const reference = document.createElement("a");
          reference.textContent = "Typst reference";
          reference.href = `https://typst.app/docs/reference/${found.help.reference}`;
          reference.target = "_blank";
          reference.rel = "noopener noreferrer";
          dom.append(reference);
        }
        return { dom };
      },
    };
  },
  { hoverTime: 350 },
);
