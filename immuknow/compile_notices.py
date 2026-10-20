"""Compile explicit render jobs with pinned Typst and a bounded file root.

Each command passes a JSON file reference rather than personal details. A PDF is
published only after its compilation succeeds. The orchestrator records each actual result before
inspection and delivery; metadata extraction never erases a useful PDF.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from .data_models import CheckResult, ClientRecord, RenderJob
from .structured_input import parse_json, read_json
from .render_contract import validate_render_report

TYPST_VERSION = "0.15.1"


@dataclass(frozen=True)
class CompilerTimeouts:
    """Wall-clock limits in seconds for separate native compiler operations."""

    version: float = 10
    compile: float = 120
    evidence: float = 120
    review: float = 60

    @classmethod
    def from_config(cls, settings: Any) -> CompilerTimeouts:
        """Resolve explicit limits; reject unbounded, mistyped or unknown settings."""
        defaults = asdict(cls())
        if not isinstance(settings, dict) or set(settings) - defaults.keys():
            raise ValueError(
                "typst.timeouts_seconds must contain only version, compile, evidence and review"
            )
        resolved = defaults | settings
        for operation, value in resolved.items():
            _validate_timeout(value, f"typst.timeouts_seconds.{operation}")
        return cls(**resolved)


class CompilerTimeoutError(TimeoutError):
    """A native operation exceeded its deadline; its subprocess was terminated."""


def _validate_timeout(value: Any, name: str) -> None:
    if type(value) not in (int, float) or not 0 < value <= 86400:
        raise ValueError(
            f"{name} must be a finite number of seconds above 0 and at most 86400"
        )


def run_typst(
    command: list[str], *, timeout: float, operation: str
) -> subprocess.CompletedProcess[str]:
    """Run with a deadline, private package paths and package downloads disabled.

    Typst 0.15.1 has no offline flag. Its downloader reads the configured CA
    certificate before opening a connection and fails on invalid certificate
    bytes. Keep that failure deliberate and local, alongside empty package paths.
    Real compiler tests cover both cached imports and attempted network access.
    """
    _validate_timeout(timeout, f"Typst {operation} timeout")
    try:
        with TemporaryDirectory(prefix="immuknow-typst-") as temporary:
            isolated = Path(temporary)
            packages = isolated / "packages"
            packages.mkdir()
            certificate = isolated / "downloads-disabled.pem"
            certificate.write_text(
                "Package downloads are disabled.\n", encoding="utf-8"
            )
            environment = os.environ.copy()
            environment.update(
                TYPST_PACKAGE_PATH=str(packages),
                TYPST_PACKAGE_CACHE_PATH=str(packages),
                TYPST_CERT=str(certificate),
            )
            return subprocess.run(
                command,
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=environment,
            )
    except subprocess.CalledProcessError as exc:
        if any(
            message in (exc.stderr or "")
            for message in (
                "failed to download package",
                "package not found",
            )
        ):
            exc.stderr = (
                "Package imports are not supported. Copy dependencies into the project "
                "and use relative paths.\n" + exc.stderr
            )
        raise
    except subprocess.TimeoutExpired as exc:
        raise CompilerTimeoutError(
            f"Typst {operation} exceeded its {timeout:g}-second deadline. "
            "Check the template or increase the corresponding typst.timeouts_seconds setting."
        ) from exc


def check_compiler(typst_bin: str, *, timeout: float = CompilerTimeouts.version) -> str:
    """Require the tested stable compiler and explain how to select it."""
    try:
        result = run_typst(
            [typst_bin, "--version"], timeout=timeout, operation="version probe"
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
    return result.stdout.strip()


def compiler_warnings(stderr: str) -> list[CheckResult]:
    """Retain compiler warning detail beside the component findings."""
    warnings = []
    for message in re.split(r"(?m)^warning: ", stderr)[1:]:
        message = message.strip()
        code = "compiler.warning"
        if "unknown font family" in message:
            code = "compiler.font_substitution"
        elif "did not converge" in message:
            code = "compiler.layout_nonconvergent"
        warnings.append(CheckResult(code, "render", "warn", message))
    return warnings


def compiler_options(job: RenderJob) -> list[str]:
    """PDF compilation and evidence evaluation use the same project inputs."""
    options = [
        "--root",
        str(job.workspace),
        "--input",
        "data=/" + job.data.relative_to(job.workspace).as_posix(),
        "--input",
        f"notice-template={job.template.name}",
        "--input",
        f"notice-version={job.version_id}",
        "--input",
        f"notice-language={job.language}",
        "--creation-timestamp",
        str(job.creation_timestamp),
    ]
    return options


def compile_render_job(
    job: RenderJob,
    typst_bin: str,
    *,
    timeout: float = CompilerTimeouts.compile,
) -> list[CheckResult]:
    """Publish one PDF after successful compilation, retaining compiler warnings.

    Failures carry full stdout/stderr in CalledProcessError. Evidence extraction
    is separate so its failure cannot erase a successfully compiled notice.
    """
    job.pdf.parent.mkdir(parents=True, exist_ok=True)
    job.pdf.unlink(missing_ok=True)
    partial = job.pdf.with_suffix(".partial.pdf")
    partial.unlink(missing_ok=True)
    command = [
        typst_bin,
        "compile",
        *compiler_options(job),
        str(job.template),
        str(partial),
    ]
    try:
        result = run_typst(command, timeout=timeout, operation="notice compilation")
        partial.replace(job.pdf)
    finally:
        partial.unlink(missing_ok=True)
    return compiler_warnings(result.stderr)


def evaluate_render_job(
    job: RenderJob,
    typst_bin: str,
    *,
    timeout: float = CompilerTimeouts.evidence,
) -> dict[str, Any]:
    """Read the required placed summary without interpreting component rules.

    This repeats layout on the same staged resources, font options, trusted
    identity and creation timestamp used for the PDF. A missing or malformed
    report raises while leaving the PDF available for review.
    """
    result = run_typst(
        [
            typst_bin,
            "eval",
            *compiler_options(job),
            "--in",
            str(job.template),
            "query(<immuknow-report>).map(it => it.value)",
            "--format",
            "json",
        ],
        timeout=timeout,
        operation="evidence evaluation",
    )
    try:
        summaries = parse_json(result.stdout)
    except ValueError as exc:
        raise ValueError("Compiler returned unreadable render evidence") from exc
    if not isinstance(summaries, list) or len(summaries) != 1:
        raise ValueError("Expected exactly one immuknow-report document summary")
    summary = summaries[0]
    notice = read_json(job.data)
    expected = {
        "row_key": job.sequence,
        "template": job.template.name,
        "client_id": job.client_id,
        "version_id": job.version_id,
        "language": job.language,
    }
    if not isinstance(notice, dict) or any(
        notice.get(key) != value for key, value in expected.items()
    ):
        raise ValueError("Prepared notice does not match the selected render job")
    validate_render_report(summary, notice)
    checks = summary["checks"]
    # Layout may issue a warning during either evaluation. Store each instance once.
    for warning in compiler_warnings(result.stderr):
        if warning.to_dict() not in checks:
            checks.append(warning.to_dict())
    return summary


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
