#!/usr/bin/env bash
# Build the browser compiler from an immutable source and its Cargo.lock.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
build_dir="${IMMUKNOW_COMPILER_BUILD_DIR:-$root/.compiler-build}"
revision=9739d81c5eaee02d2dc9c4e691262a3f6758cdc4
if [ ! -d "$build_dir/.git" ]; then
  git clone https://github.com/Myriad-Dreamin/typst.ts.git "$build_dir"
fi
git -C "$build_dir" checkout --detach "$revision"
test -z "$(git -C "$build_dir" status --porcelain)"
rustup toolchain install 1.92.0 --profile minimal --component rust-src --target wasm32-unknown-unknown
cd "$build_dir"
cargo +1.92.0 build --locked --release --target wasm32-unknown-unknown \
  -p typst-ts-web-compiler --no-default-features --features web,pdf
test "$(wasm-bindgen --version)" = 'wasm-bindgen 0.2.118'
mkdir -p "$root/vendor/compiler"
wasm-bindgen --target web --out-dir "$root/vendor/compiler" \
  target/wasm32-unknown-unknown/release/typst_ts_web_compiler.wasm
cp LICENSE "$root/vendor/compiler/LICENSE"
printf '%s\n' "$revision" > "$root/vendor/compiler/source-revision.txt"
cd "$root/vendor/compiler"
sha256sum typst_ts_web_compiler.js typst_ts_web_compiler_bg.wasm > SHA256SUMS
mkdir -p "$root/public/generated/compiler"
cp LICENSE SHA256SUMS source-revision.txt "$root/public/generated/compiler/"
