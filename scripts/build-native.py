"""Build native distributions without modifying package source files."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from immuknow.build_info import native_typst_version  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "dist")
    parser.add_argument("--print-typst-version", action="store_true")
    args = parser.parse_args()
    if args.print_typst_version:
        print(native_typst_version(ROOT / "immuknow"))
        return
    subprocess.run(
        ["uv", "build", "--out-dir", str(args.out_dir.resolve())], cwd=ROOT, check=True
    )


if __name__ == "__main__":
    main()
