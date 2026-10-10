import {
  getDocument,
  GlobalWorkerOptions,
  type PDFDocumentProxy,
  type RenderTask,
  type PDFDocumentLoadingTask,
} from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
GlobalWorkerOptions.workerSrc = workerUrl;

type Sheet = {
  paper: HTMLElement;
  canvas: HTMLCanvasElement;
  overlay: HTMLElement;
  scale: number;
  rendered: boolean;
};
export class Viewer {
  page = 1;
  pages = 0;
  zoom: number | "fit" = "fit";
  private document?: PDFDocumentProxy;
  private loading?: PDFDocumentLoadingTask;
  private task?: RenderTask;
  private queue: Promise<void> = Promise.resolve();
  private revision = 0;
  private drawRevision = 0;
  private geometry: Record<string, number> = {};
  private guide = false;
  private sheets: Sheet[] = [];
  private scheduled = false;
  constructor(
    private container: HTMLElement,
    private updated: () => void,
  ) {
    let width = container.clientWidth;
    new ResizeObserver(() => {
      if (width === container.clientWidth) return;
      width = container.clientWidth;
      if (this.zoom === "fit") void this.render();
    }).observe(container);
    container.addEventListener("scroll", () => {
      if (this.scheduled) return;
      this.scheduled = true;
      requestAnimationFrame(() => {
        this.scheduled = false;
        const top = container.getBoundingClientRect().top + 80;
        const index = this.sheets.findIndex(
          (sheet) => sheet.paper.getBoundingClientRect().bottom > top,
        );
        if (index >= 0 && this.page !== index + 1) {
          this.page = index + 1;
          this.updated();
        }
        this.queue = this.queue.catch(() => {}).then(() => this.paintVisible(this.drawRevision));
      });
    });
  }
  async open(bytes: Uint8Array) {
    const revision = ++this.revision;
    this.task?.cancel();
    this.drawRevision++;
    const loading = getDocument({
      data: bytes.slice(),
      useWasm: false,
      enableXfa: false,
      disableAutoFetch: true,
    });
    const doc = await loading.promise;
    await this.queue.catch(() => {});
    if (revision !== this.revision) {
      await loading.destroy();
      return;
    }
    const old = this.loading;
    this.loading = loading;
    this.document = doc;
    this.pages = doc.numPages;
    this.page = 1;
    if (old) await old.destroy();
    const content = await (await doc.getPage(1)).getTextContent();
    if (revision !== this.revision) return;
    const text = content.items.map((item) => ("str" in item ? item.str : "")).join(" ");
    this.geometry = {};
    for (const match of text.matchAll(/MEASURE_(\w+):(-?[\d.eE+-]+)/g))
      this.geometry[match[1]] = Number(match[2]);
    await this.render();
    this.updated();
  }
  layoutWarning(): string | undefined {
    const g = this.geometry;
    if (
      ![
        "WINDOW_X",
        "WINDOW_Y",
        "WINDOW_WIDTH",
        "WINDOW_HEIGHT",
        "WINDOW_PADDING",
        "ADDRESS_X",
        "ADDRESS_Y",
        "ADDRESS_WIDTH",
        "ADDRESS_HEIGHT",
      ].every((key) => Number.isFinite(g[key]))
    )
      return "Envelope geometry evidence is missing. Production validation will check the configured rule.";
    if (
      g.ADDRESS_X < g.WINDOW_X + g.WINDOW_PADDING - 0.01 ||
      g.ADDRESS_Y < g.WINDOW_Y + g.WINDOW_PADDING - 0.01 ||
      g.ADDRESS_X + g.ADDRESS_WIDTH > g.WINDOW_X + g.WINDOW_WIDTH - g.WINDOW_PADDING + 0.01 ||
      g.ADDRESS_Y + g.ADDRESS_HEIGHT > g.WINDOW_Y + g.WINDOW_HEIGHT - g.WINDOW_PADDING + 0.01
    )
      return "Address exceeds the envelope safety area. Adjust the authored window or address layout; review an actual-size print.";
    return undefined;
  }

