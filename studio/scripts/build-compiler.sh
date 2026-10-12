#!/usr/bin/env bash
# Reuse the verified local compiler, or build the source pinned by Studio metadata.
set -euo pipefail
studio_root=$(cd "$(dirname "$0")/.." && pwd)
pin_values=$(python - "$studio_root/compiler-pins.json" <<'PY'
import hashlib, json, pathlib, sys
compiler = json.load(open(sys.argv[1]))['browser_compiler']
print(compiler['source_revision'])
print(compiler['rust_version'])
print(compiler['wasm_bindgen_version'])
print(','.join(compiler['features']))
build_root = pathlib.Path(sys.argv[1]).resolve().parent.parent
for name in ('cache', 'preview'):
    patch = build_root / f'studio/scripts/patches/compiler-{name}.patch'
    assert hashlib.sha256(patch.read_bytes()).hexdigest() == compiler[f'{name}_patch_sha256'], f'{name} patch differs from build identity'
renderer = json.load(open(sys.argv[1]))['browser_renderer']
assert renderer['source_revision'] == compiler['source_revision'], 'Renderer source revision differs'
assert renderer['rust_version'] == compiler['rust_version'], 'Renderer Rust version differs'
assert renderer['wasm_bindgen_version'] == compiler['wasm_bindgen_version'], 'Renderer bindgen version differs'
renderer_patch = build_root / 'studio/scripts/patches/renderer-canvas.patch'
assert hashlib.sha256(renderer_patch.read_bytes()).hexdigest() == renderer['canvas_patch_sha256'], 'Renderer patch differs from build identity'
print(','.join(renderer['features']))
PY
)
mapfile -t pins <<< "$pin_values"
revision=${pins[0]}
rust_version=${pins[1]}
bindgen_version=${pins[2]}
features=${pins[3]}
renderer_features=${pins[4]}
cache_patch="$studio_root/scripts/patches/compiler-cache.patch"
preview_patch="$studio_root/scripts/patches/compiler-preview.patch"
renderer_patch="$studio_root/scripts/patches/renderer-canvas.patch"
artifact="$studio_root/vendor/compiler"
renderer_artifact="$studio_root/vendor/renderer"
# License notices need the pinned checkout even when a verified WASM artifact
# is restored without its source/cache directory.
build_dir="${IMMUKNOW_COMPILER_BUILD_DIR:-$studio_root/.compiler-build}"
if [ ! -d "$build_dir/.git" ]; then git clone https://github.com/Myriad-Dreamin/typst.ts.git "$build_dir"; fi
git -C "$build_dir" checkout --detach "$revision"
test -z "$(git -C "$build_dir" status --porcelain)"
python - "$build_dir/Cargo.toml" "$studio_root/compiler-pins.json" <<'PY'
import json, sys, tomllib
with open(sys.argv[1], 'rb') as manifest:
    version = tomllib.load(manifest)['workspace']['package']['version']
build = json.load(open(sys.argv[2]))
assert version == build['browser_compiler']['crate_version'] == build['browser_renderer']['crate_version'], 'Pinned compiler/renderer crate version differs'
PY
verified=false
if [ -f "$artifact/build-inputs.json" ] && [ -f "$artifact/source-revision.txt" ] && [ "$(cat "$artifact/source-revision.txt")" = "$revision" ] && python - "$studio_root/compiler-pins.json" "$artifact/build-inputs.json" <<'PY'
import json, sys
sys.exit(0 if json.load(open(sys.argv[1]))['browser_compiler'] == json.load(open(sys.argv[2])) else 1)
PY
then
  if (cd "$artifact" && sha256sum --check SHA256SUMS); then verified=true; fi
