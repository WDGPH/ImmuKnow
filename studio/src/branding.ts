import { MAX_FILE } from "./project";

export async function imageBytes(file: File): Promise<Uint8Array> {
  if (!["image/png", "image/jpeg", "image/webp", "image/svg+xml"].includes(file.type))
    throw new Error("Choose a PNG, JPEG, WebP, or SVG image.");
  if (file.size > MAX_FILE) throw new Error("Images must be smaller than 12 MB.");
  const url = URL.createObjectURL(file);
  try {
    const image = new Image();
    image.src = url;
    await image.decode();
    if (image.naturalWidth * image.naturalHeight > 16_000_000)
      throw new Error("Images must contain at most 16 megapixels.");
    return new Uint8Array(await file.arrayBuffer());
  } finally {
    URL.revokeObjectURL(url);
  }
}

export function relativeImage(settings: string, asset: string): string {
  const from = settings.split("/").slice(0, -1),
    to = asset.split("/");
  while (from.length && to.length && from[0] === to[0]) {
    from.shift();
    to.shift();
  }
  return [...from.map(() => ".."), ...to].join("/");
}
export function imagePath(settings: string, relative: string): string | undefined {
  const parts = relative.startsWith("/") ? [] : settings.split("/").slice(0, -1);
  for (const part of relative.split("/")) {
    if (!part || part === ".") continue;
    if (part === "..") {
      if (!parts.length) return undefined;
      parts.pop();
    } else parts.push(part);
  }
  return parts.join("/");
}
