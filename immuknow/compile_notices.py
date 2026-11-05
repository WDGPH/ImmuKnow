"""Compile explicit render jobs with pinned Typst and a bounded file root.

Each notice compiles once with its placed report. Internal evidence is removed
before PDF publication; invalid reports retain a sanitized readable original.
The orchestrator records the actual PDF and findings before delivery.
"""

from __future__ import annotations

import os
from io import BytesIO
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    IndirectObject,
    StreamObject,
    TextStringObject,
)

from .data_models import CheckResult, ClientRecord, RenderJob
from .structured_input import parse_json, read_json
from .render_contract import validate_render_report

TYPST_VERSION = "0.15.1"


@dataclass(frozen=True)
class CompilerTimeouts:
    """Wall-clock limits in seconds for separate native compiler operations."""

    version: float = 10
    compile: float = 120

    @classmethod
    def from_config(cls, settings: Any) -> CompilerTimeouts:
        """Resolve explicit limits; reject unbounded, mistyped or unknown settings."""
        defaults = asdict(cls())
        if not isinstance(settings, dict) or set(settings) - defaults.keys():
            raise ValueError(
                "typst.timeouts_seconds must contain only version and compile"
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
    """Freeze project inputs and identity for one notice compilation."""
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


EVIDENCE_ATTACHMENT = "immuknow-evidence.json"


def _strip_evidence(content: bytes) -> tuple[bytes, list[bytes], bool]:
    """Remove evidence from the reader before cloning any reachable PDF objects."""
    reader = PdfReader(BytesIO(content), strict=True)
    names = reader.root_object.get("/Names")
    if names is not None:
        names = names.get_object()
        if not isinstance(names, DictionaryObject):
            raise ValueError("PDF attachment name tree is invalid")
        embedded = names.get("/EmbeddedFiles")
        if embedded is not None:
            embedded = embedded.get_object()
            if not isinstance(embedded, DictionaryObject) or "/Kids" in embedded:
                raise ValueError("PDF attachment name tree is unsupported")
            entries = embedded.get("/Names", ArrayObject()).get_object()
            if not isinstance(entries, ArrayObject) or len(entries) % 2:
                raise ValueError("PDF attachment name tree is invalid")
            for index in range(0, len(entries), 2):
                if not isinstance(
                    entries[index].get_object(), TextStringObject
                ) or not isinstance(entries[index + 1].get_object(), DictionaryObject):
                    raise ValueError("PDF attachment name tree is invalid")
    reserved = [
        item for item in reader.attachment_list if item.name == EVIDENCE_ATTACHMENT
    ]
    payloads: list[bytes] = []
    unreadable = False
    specs = {id(item.pdf_object) for item in reserved}
    for item in reserved:
        try:
            payloads.append(item.content)
        except (ValueError, KeyError, PdfReadError):
            unreadable = True
        files = item.pdf_object.get("/EF")
        if files is None:
            raise ValueError("PDF evidence attachment is invalid")
        files = files.get_object()
        if not isinstance(files, DictionaryObject) or not files:
            raise ValueError("PDF evidence attachment is invalid")
        for value in files.values():
            stream = value.get_object()
            if not isinstance(stream, StreamObject):
                raise ValueError("PDF evidence stream is invalid")
            stream.set_data(b"")
        item.delete()

    # A file specification may also be associated with a page or structure
    # element via /AF. Scrub all associated references, including aliases.
    visited: set[int] = set()

    def remove_associations(value: Any) -> None:
        if isinstance(value, IndirectObject):
            value = value.get_object()
        if (
            not isinstance(value, (DictionaryObject, ArrayObject))
            or id(value) in visited
        ):
            return
        visited.add(id(value))
        if isinstance(value, DictionaryObject):
            if (
                "/EF" in value
                and any(value.get(key) == EVIDENCE_ATTACHMENT for key in ("/F", "/UF"))
                and id(value) not in specs
            ):
                raise ValueError("PDF contains unlisted render evidence")
            associated = value.get("/AF")
            if associated is not None:
                associated = associated.get_object()
                if not isinstance(associated, ArrayObject):
                    raise ValueError("PDF associated files are invalid")
                associated[:] = [
                    ref for ref in associated if id(ref.get_object()) not in specs
                ]
            for child in list(value.values()):
                remove_associations(child)
        else:
            for child in value:
                remove_associations(child)

    remove_associations(reader.root_object)
    if "/Info" in reader.trailer:
        remove_associations(reader.trailer.raw_get("/Info"))
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    output = BytesIO()
    writer.write(output)
    return output.getvalue(), payloads, unreadable


def compile_render_job(
    job: RenderJob,
    typst_bin: str,
    *,
    timeout: float = CompilerTimeouts.compile,
    jobs: int | None = None,
) -> tuple[list[CheckResult], dict[str, Any] | None, Exception | None]:
    """Compile once, publish only sanitized PDF bytes, and validate placed evidence."""
    job.pdf.parent.mkdir(parents=True, exist_ok=True)
    job.pdf.unlink(missing_ok=True)
    work = job.workspace / "work"
    work.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="render-", dir=work) as temporary:
        directory = Path(temporary)
        wrapper = directory / "entry.typ"
        wrapper.write_text(
            '#include sys.inputs.at("immuknow-template-path")\n'
            "#context {\n"
            "  let reports = query(<immuknow-report>).map(it => it.value)\n"
            f'  pdf.attach("/{EVIDENCE_ATTACHMENT}", bytes(json.encode(reports)), mime-type: "application/json")\n'
            "}\n",
            encoding="utf-8",
        )
        raw_pdf = directory / "compiled.pdf"
        command = [
            typst_bin,
            "compile",
            *compiler_options(job),
            "--input",
            "immuknow-template-path=/"
            + job.template.relative_to(job.workspace).as_posix(),
            *(["--jobs", str(jobs)] if jobs is not None else []),
            str(wrapper),
            str(raw_pdf),
        ]
        result = run_typst(command, timeout=timeout, operation="notice compilation")
        sanitized, payloads, unreadable = _strip_evidence(raw_pdf.read_bytes())
        partial = directory / "sanitized.pdf"
        partial.write_bytes(sanitized)
        partial.replace(job.pdf)
    diagnostics = compiler_warnings(result.stderr)
    try:
        if unreadable or len(payloads) != 1:
            raise ValueError("Expected exactly one readable render evidence attachment")
        summaries = parse_json(payloads[0], label="Render evidence")
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
        return diagnostics, summary, None
    except Exception as exc:
        # The sanitized original is already published; preserve that outcome even
        # if evidence validation raises an unexpected error.
        return diagnostics, None, exc


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
