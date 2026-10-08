"""Remove configured intermediate outputs after the full cohort succeeds."""

import shutil
from pathlib import Path


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
