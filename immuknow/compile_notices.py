"""Compile explicit render jobs with pinned Typst and a bounded file root.

Each command passes a JSON file reference rather than personal details. A PDF is
published only after its compilation succeeds. The orchestrator records each actual result before
inspection and delivery; metadata extraction never erases a useful PDF.
"""

from __future__ import annotations

import json
import subprocess
import re
from typing import Any
from pathlib import Path

from .data_models import CheckResult, ClientRecord, RenderJob

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
    """PDF compilation and evidence evaluation use identical frozen inputs."""
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
    job: RenderJob, typst_bin: str
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
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        partial.replace(job.pdf)
    finally:
        partial.unlink(missing_ok=True)
    return compiler_warnings(result.stderr)


def evaluate_render_job(
    job: RenderJob, typst_bin: str
) -> dict[str, Any]:
    """Read the required placed summary without interpreting component rules.

    This repeats layout on the same staged resources, font options, trusted
    identity and creation timestamp used for the PDF. A missing or malformed
    report raises while leaving the PDF available for review.
    """
    result = subprocess.run(
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
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        summaries = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("Compiler returned unreadable render evidence") from exc
    if not isinstance(summaries, list) or len(summaries) != 1:
        raise ValueError("Expected exactly one immuknow-report document summary")
    summary = summaries[0]
    if (
        not isinstance(summary, dict)
        or type(summary.get("schema_version")) is not int
        or summary["schema_version"] != 1
    ):
        raise ValueError("Unsupported or missing render evidence schema")
    identity = summary.get("identity")
    if not isinstance(identity, dict) or any(
        not isinstance(identity.get(key), str)
        for key in ("client_id", "version_id", "language")
    ):
        raise ValueError("Render evidence is missing document identity")
    if type(summary.get("page_count")) is not int or summary["page_count"] < 1:
        raise ValueError("Render evidence is missing actual page count")
    components = summary.get("components")
    known_components = {
        "page",
        "section",
        "header",
        "address",
        "client",
        "signature",
        "history",
        "overdue_diseases",
        "overdue_agents",
        "qr",
        "privacy",
    }
    if (
        not isinstance(components, dict)
        or not known_components <= components.keys()
        or any(type(value) is not bool for value in components.values())
    ):
        raise ValueError("Render evidence has invalid component presence")
    if not isinstance(summary.get("measurements"), dict):
        raise ValueError("Render evidence is missing measurements")
    urls = summary.get("qr_urls")
    if not isinstance(urls, list) or any(
        not isinstance(url, str) or not url for url in urls
    ):
        raise ValueError("Render evidence has invalid QR destinations")
    checks = summary.get("checks")
    if not isinstance(checks, list):
        raise ValueError("Render evidence is missing check results")
    for check in checks:
        if not isinstance(check, dict) or any(
            not isinstance(check.get(key), str) or not check[key]
            for key in ("code", "stage", "status", "message")
        ):
            raise ValueError("Render evidence contains an invalid check result")
        if check["status"] not in ("pass", "warn", "fail", "not_applicable", "not_run"):
            raise ValueError("Render evidence contains an unknown check status")
        if "page" in check and (type(check["page"]) is not int or check["page"] < 1):
            raise ValueError("Render evidence contains an invalid check page")
        if "measurements" in check and not isinstance(check["measurements"], dict):
            raise ValueError("Render evidence contains invalid check measurements")
        if "component" in check and not isinstance(check["component"], str):
            raise ValueError("Render evidence contains an invalid component name")
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
