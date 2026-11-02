"""Small unbranded projects for engine contract tests, never shipped as starters."""

import shutil
from pathlib import Path

from immuknow.resources import typst_library_root

TEMPLATES = Path(__file__).parent / "templates"


def copy_project(destination: Path) -> Path:
    shutil.copytree(TEMPLATES, destination)
    shutil.copytree(typst_library_root(), destination / "lib/immuknow")
    return destination