fi
if [ "$verified" = false ]; then
  if ! command -v rustup >/dev/null || ! command -v cargo >/dev/null; then
    echo "Compiler build requires Rust/rustup on PATH. See docs/developer_guide/testing.md." >&2
    exit 1
  fi
  if ! command -v wasm-bindgen >/dev/null || [ "$(wasm-bindgen --version)" != "wasm-bindgen $bindgen_version" ]; then
    echo "Compiler build requires wasm-bindgen $bindgen_version. Install with:" >&2
    echo "  rustup toolchain install $rust_version --profile minimal" >&2
    echo "  cargo +$rust_version install --locked wasm-bindgen-cli --version $bindgen_version" >&2
    exit 1
  fi
  rustup toolchain install "$rust_version" --profile minimal --component rust-src --target wasm32-unknown-unknown
  git -C "$build_dir" apply --check "$cache_patch"
  git -C "$build_dir" apply --check "$preview_patch"
  git -C "$build_dir" apply "$cache_patch"
  trap 'git -C "$build_dir" apply --reverse "$cache_patch"' EXIT
  git -C "$build_dir" apply "$preview_patch"
  trap 'git -C "$build_dir" apply --reverse "$preview_patch"; git -C "$build_dir" apply --reverse "$cache_patch"' EXIT
  (cd "$build_dir" && cargo +"$rust_version" build --locked --release --target wasm32-unknown-unknown -p typst-ts-web-compiler --no-default-features --features "$features")
  git -C "$build_dir" apply --reverse "$preview_patch"
  trap 'git -C "$build_dir" apply --reverse "$cache_patch"' EXIT
  git -C "$build_dir" apply --reverse "$cache_patch"
  trap - EXIT
  mkdir -p "$artifact"
  wasm-bindgen --target web --out-dir "$artifact" "$build_dir/target/wasm32-unknown-unknown/release/typst_ts_web_compiler.wasm"
  cp "$build_dir/LICENSE" "$artifact/LICENSE"
  printf '%s\n' "$revision" > "$artifact/source-revision.txt"
  python - "$studio_root/compiler-pins.json" "$artifact/build-inputs.json" <<'PY'
import json, sys
with open(sys.argv[2], 'w') as output:
    json.dump(json.load(open(sys.argv[1]))['browser_compiler'], output, indent=2)
    output.write('\n')
PY
  (cd "$artifact" && sha256sum typst_ts_web_compiler.js typst_ts_web_compiler_bg.wasm > SHA256SUMS)
fi
renderer_verified=false
if [ -s "$renderer_artifact/build-inputs.json" ] && python - "$studio_root/compiler-pins.json" "$renderer_artifact/build-inputs.json" <<'PY'
import json, sys
sys.exit(0 if json.load(open(sys.argv[1]))['browser_renderer'] == json.load(open(sys.argv[2])) else 1)
PY
then
  if (cd "$renderer_artifact" && sha256sum --check SHA256SUMS); then renderer_verified=true; fi
fi
if [ "$renderer_verified" = false ]; then
  if ! command -v rustup >/dev/null || ! command -v cargo >/dev/null; then
    echo "Renderer build requires Rust/rustup on PATH. See docs/developer_guide/testing.md." >&2
    exit 1
  fi
  if ! command -v wasm-bindgen >/dev/null || [ "$(wasm-bindgen --version)" != "wasm-bindgen $bindgen_version" ]; then
    echo "Renderer build requires wasm-bindgen $bindgen_version. See docs/developer_guide/testing.md." >&2
    exit 1
  fi
  rustup toolchain install "$rust_version" --profile minimal --component rust-src --target wasm32-unknown-unknown
  git -C "$build_dir" apply --check "$renderer_patch"
  git -C "$build_dir" apply "$renderer_patch"
  trap 'git -C "$build_dir" apply --reverse "$renderer_patch"' EXIT
  (cd "$build_dir" && cargo +"$rust_version" build --locked --release --target wasm32-unknown-unknown -p typst-ts-renderer --no-default-features --features "$renderer_features")
  git -C "$build_dir" apply --reverse "$renderer_patch"
  trap - EXIT
  mkdir -p "$renderer_artifact"
  wasm-bindgen --target web --out-dir "$renderer_artifact" "$build_dir/target/wasm32-unknown-unknown/release/typst_ts_renderer.wasm"
  cp "$build_dir/LICENSE" "$renderer_artifact/LICENSE"
  python - "$studio_root/compiler-pins.json" "$renderer_artifact/build-inputs.json" <<'PY'
import json, sys
with open(sys.argv[2], 'w') as output:
    json.dump(json.load(open(sys.argv[1]))['browser_renderer'], output, indent=2)
    output.write('\n')
PY
  (cd "$renderer_artifact" && sha256sum typst_ts_renderer.js typst_ts_renderer_bg.wasm > SHA256SUMS)
fi
mkdir -p "$studio_root/public/generated/compiler"
cp "$artifact/LICENSE" "$artifact/SHA256SUMS" "$artifact/source-revision.txt" "$artifact/build-inputs.json" "$studio_root/public/generated/compiler/"
mkdir -p "$studio_root/public/generated/renderer"
cp "$renderer_artifact/LICENSE" "$renderer_artifact/SHA256SUMS" "$renderer_artifact/build-inputs.json" "$studio_root/public/generated/renderer/"
