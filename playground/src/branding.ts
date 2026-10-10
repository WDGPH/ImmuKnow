import { MAX_FILE } from "./project";

export async function brandingPNG(file: File): Promise<Uint8Array> {
  if (!["image/png", "image/jpeg", "image/webp"].includes(file.type))
    throw new Error("Choose a PNG, JPEG, or WebP image.");
  if (file.size > MAX_FILE) throw new Error("Branding images must be smaller than 8 MiB.");
  const bitmap = await createImageBitmap(file);
  try {
    if (bitmap.width * bitmap.height > 16_000_000)
      throw new Error("Branding images must contain at most 16 megapixels.");
    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("This browser cannot prepare images.");
    context.drawImage(bitmap, 0, 0);
    const png = await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob(
        (blob) => (blob ? resolve(blob) : reject(new Error("Image conversion failed."))),
        "image/png",
      ),
    );
    if (png.size > MAX_FILE) throw new Error("Converted PNG exceeds the 8 MiB project file limit.");
    return new Uint8Array(await png.arrayBuffer());
  } finally {
    bitmap.close();
  }
}
