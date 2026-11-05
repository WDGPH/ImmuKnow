#!/usr/bin/env bash
# Build a native executable and package it with its license.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
out_dir=${1:-"$root/dist"}
mkdir -p -- "$out_dir"
out_dir=$(cd -- "$out_dir" && pwd)
cd -- "$root"
cargo build --release --locked
binary_dir=${CARGO_TARGET_DIR:-"$root/target"}/release
stage=$(mktemp -d "${TMPDIR:-/tmp}/immuknow-release.XXXXXX")
trap 'rm -rf -- "$stage"' EXIT
install -m 755 "$binary_dir/immuknow" "$stage/immuknow"
install -m 644 LICENSE "$stage/LICENSE"
archive="$out_dir/immuknow-$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m).tar.gz"
tar -czf "$archive" -C "$stage" immuknow LICENSE
printf 'Created %s\n' "$archive"
