"""Build one local documentation/Studio artifact with its browser compiler.

This command prepares files only; publication is a separate workflow. Install
locked Python/npm dependencies first. The pinned compiler build is reused when
its source, toolchain and file hashes match.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--compiler-source",
        type=Path,
        default=Path(
            os.environ.get(
                "IMMUKNOW_COMPILER_BUILD_DIR", ROOT / "studio/.compiler-build"
            )
        ),
        help="Pinned compiler checkout used for building and license notices",
    )
    args = parser.parse_args()
    missing = [tool for tool in ("rustup", "cargo") if shutil.which(tool) is None]
    if missing:
        raise SystemExit(
            f"Studio build prerequisites missing from PATH: {', '.join(missing)}.\n"
            "Install Rust via https://rust-lang.org/tools/install/ and load its "
            "shell environment. See docs/developer_guide/testing.md for pinned "
            "toolchain setup. Rust is needed to prepare assets, not to serve them."
        )
    subprocess.run(
        ["bash", "studio/scripts/build-compiler.sh"],
        cwd=ROOT,
        check=True,
        env={
            **os.environ,
            "IMMUKNOW_COMPILER_BUILD_DIR": str(args.compiler_source.resolve()),
        },
    )
    for command in (
        [
            sys.executable,
            "-m",
            "studio.scripts.notices",
            "--compiler-source",
            str(args.compiler_source.resolve()),
        ],
        [sys.executable, "-m", "studio.scripts.examples", "--check"],
        [sys.executable, "docs/generate_schema_docs.py"],
        [sys.executable, "-m", "mkdocs", "build", "--strict"],
        ["npm", "run", "build", "--prefix", "studio"],
    ):
        subprocess.run(command, cwd=ROOT, check=True)
    shutil.copytree(ROOT / "studio/dist", ROOT / "site/studio", dirs_exist_ok=True)
    (ROOT / "site/.nojekyll").touch()
    print(f"Complete local artifact: {ROOT / 'site'}")


if __name__ == "__main__":
    main()
