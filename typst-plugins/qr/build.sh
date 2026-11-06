#!/usr/bin/env bash
# Rebuild or verify the bundled QR plugin with the pinned toolchain.
set -euo pipefail
project=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=$(cd -- "$project/../.." && pwd)
mode=${1:-}
if [[ -n "$mode" && "$mode" != --check ]] || (( $# > 1 )); then
  printf 'Usage: %s [--check]\n' "$0" >&2
  exit 2
fi
toolchain=1.92.0
destination="$root/resources/typst/vendor/qr/qr.wasm"
cargo_dir=${CARGO_HOME:-"$HOME/.cargo"}
mkdir -p "$cargo_dir"
cargo_dir=$(cd -- "$cargo_dir" && pwd)
sysroot=$(rustc "+$toolchain" --print sysroot)
target=$(mktemp -d "${TMPDIR:-/tmp}/immuknow-qr-build.XXXXXX")
trap 'rm -rf -- "$target"' EXIT
printf -v CARGO_ENCODED_RUSTFLAGS '%s\x1f%s\x1f%s\x1f%s' \
  "--remap-path-prefix=$root=/immuknow" \
  "--remap-path-prefix=$cargo_dir=/cargo" \
  "--remap-path-prefix=$target=/target" \
  "--remap-path-prefix=$sysroot=/rust-toolchain"
export CARGO_ENCODED_RUSTFLAGS
unset RUSTFLAGS
export CARGO_TARGET_DIR="$target"
cd -- "$project"
cargo "+$toolchain" build --locked --release --target wasm32-unknown-unknown
built="$target/wasm32-unknown-unknown/release/immuknow_qr.wasm"
if [[ "$mode" == --check ]]; then
  cmp --silent "$built" "$destination" || { printf 'QR plugin differs; rebuild with typst-plugins/qr/build.sh\n' >&2; exit 1; }
  printf 'QR plugin verified: %s\n' "$destination"
else
  cp -- "$built" "$destination"
  printf 'QR plugin built: %s\n' "$destination"
fi
