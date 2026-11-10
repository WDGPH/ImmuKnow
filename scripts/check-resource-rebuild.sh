#!/usr/bin/env bash
# Check resource-only edit/add/remove rebuilds without changing this checkout.
set -euo pipefail

repo=$(git -C "$(dirname "$0")/.." rev-parse --show-toplevel)
target=${CARGO_TARGET_DIR:-"$repo/target"}
if [[ "$target" != /* ]]; then
  target="$PWD/$target"
fi
scratch=$(mktemp -d "${TMPDIR:-/tmp}/immuknow-resource-rebuild.XXXXXX")
trap 'rm -rf -- "$scratch"' EXIT
mkdir "$scratch/source"
git -C "$repo" ls-files -z | tar -C "$repo" --null -T - -cf - | tar -C "$scratch/source" -xf -

build_export() {
  local stage=$1
  (cd "$scratch/source" && CARGO_TARGET_DIR="$target" cargo build --release --locked)
  "$target/release/immuknow" resources --output "$scratch/$stage" > "$scratch/$stage.json"
}

build_export baseline
resource="$scratch/source/resources/typst/README.md"
cp "$resource" "$scratch/original-readme"
printf '\nResource rebuild check.\n' >> "$resource"
build_export edited
cmp "$resource" "$scratch/edited/typst/README.md"
if cmp -s "$scratch/baseline.json" "$scratch/edited.json"; then
  echo 'Resource edit did not change the exported identity.' >&2
  exit 1
fi

probe="$scratch/source/resources/rebuild-probe.txt"
printf 'Fictional resource rebuild probe.\n' > "$probe"
build_export added
cmp "$probe" "$scratch/added/rebuild-probe.txt"
rm "$probe"
cp "$scratch/original-readme" "$resource"
build_export restored
test ! -e "$scratch/restored/rebuild-probe.txt"
cmp "$scratch/baseline.json" "$scratch/restored.json"
cmp "$scratch/baseline/resource-manifest.json" "$scratch/restored/resource-manifest.json"
echo 'Resource-only edit, addition and removal all refreshed the executable exports.'
