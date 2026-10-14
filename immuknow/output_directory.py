"""Create a separate private workspace for each run; retain original evidence."""

from __future__ import annotations

import shutil
from pathlib import Path


def prepare_run_directory(output_dir: Path, run_id: str) -> Path:
    """Never clear previous runs or installed resources."""
    output_dir.mkdir(parents=True, exist_ok=True)
    run_dir = output_dir / run_id
    run_dir.mkdir(mode=0o700)
    for name in (
        "originals",
        "facts",
        "resources",
        "encrypted",
        "bundles",
        "logs",
        "work",
    ):
        (run_dir / name).mkdir(mode=0o700)
    return run_dir


def cleanup_output(run_dir: Path, config: dict) -> None:
    """Only disposable work may be removed by the existing cleanup setting."""
    if not run_dir.is_dir():
        raise ValueError(f"The path {run_dir} is not a valid directory.")
    if config.get("pipeline", {}).get("after_run", {}).get("remove_artifacts", False):
        shutil.rmtree(run_dir / "work", ignore_errors=False)
