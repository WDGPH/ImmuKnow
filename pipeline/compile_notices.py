"""Compile explicit render jobs with pinned Typst and a bounded file root.

Each command passes a JSON file reference rather than personal details. A PDF is
published only after its compilation succeeds. Whole-stage completion evidence
is written only after every job succeeds; downstream stages require that evidence.
"""

from __future__ import annotations

import os
import json
import subprocess
from pathlib import Path

from .config_loader import load_config
from .data_models import RenderJob
from .generate_notices import read_render_jobs

TYPST_VERSION = "0.15.1"


def check_compiler(typst_bin: str) -> None:
    """Require the tested stable compiler and explain how to select it."""
    try:
        result = subprocess.run(
            [typst_bin, "--version"], check=True, capture_output=True, text=True
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Typst executable not found: {typst_bin}. Install Typst {TYPST_VERSION} "
            "and select it through PATH, typst.bin, or TYPST_BIN."
        ) from exc
    if result.stdout.split()[:2] != ["typst", TYPST_VERSION]:
        raise RuntimeError(
            f"Unsupported compiler: {result.stdout.strip()}. Use Typst {TYPST_VERSION}; "
            "set typst.bin or TYPST_BIN to its executable."
        )


def compile_render_job(
    job: RenderJob, typst_bin: str, font_path: Path | None = None
) -> None:
    """Compile one static entry point, publishing its PDF only after success.

    Parameters
    ----------
    job : RenderJob
        Explicit template, JSON reference, bounded file root, and expected PDF.
    typst_bin : str
        Validated compiler executable.
    font_path : Path, optional
        Additional font directory.

    Raises
    ------
    subprocess.CalledProcessError
        If Typst rejects the data or document. No old or partial PDF survives.
    """
    job.pdf.parent.mkdir(parents=True, exist_ok=True)
    job.pdf.unlink(missing_ok=True)
    partial = job.pdf.with_suffix(".partial.pdf")
    partial.unlink(missing_ok=True)
    data_reference = "/" + job.data.relative_to(job.workspace).as_posix()
    command = [
        typst_bin,
        "compile",
        "--root",
        str(job.workspace),
        "--input",
        f"data={data_reference}",
    ]
    if font_path:
        command.extend(["--font-path", str(font_path)])
    command.extend([str(job.template), str(partial)])
    try:
        subprocess.run(command, check=True)
        partial.replace(job.pdf)
    finally:
        partial.unlink(missing_ok=True)


def compile_with_config(
    artifact_dir: Path,
    output_dir: Path,
    config_path: Path | None = None,
    template_dir: Path | None = None,
) -> int:
    """Compile Typst files using configuration from parameters.yaml.

    Reads typst configuration (binary path, font path) from parameters.yaml
    and compiles all Typst files in the artifact directory.

    Parameters
    ----------
    artifact_dir : Path
        Directory containing Typst template files
    output_dir : Path
        Directory where compiled PDFs will be written
    config_path : Path, optional
        Path to parameters.yaml. If not provided, uses default location.
    template_dir : Path, optional
        Template directory for dynamic template loading. Typst compilation always
        uses PROJECT_ROOT as --root to find both templates and output artifacts.

    Returns
    -------
    int
        Number of files compiled.
    """
    config = load_config(config_path)

    typst_config = config.get("typst", {})
    font_path_str = typst_config.get("font_path", "/usr/share/fonts/truetype/freefont/")
    typst_bin = typst_config.get("bin", "typst")

    # Allow TYPST_BIN environment variable to override config
    typst_bin = os.environ.get("TYPST_BIN", typst_bin)

    font_path = Path(font_path_str) if font_path_str else None

    jobs = read_render_jobs(artifact_dir)
    evidence_path = artifact_dir / "compilation.json"
    evidence_path.unlink(missing_ok=True)
    check_compiler(typst_bin)
    for job in jobs:
        if job.pdf.parent != output_dir.resolve():
            raise ValueError(
                f"Render job PDF directory differs from requested output: {job.pdf}"
            )
        job.pdf.unlink(missing_ok=True)
    for job in jobs:
        compile_render_job(job, typst_bin, font_path)
    evidence_path.write_text(
        json.dumps(
            {
                "compiler_version": TYPST_VERSION,
                "outputs": [str(job.pdf) for job in jobs],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return len(jobs)


def main(
    artifact_dir: Path,
    output_dir: Path,
    config_path: Path | None = None,
    template_dir: Path | None = None,
) -> int:
    """Main entry point for Typst compilation.

    Parameters
    ----------
    artifact_dir : Path
        Directory containing Typst artifacts.
    output_dir : Path
        Directory for output PDFs.
    config_path : Path, optional
        Path to parameters.yaml configuration file.
    template_dir : Path, optional
        Template directory containing conf.typ and assets/. Used as Typst --root.
        If not provided, defaults to project root.

    Returns
    -------
    int
        Number of files compiled.
    """
    compiled = compile_with_config(artifact_dir, output_dir, config_path, template_dir)
    if compiled:
        print(f"Compiled {compiled} Typst file(s) to PDFs in {output_dir}.")
    return compiled


if __name__ == "__main__":
    import sys

    print(
        "⚠️  Direct invocation: This module is typically executed via orchestrator.py.\n"
        "   Re-running a single step is valid when pipeline artifacts are retained on disk,\n"
        "   allowing you to skip earlier steps and regenerate output.\n"
        "   Note: Output will overwrite any previous files.\n"
        "\n"
        "   For typical usage, run: uv run viper <input> <language>\n",
        file=sys.stderr,
    )
    sys.exit(1)
