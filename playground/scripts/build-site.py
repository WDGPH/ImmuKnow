"""Assemble documentation and playground into the one GitHub Pages artifact."""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    for command in (
        [sys.executable, "docs/generate_schema_docs.py"],
        [sys.executable, "-m", "mkdocs", "build", "--strict"],
        [sys.executable, "-m", "playground.scripts.examples", "--check"],
        ["npm", "run", "build", "--prefix", "playground"],
    ):
        subprocess.run(command, cwd=ROOT, check=True)
    shutil.copytree(
        ROOT / "playground/dist", ROOT / "site/playground", dirs_exist_ok=True
    )
    (ROOT / "site/.nojekyll").touch()


if __name__ == "__main__":
    main()
