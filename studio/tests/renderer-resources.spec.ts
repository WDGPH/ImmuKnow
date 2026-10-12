import { expect, test } from "@playwright/test";

test("changing image previews close bitmaps and revoke blob URLs", async ({ page }) => {
  await page.addInitScript(() => {
    const liveBitmaps = new Set<ImageBitmap>();
    const liveUrls = new Set<string>();
    const originalCreate = window.createImageBitmap.bind(window);
    const originalTransfer = OffscreenCanvas.prototype.transferToImageBitmap;
    const originalClose = ImageBitmap.prototype.close;
    const originalUrlCreate = URL.createObjectURL.bind(URL);
    const originalUrlRevoke = URL.revokeObjectURL.bind(URL);
    let createdBitmaps = 0;
    let createdUrls = 0;
    const track = (bitmap: ImageBitmap) => {
      createdBitmaps++;
      liveBitmaps.add(bitmap);
      return bitmap;
    };
    window.createImageBitmap = ((...args: Parameters<typeof createImageBitmap>) =>
      originalCreate(...args).then(track)) as typeof createImageBitmap;
    OffscreenCanvas.prototype.transferToImageBitmap = function () {
      return track(originalTransfer.call(this));
    };
    ImageBitmap.prototype.close = function () {
      liveBitmaps.delete(this);
      return originalClose.call(this);
    };
    URL.createObjectURL = (object: Blob | MediaSource) => {
      const url = originalUrlCreate(object);
      createdUrls++;
      liveUrls.add(url);
      return url;
    };
    URL.revokeObjectURL = (url: string) => {
      liveUrls.delete(url);
      return originalUrlRevoke(url);
    };
    Object.defineProperty(window, "__renderResources", {
      value: () => ({
        createdBitmaps,
        liveBitmaps: liveBitmaps.size,
        createdUrls,
        liveUrls: liveUrls.size,
      }),
    });
  });
  await page.goto("proof.html");
  await page.waitForFunction(() => Boolean(window.proof?.compiler.compilerVersion));

  const samples = await page.evaluate(async () => {
    const { proof } = window;
    const original = proof.job;
    const source = new TextDecoder().decode(original.files["/templates/settings.typ"]);
    if (!source.includes('image("assets/logo.png"')) throw Error("Logo source is missing");
    const settings = new TextEncoder().encode(
      source.replace('image("assets/logo.png"', 'image("assets/logo.svg"'),
    );
    const samples = [];
    for (let index = 0; index < 20; index++) {
      const color = `#${(index * 87121 + 0x204060).toString(16).padStart(6, "0")}`;
      const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="48" height="32"><rect width="48" height="32" fill="${color}"/></svg>`;
      const files = {
        ...original.files,
        "/templates/settings.typ": settings,
        "/templates/assets/logo.svg": new TextEncoder().encode(svg),
      };
      const revision = proof.compiler.submit({ ...original, files }, true);
      await new Promise<void>((resolve, reject) => {
        const started = performance.now();
        const poll = () => {
          const result = proof.results.find((item) => item.revision === revision);
          if (result?.timing?.committed) return resolve();
          if (result && !result.preview) return reject(Error(JSON.stringify(result.diagnostics)));
          if (performance.now() - started > 30000) return reject(Error("Preview timeout"));
          setTimeout(poll, 10);
        };
        poll();
      });
      const counters = (
        window as unknown as {
          __renderResources: () => {
            createdBitmaps: number;
            liveBitmaps: number;
            createdUrls: number;
            liveUrls: number;
          };
        }
      ).__renderResources();
      samples.push({ ...counters, viewer: proof.viewer.resources });
      proof.results.length = 0;
    }
    return samples;
  });

  expect(samples.at(-1)?.createdBitmaps).toBeGreaterThan(10);
  expect(samples.at(-1)?.createdUrls).toBeGreaterThan(10);
  for (const sample of samples) {
    expect(sample.liveBitmaps).toBe(0);
    expect(sample.liveUrls).toBe(0);
    expect(sample.viewer.documents).toBe(1);
    expect(sample.viewer.canvases).toBeGreaterThan(0);
    expect(sample.viewer.pending).toBe(0);
    expect(sample.viewer.preparing).toBe(0);
  }
});
