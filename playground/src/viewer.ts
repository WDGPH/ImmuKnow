import {
  getDocument,
  GlobalWorkerOptions,
  type PDFDocumentProxy,
  type RenderTask,
  type PDFDocumentLoadingTask,
} from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
GlobalWorkerOptions.workerSrc = workerUrl;

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
  private container: HTMLElement;
  constructor(
    private canvas: HTMLCanvasElement,
    private paper: HTMLElement,
    private overlay: HTMLElement,
    private updated: () => void,
  ) {
    const container = paper.parentElement;
    if (!container) throw new Error("Preview container is missing");
    this.container = container;
    new ResizeObserver(() => {
      if (this.zoom === "fit") void this.render();
    }).observe(container);
  }
  async open(bytes: Uint8Array) {
    const revision = ++this.revision;
    this.task?.cancel();
    const loading = getDocument({
      data: bytes.slice(),
      useWasm: false,
      enableXfa: false,
      disableAutoFetch: true,
    });
    const doc = await loading.promise;
    if (revision !== this.revision) {
      await loading.destroy();
      return;
    }
    await this.queue.catch(() => {});
    if (revision !== this.revision) {
      await loading.destroy();
      return;
    }
    const old = this.loading;
    this.loading = loading;
    this.document = doc;
    this.pages = doc.numPages;
    this.page = Math.min(this.page, this.pages);
    if (old) await old.destroy();
    const first = await doc.getPage(1);
    const content = await first.getTextContent();
    const text = content.items.map((item) => ("str" in item ? item.str : "")).join(" ");
    if (revision !== this.revision) return;
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
    await this.render();
    this.updated();
  }
  setGuide(on: boolean) {
    this.guide = on;
    void this.render();
  }
  render(): Promise<void> {
    const revision = ++this.drawRevision;
    this.task?.cancel();
    this.queue = this.queue
      .catch(() => {})
      .then(async () => {
        if (!this.document || revision !== this.drawRevision) return;
        const page = await this.document.getPage(this.page);
        if (revision !== this.drawRevision) return;
        const original = page.getViewport({ scale: 1 });
        const scale =
          this.zoom === "fit"
            ? Math.max(0.25, (this.container.clientWidth - 40) / original.width)
            : this.zoom;
        const viewport = page.getViewport({ scale });
        const ratio = Math.min(devicePixelRatio || 1, 2);
        this.canvas.width = Math.ceil(viewport.width * ratio);
        this.canvas.height = Math.ceil(viewport.height * ratio);
        this.canvas.style.width = `${viewport.width}px`;
        this.canvas.style.height = `${viewport.height}px`;
        this.paper.style.width = `${viewport.width}px`;
        this.paper.style.height = `${viewport.height}px`;
        this.task = page.render({
          canvas: this.canvas,
          viewport,
          transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
        });
        try {
          await this.task.promise;
        } catch (error) {
          if ((error as Error).name !== "RenderingCancelledException") throw error;
        }
        this.overlay.replaceChildren();
        const g = this.geometry;
        if (
          this.guide &&
          this.page === 1 &&
          ["WINDOW_X", "WINDOW_Y", "WINDOW_WIDTH", "WINDOW_HEIGHT", "WINDOW_PADDING"].every((key) =>
            Number.isFinite(g[key]),
          )
        ) {
          for (const [padding, name] of [
            [0, "window"],
            [g.WINDOW_PADDING, "safe"],
          ] as const) {
            const rect = document.createElement("div");
            rect.className = `envelope-${name}`;
            Object.assign(rect.style, {
              left: `${(g.WINDOW_X + padding) * scale}px`,
              top: `${(g.WINDOW_Y + padding) * scale}px`,
              width: `${(g.WINDOW_WIDTH - 2 * padding) * scale}px`,
              height: `${(g.WINDOW_HEIGHT - 2 * padding) * scale}px`,
            });
            rect.title = name === "window" ? "Envelope window" : "Internal safety area";
            this.overlay.append(rect);
          }
        }
      });
    return this.queue;
  }
}
