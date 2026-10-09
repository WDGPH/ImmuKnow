"""Prepare output directories before a run and clean up after successful delivery.

Preparation clears prior outputs while preserving logs, with a prompt when
configured. Final cleanup removes only the intermediate files selected by
run settings. The orchestrator calls these operations at opposite ends of
the workflow; they share ownership of output files, not execution timing.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable, Optional


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


def cleanup_output(output_dir: Path, config: dict) -> None:
    """Remove configured intermediate files after successful delivery."""
    if not output_dir.is_dir():
        raise ValueError(f"The path {output_dir} is not a valid directory.")
    pipeline_config = config.get("pipeline", {})
    after_run_config = pipeline_config.get("after_run", {})
    encryption_enabled = config.get("encryption", {}).get("enabled", False)
    bundling_config = config.get("bundling", {})
    bundle_size = bundling_config.get("bundle_size", 0)
    bundling_enabled = bundle_size > 0

    remove_artifacts = after_run_config.get("remove_artifacts", False)
    remove_unencrypted = after_run_config.get("remove_unencrypted_pdfs", False)

    # Remove artifacts directory if configured
    if remove_artifacts:
        safe_delete(output_dir / "artifacts")

    # Keep individual PDFs unless encryption or bundling provided delivery copies.
    if remove_unencrypted and (encryption_enabled or bundling_enabled):
        pdf_dir = output_dir / "pdf_individual"
        if pdf_dir.exists():
            for pdf_file in pdf_dir.glob("*.pdf"):
                # Only delete non-encrypted PDFs (skip _encrypted versions)
                if not pdf_file.stem.endswith("_encrypted"):
                    safe_delete(pdf_file)


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


def safe_delete(path: Path):
    """Safely delete a file or directory if it exists.

    Parameters
    ----------
    path : Path
        File or directory to delete.
    """
    if path.exists():
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