  async go(delta: number) {
    this.page = Math.max(1, Math.min(this.pages, this.page + delta));
    this.scrollToPage();
    this.updated();
  }
  private scrollToPage() {
    const sheet = this.sheets[this.page - 1];
    if (sheet)
      this.container.scrollTop +=
        sheet.paper.getBoundingClientRect().top - this.container.getBoundingClientRect().top - 20;
  }
  setGuide(on: boolean) {
    this.guide = on;
    this.drawGuide();
  }
  private drawGuide() {
    const sheet = this.sheets[0];
    if (!sheet) return;
    sheet.overlay.replaceChildren();
    const g = this.geometry;
    if (
      !this.guide ||
      !["WINDOW_X", "WINDOW_Y", "WINDOW_WIDTH", "WINDOW_HEIGHT", "WINDOW_PADDING"].every((key) =>
        Number.isFinite(g[key]),
      )
    )
      return;
    for (const [padding, name] of [
      [0, "window"],
      [g.WINDOW_PADDING, "safe"],
    ] as const) {
      const rect = document.createElement("div");
      rect.className = `envelope-${name}`;
      Object.assign(rect.style, {
        left: `${(g.WINDOW_X + padding) * sheet.scale}px`,
        top: `${(g.WINDOW_Y + padding) * sheet.scale}px`,
        width: `${(g.WINDOW_WIDTH - 2 * padding) * sheet.scale}px`,
        height: `${(g.WINDOW_HEIGHT - 2 * padding) * sheet.scale}px`,
      });
      rect.title = name === "window" ? "Envelope window" : "Internal safety area";
      sheet.overlay.append(rect);
    }
  }
  render(): Promise<void> {
    const revision = ++this.drawRevision;
    this.task?.cancel();
    this.queue = this.queue
      .catch(() => {})
      .then(async () => {
        const doc = this.document;
        if (!doc || revision !== this.drawRevision) return;
        const sheets: Sheet[] = [];
        const fragment = document.createDocumentFragment();
        for (let number = 1; number <= doc.numPages; number++) {
          const page = await doc.getPage(number);
          if (revision !== this.drawRevision) return;
          const original = page.getViewport({ scale: 1 });
          const scale =
            this.zoom === "fit"
              ? Math.max(0.25, (this.container.clientWidth - 40) / original.width)
              : this.zoom;
          const viewport = page.getViewport({ scale });
          const paper = document.createElement("div"),
            canvas = document.createElement("canvas"),
            overlay = document.createElement("div");
          paper.className = "pdf-page";
          paper.dataset.page = String(number);
          paper.style.width = `${viewport.width}px`;
          paper.style.height = `${viewport.height}px`;
          canvas.setAttribute("aria-label", `Notice PDF page ${number} of ${doc.numPages}`);
          overlay.className = "pdf-overlay";
          overlay.setAttribute("aria-hidden", "true");
          paper.append(canvas, overlay);
          fragment.append(paper);
          sheets.push({ paper, canvas, overlay, scale, rendered: false });
        }
        this.sheets = sheets;
        this.container.replaceChildren(fragment);
        this.scrollToPage();
        this.drawGuide();
        await this.paintVisible(revision);
      });
    return this.queue;
  }
  private async paintVisible(revision: number) {
    const doc = this.document;
    if (!doc || revision !== this.drawRevision) return;
    const bounds = this.container.getBoundingClientRect();
    for (const [index, sheet] of this.sheets.entries()) {
      if (revision !== this.drawRevision) return;
      const rect = sheet.paper.getBoundingClientRect();
      if (rect.bottom < bounds.top - 600 || rect.top > bounds.bottom + 600) {
        if (sheet.rendered) {
          sheet.canvas.width = 0;
          sheet.canvas.height = 0;
          sheet.rendered = false;
        }
        continue;
      }
      if (sheet.rendered) continue;
      const page = await doc.getPage(index + 1);
      if (revision !== this.drawRevision) return;
      const viewport = page.getViewport({ scale: sheet.scale });
      const ratio = Math.min(devicePixelRatio || 1, 2);
      sheet.canvas.width = Math.ceil(viewport.width * ratio);
      sheet.canvas.height = Math.ceil(viewport.height * ratio);
      sheet.canvas.style.width = `${viewport.width}px`;
      sheet.canvas.style.height = `${viewport.height}px`;
      this.task = page.render({
        canvas: sheet.canvas,
        viewport,
        transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
      });
      try {
        await this.task.promise;
        sheet.rendered = true;
      } catch (error) {
        if ((error as Error).name !== "RenderingCancelledException") throw error;
      }
    }
  }
}
