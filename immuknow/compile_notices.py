"""Compile explicit render jobs with pinned Typst and a bounded file root.

Each command passes a JSON file reference rather than personal details. A PDF is
published only after its compilation succeeds. Whole-stage completion evidence
is written only after every job succeeds. The orchestrator then checks the files
before validation and delivery.
"""

from __future__ import annotations

import os
import json
import subprocess
from pathlib import Path

from .data_models import ClientRecord, RenderJob

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


def check_expected_notices(
    clients: list[ClientRecord], jobs: list[RenderJob], *, require_files: bool = False
) -> None:
    """Require exactly one uniquely named render job for each prepared client."""
    expected = [
        (client.sequence, client.client_id, client.language, client.version_id)
        for client in clients
    ]
    actual = [
        (job.sequence, job.client_id, job.language, job.version_id) for job in jobs
    ]
    if (
        len(set(expected)) != len(expected)
        or len(set(actual)) != len(actual)
        or set(expected) != set(actual)
        or len({job.pdf for job in jobs}) != len(jobs)
    ):
        raise ValueError(
            "Render jobs do not match the prepared client list exactly once"
        )
    if require_files:
        for job in jobs:
            if not job.pdf.is_file():
                raise FileNotFoundError(f"Expected notice PDF is missing: {job.pdf}")


def compile_notices(jobs: list[RenderJob], artifact_dir: Path, config: dict) -> int:
    """Compile the complete expected set and record success only after every job."""
    settings = config.get("typst", {})
    typst_bin = os.environ.get("TYPST_BIN", settings.get("bin", "typst"))
    font_path = settings.get("font_path", "/usr/share/fonts/truetype/freefont/")
    evidence_path = artifact_dir / "compilation.json"
    evidence_path.unlink(missing_ok=True)
    for job in jobs:
        job.pdf.unlink(missing_ok=True)
    check_compiler(typst_bin)
    for job in jobs:
        compile_render_job(job, typst_bin, Path(font_path) if font_path else None)
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
