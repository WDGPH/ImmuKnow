"""Prepare a run's output directory while preserving its logs."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable, Optional


def purge_output_directory(output_dir: Path, log_dir: Path) -> None:
    """Remove prior outputs, preserving logs from earlier runs."""

    resolved_log_dir = log_dir.resolve()
    for child in output_dir.iterdir():
        if child.resolve() == resolved_log_dir:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink(missing_ok=True)


def default_prompt(output_dir: Path) -> bool:
    """Ask before removing existing output files."""
    print("")
    print(f"⚠️  Output directory already exists: {output_dir}")
    response = input("Delete contents (except logs) and proceed? [y/N] ")
    return response.strip().lower() in {"y", "yes"}


def prepare_output_directory(
    output_dir: Path,
    log_dir: Path,
    auto_remove: bool,
    prompt: Optional[Callable[[Path], bool]] = None,
) -> bool:
    """Create a clean workspace or return False if the user declines cleanup."""

    prompt_callable = prompt or default_prompt

    if output_dir.exists():
        if not auto_remove and not prompt_callable(output_dir):
            print("❌ Pipeline cancelled. No changes made.")
            return False
        purge_output_directory(output_dir, log_dir)
    else:
        output_dir.mkdir(parents=True, exist_ok=True)

    log_dir.mkdir(parents=True, exist_ok=True)
    return True
