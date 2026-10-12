import initialize, {
  TypstRenderer,
  RenderPageImageOptions,
  type RenderSession,
} from "../vendor/renderer/typst_ts_renderer.js";
import wasmUrl from "../vendor/renderer/typst_ts_renderer_bg.wasm?url";
import type { CheckResult, Preview, PreviewPage } from "./types";

// One local module initialization; sessions contain one complete document only.
let initialized: ReturnType<typeof initialize> | undefined;
let rendererMemory: WebAssembly.Memory | undefined;
type Sheet = {
  paper: HTMLElement;
  canvas: HTMLCanvasElement;
  overlay: HTMLElement;
  scale: number;
  width: number;
  height: number;
  top: number;
  page: PreviewPage;
};
type Position = { page: number; y: number; x: number };
type Candidate = {
  preview: Preview;
  checks: CheckResult[];
  timing: Record<string, number>;
  resolve: (committed: boolean) => void;
  reject: (error: unknown) => void;
};

export class Viewer {
  page = 1;
  pages = 0;
  zoom: number | "fit" = "fit";
  private renderer?: TypstRenderer;
  private document?: Preview;
  private generation = 0;
  private pending?: Candidate;
  private running = false;
  private frame?: number;
  private disposed = false;
  private observer: ResizeObserver;
  private geometry: Record<string, number> = {};
  private guide = false;
  private sheets: Sheet[] = [];
  private canvasesPainted = 0;
  get resources() {
    return {
      documents: Number(Boolean(this.document)),
      preparing: Number(this.running),
      pending: Number(Boolean(this.pending)),
      canvases: this.sheets.length,
      canvasBytes: this.sheets.reduce((sum, s) => sum + s.canvas.width * s.canvas.height * 4, 0),
      artifactBytes: this.document?.artifact.byteLength ?? 0,
      rendererBytes: rendererMemory?.buffer.byteLength ?? 0,
      canvasesPainted: this.canvasesPainted,
    };
  }
  constructor(
    private container: HTMLElement,
    private updated: () => void,
    private selected: (text: string) => boolean,
  ) {
    let width = container.clientWidth;
    this.observer = new ResizeObserver(() => {
      if (width === container.clientWidth) return;
      width = container.clientWidth;
      if (this.zoom === "fit") this.render();
    });
    this.observer.observe(container);
    container.addEventListener("scroll", this.scrolled);
    container.addEventListener("dblclick", this.selectText);
  }
  private free(sheets: Sheet[]) {
    for (const sheet of sheets) sheet.canvas.width = sheet.canvas.height = 0;
  }
  clear() {
    this.generation++;
    this.pending?.resolve(false);
    this.pending = undefined;
    this.document = undefined;
    this.free(this.sheets);
    this.sheets = [];
    this.geometry = {};
    this.page = 1;
    this.pages = 0;
    this.container.replaceChildren();
    this.container.scrollTop = this.container.scrollLeft = 0;
    this.updated();
  }
  async destroy() {
    this.disposed = true;
    this.clear();
    if (this.frame !== undefined) cancelAnimationFrame(this.frame);
    this.observer.disconnect();
    this.container.removeEventListener("scroll", this.scrolled);
    this.container.removeEventListener("dblclick", this.selectText);
    // An in-flight renderer owns its session until its async draw finishes.
    if (!this.running) this.releaseRenderer();
  }
  private releaseRenderer() {
    this.renderer?.free();
    this.renderer = undefined;
  }
  open(
    preview: Preview,
    checks: CheckResult[] = [],
    timing: Record<string, number> = {},
  ): Promise<boolean> {
    if (this.disposed) return Promise.resolve(false);
    this.pending?.resolve(false);
    const result = new Promise<boolean>((resolve, reject) => {
      this.pending = { preview, checks, timing, resolve, reject };
    });
    if (!this.running) void this.work();
    return result;
  }
  get zoomScale() {
    return typeof this.zoom === "number" ? this.zoom : (this.sheets[0]?.scale ?? 1);
  }
  zoomBy(factor: number) {
    this.zoom = Math.max(0.25, Math.min(3, this.zoomScale * factor));
    this.render();
  }
  render() {
    if (this.disposed || this.frame !== undefined) return;
    // Resizing/zoom changes the shell only. Every page remains painted.
    this.frame = requestAnimationFrame(() => {
      this.frame = undefined;
      const position = this.position();
      this.size(this.sheets);
      this.drawGuide();
      this.restore(position);
      this.updated();
    });
  }
  private scrolled = () => {
    this.page = this.position().page;
    this.updated();
  };
  private position(): Position {
    const top = this.container.scrollTop;
    const found = this.sheets.findIndex((s) => s.top + s.height > top);
    const index = found < 0 ? Math.max(0, this.sheets.length - 1) : found;
    const sheet = this.sheets[index];
    return {
      page: index + 1,
      y: sheet ? (top - sheet.top) / sheet.height : 0,
      x: this.container.scrollLeft / (sheet?.scale ?? 1),
    };
  }
  private restore(position: Position) {
    const index = Math.min(position.page, this.sheets.length) - 1;
    const sheet = this.sheets[index];
    if (!sheet) return;
    this.container.scrollTop = Math.max(0, sheet.top + position.y * sheet.height);
    this.container.scrollLeft = position.x * sheet.scale;
    this.page = this.position().page;
  }
  private size(sheets: Sheet[]) {
    let top = 1;
    for (const sheet of sheets) {
      sheet.paper.querySelector(".preview-source-target")?.remove();
      sheet.scale =
        this.zoom === "fit"
          ? Math.max(0.25, (this.container.clientWidth - 40) / sheet.page.width)
          : this.zoom;
      sheet.width = sheet.page.width * sheet.scale;
      sheet.height = sheet.page.height * sheet.scale;
      sheet.top = top;
      sheet.paper.style.width = `${sheet.width}px`;
      sheet.paper.style.height = `${sheet.height}px`;
      sheet.canvas.style.width = "100%";
      sheet.canvas.style.height = "100%";
      top += sheet.height + 20;
    }
  }
  private async prepare(preview: Preview, sheets: Sheet[], generation: number) {
    initialized ??= initialize({ module_or_path: wasmUrl });
    try {
      rendererMemory = (await initialized).memory;
    } catch (error) {
      // A later preview can retry a failed local resource fetch.
      initialized = undefined;
      throw error;
    }
    if (generation !== this.generation || this.disposed) return;
    this.renderer ??= new TypstRenderer();
    // Bound total allocation and each canvas edge, without truncating pages.
    const area = preview.pages.reduce((sum, p) => sum + p.width * p.height, 0);
    const edge = Math.max(...preview.pages.map((p) => Math.max(p.width, p.height)));
    const resolution = Math.min(2, Math.sqrt(32_000_000 / area), 8192 / edge);
    if (!preview.pages.length || !Number.isFinite(resolution) || resolution < 0.5)
      throw new Error(
        "This notice exceeds the preview resource limit. The last usable preview is retained.",
      );
    let session: RenderSession | undefined;
    try {
      session = this.renderer.session_from_artifact(preview.artifact, "vector");
      const info = session.pages_info;
      try {
        if (info.page_count !== preview.pages.length)
          throw new Error("Preview page count differs from the compiled document");
        for (let i = 0; i < preview.pages.length; i++) {
          const actual = info.page(i);
          try {
            if (
              Math.abs(actual.width_pt - preview.pages[i].width) > 0.01 ||
              Math.abs(actual.height_pt - preview.pages[i].height) > 0.01
            )
              throw new Error("Preview dimensions differ from the compiled document");
          } finally {
            actual.free();
          }
        }
      } finally {
        info.free();
      }
      for (const [index, page] of preview.pages.entries()) {
        const paper = document.createElement("div"),
          canvas = document.createElement("canvas"),
          overlay = document.createElement("div");
        paper.className = "preview-page";
        paper.dataset.page = String(index + 1);
        paper.setAttribute("role", "group");
        paper.setAttribute("aria-label", `Notice page ${index + 1} of ${preview.pages.length}`);
        paper.title = "Double-click text to find it in the current template";
        canvas.width = Math.ceil(page.width * resolution);
        canvas.height = Math.ceil(page.height * resolution);
        canvas.setAttribute("aria-hidden", "true");
        overlay.className = "preview-overlay";
        overlay.setAttribute("aria-hidden", "true");
        const text = document.createElement("span");
        text.className = "visually-hidden";
        text.textContent = page.plainText;
        paper.append(canvas, text, overlay);
        sheets.push({
          paper,
          canvas,
          overlay,
          page,
          scale: 1,
          width: page.width,
          height: page.height,
          top: 0,
        });
        const options = new RenderPageImageOptions();
        options.page_off = index;
        options.pixel_per_pt = resolution;
        options.data_selection = 1;
        options.background_color = "#ffffff";
        // The binding consumes options. No HTML, links, or document scripts are inserted.
        await this.renderer.render_page_to_canvas(session, canvas.getContext("2d"), options);
        this.canvasesPainted++;
        if (generation !== this.generation || this.disposed) return;
      }
    } finally {
      session?.free();
      this.renderer.release_resources();
    }
  }
  private async work() {
    const candidate = this.pending;
    if (!candidate || this.disposed) return;
    this.pending = undefined;
    this.running = true;
    const generation = this.generation;
    let sheets: Sheet[] = [];
    try {
      const start = performance.now();
      const painted = this.canvasesPainted;
      await this.prepare(candidate.preview, sheets, generation);
      if (generation !== this.generation || this.disposed) {
        candidate.resolve(false);
        return;
      }
      // Read the user's latest position only after every replacement page is ready.
      const position = this.position();
      this.size(sheets);
      const previous = this.sheets;
      this.sheets = sheets;
      sheets = [];
      this.document = candidate.preview;
      this.pages = this.sheets.length;
      this.measurements(candidate.checks);
      this.drawGuide();
      this.container.replaceChildren(...this.sheets.map((s) => s.paper));
      this.restore(position);
      this.free(previous);
      candidate.timing.render = performance.now() - start;
      candidate.timing.canvasesPainted = this.canvasesPainted - painted;
      candidate.timing.canvasBytes = this.resources.canvasBytes;
      candidate.timing.committed = performance.timeOrigin + performance.now();
      this.updated();
      candidate.resolve(true);
    } catch (error) {
      if (generation !== this.generation) candidate.resolve(false);
      else candidate.reject(error);
    } finally {
      this.free(sheets);
      this.running = false;
      if (this.disposed) this.releaseRenderer();
      else if (this.pending) void this.work();
    }
  }
  private selectText = (event: MouseEvent) => {
    const paper = (event.target as HTMLElement).closest<HTMLElement>(".preview-page");
    const sheet = this.sheets[Number(paper?.dataset.page) - 1];
    if (!paper || !sheet) return;
    const bounds = paper.getBoundingClientRect();
    const x = (event.clientX - bounds.left) / sheet.scale,
      y = (event.clientY - bounds.top) / sheet.scale;
    const text = sheet.page.text.find(
      (t) => x >= t.x - 2 && x <= t.x + t.width + 2 && y >= t.y - 2 && y <= t.y + t.height + 2,
    );
    if (!text || !this.selected(text.text)) return;
    this.container.querySelectorAll(".preview-source-target").forEach((target) => {
      target.remove();
    });
    const target = document.createElement("div");
    target.className = "preview-source-target source-target";
    target.setAttribute("aria-hidden", "true");
    Object.assign(target.style, {
      left: `${text.x * sheet.scale - 2}px`,
      top: `${text.y * sheet.scale - 2}px`,
      width: `${text.width * sheet.scale + 4}px`,
      height: `${text.height * sheet.scale + 4}px`,
    });
    paper.append(target);
  };
  setGuide(on: boolean) {
    this.guide = on;
    this.drawGuide();
  }
  private measurements(checks: CheckResult[]) {
    const measurement = checks.find(
      (check) => check.component === "address" && check.measurements?.window_x_pt !== undefined,
    )?.measurements;
    this.geometry = {};
    if (measurement) {
      if (typeof measurement.page === "number") this.geometry.PAGE = measurement.page;
      for (const [target, source] of Object.entries({
        WINDOW_X: "window_x_pt",
        WINDOW_Y: "window_y_pt",
        WINDOW_WIDTH: "window_width_pt",
        WINDOW_HEIGHT: "window_height_pt",
        WINDOW_PADDING: "window_padding_pt",
        ADDRESS_X: "x_pt",
        ADDRESS_Y: "y_pt",
        ADDRESS_WIDTH: "width_pt",
        ADDRESS_HEIGHT: "height_pt",
      })) {
        const value = measurement[source];
        if (typeof value === "number") this.geometry[target] = value;
      }
    }
  }
  private drawGuide() {
    for (const page of this.sheets) page.overlay.replaceChildren();
    const sheet = this.sheets[(this.geometry.PAGE ?? 1) - 1];
    if (!sheet) return;
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
    if (
      ["ADDRESS_X", "ADDRESS_Y", "ADDRESS_WIDTH", "ADDRESS_HEIGHT"].every((key) =>
        Number.isFinite(g[key]),
      )
    ) {
      const address = document.createElement("div");
      address.className = "envelope-address";
      address.title = "Measured address";
      Object.assign(address.style, {
        left: `${g.ADDRESS_X * sheet.scale}px`,
        top: `${g.ADDRESS_Y * sheet.scale}px`,
        width: `${g.ADDRESS_WIDTH * sheet.scale}px`,
        height: `${g.ADDRESS_HEIGHT * sheet.scale}px`,
      });
      sheet.overlay.append(address);
    }
  }
}
