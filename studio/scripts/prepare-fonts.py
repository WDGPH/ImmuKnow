"""Copy the web app's preview fonts after checksum verification.

No downloads or font-name inference: the preview manifest and family catalog are
also used by Studio compilation and complete project export.
"""

from __future__ import annotations

import argparse
import json
import shutil
from hashlib import sha256
from pathlib import Path

from immuknow.generate_notices import reject_overlap

ROOT = Path(__file__).resolve().parents[2]


def prepare_fonts(source: Path, destination: Path) -> dict[str, str]:
    """Verify the complete supported set before replacing disposable generated files."""
    source, destination = source.resolve(), destination.resolve()
    reject_overlap(source, destination)
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest.items():
        if sha256((source / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Supplied font file has changed: {name}")
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination, copy_function=shutil.copyfile)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--destination", type=Path, default=ROOT / "studio/public/generated/fonts"
    )
    args = parser.parse_args()
    source = ROOT / "studio/assets/fonts"
    manifest = prepare_fonts(source, args.destination)
    print(f"Verified and copied {len(manifest)} preview fonts")


if __name__ == "__main__":
    main()
