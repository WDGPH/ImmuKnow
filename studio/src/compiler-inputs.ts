import { safePath, validateFiles } from "./project";
import type { Files } from "./types";

export function sameBytes(a: Uint8Array | undefined, b: Uint8Array): boolean {
  if (a === b) return true;
  if (!a || a.length !== b.length) return false;
  // Compare aligned words without allocating/copying the font or image bytes.
  // Unaligned imported views and the final 0–3 bytes still compare bytewise.
  let offset = 0;
  if ((a.byteOffset | b.byteOffset) % 4 === 0) {
    const length = Math.floor(a.length / 4);
    const left = new Uint32Array(a.buffer, a.byteOffset, length);
    const right = new Uint32Array(b.buffer, b.byteOffset, length);
    for (let i = 0; i < length; i++) if (left[i] !== right[i]) return false;
    offset = length * 4;
  }
  for (let i = offset; i < a.length; i++) if (a[i] !== b[i]) return false;
  return true;
}

interface ShadowCompiler {
  reset_shadow(): void;
  map_shadow(path: string, bytes: Uint8Array): boolean;
  unmap_shadow(path: string): boolean;
}

// The comparison base is only the state actually applied in this worker. Every
// request is a complete immutable desired snapshot, so coalescing loses no delta.
export class ShadowFiles {
  private files: Files = {};
  private context?: number;
  constructor(private compiler: ShadowCompiler) {}
  reconcile(context: number, desired: Files) {
    let mappedFiles = 0,
      mappedBytes = 0,
      removedFiles = 0;
    if (this.context !== context) {
      this.compiler.reset_shadow();
      this.files = {};
      this.context = context;
    }
    try {
      for (const path of Object.keys(this.files)) {
        if (Object.hasOwn(desired, path)) continue;
        if (!this.compiler.unmap_shadow(path))
          throw new Error(`Could not remove project file: ${path}`);
        removedFiles++;
      }
      for (const [path, bytes] of Object.entries(desired)) {
        if (sameBytes(this.files[path], bytes)) continue;
        if (!this.compiler.map_shadow(path, bytes))
          throw new Error(`Could not map project file: ${path}`);
        mappedFiles++;
        mappedBytes += bytes.length;
      }
      this.files = desired;
    } catch (error) {
      this.compiler.reset_shadow();
      this.files = {};
      throw error;
    }
    return { mappedFiles, mappedBytes, removedFiles, retainedFiles: Object.keys(desired).length };
  }
}

export function validateSnapshot(files: Files) {
  const relative: Files = {};
  for (const [path, bytes] of Object.entries(files)) {
    if (!path.startsWith("/"))
      throw new Error(`Project path must be an absolute shadow path: ${path}`);
    relative[safePath(path.slice(1))] = bytes;
  }
  validateFiles(relative);
}
