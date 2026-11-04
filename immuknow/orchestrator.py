"""Run the complete notice workflow; expose the same callable through the CLI."""

from __future__ import annotations
import argparse
import json
import logging
import sys
import os
import shutil
import subprocess
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from copy import deepcopy
from hashlib import sha256
from importlib.metadata import version
from typing import Any, TextIO

import yaml
import pandas as pd
from pypdf.errors import PdfReadError
from dataclasses import asdict, dataclass, fields
from contextlib import contextmanager
from collections.abc import Generator
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
from .assignment_manifest import (
    ReconciliationResult,
    load_manifest,
    print_preflight_summary,
)
from .data_models import CheckResult, ClientRecord, RenderJob
from .load_config import parse_config
from .component_resources import verify_components
from .run_lock import run_lock
from .progress import StageProgress
from .build_info import current_build_info
from . import run_report, validation_policy
from .version_notices import load_catalog, template_identity

# Pipeline stages follow the main workflow below; imports do not run the stages.
# isort: off
from . import (
    output_directory,
    preprocess,
    generate_notices,
    compile_notices,
    validate_pdfs,
    encrypt_notices,
    bundle_pdfs,
)
# isort: on

DEFAULT_OUTPUT_DIR = Path.cwd() / "runs"
DEFAULT_CONFIG_DIR = Path(str(files("immuknow").joinpath("config")))


_CLIENT_FACT_FIELDS = tuple(field.name for field in fields(ClientRecord))


def _prepared_facts(client: ClientRecord) -> dict[str, Any]:
    """Expose prepared fields without copying their read-only nested values.

    Rendering, encryption, and reporting treat these shared values as immutable;
    independently produced render evidence remains owned by its own record fields.
    """
    return {name: getattr(client, name) for name in _CLIENT_FACT_FIELDS}


def _positive_workers(value: str) -> int:
    try:
        number = int(value)
        if number > 0:
            return number
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("workers must be a positive integer")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run the ImmuKnow immunization notice generation pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
        epilog="""
Examples:
  %(prog)s clients.csv --template ./templates/overdue_diseases_v1.en.typ --output ./runs
  %(prog)s clients.csv --notice-assignments ./assignments.json --templates ./templates --output ./runs

assignments.json is a UTF-8 JSON array:
[
  {"client_id": "1234567890", "template": "overdue_diseases_v1.en.typ"},
  {"client_id": "1234567891", "template": "overdue_agents_v1.fr.typ",
   "experiment_id": "wording-comparison", "experiment_arm": "B"}
]

Use nonempty string client_id and template values, one unambiguous assignment
per input client. Optional experiment_id and experiment_arm are string labels.
Template names are filenames inside --templates, not paths. Each filename
must be <version_id>.<language>.typ; supported languages are en and fr.
--template selects that file for every client; it never switches automatically.
Extra assignments are reported and do not create clients. Warnings remain in
the report; any input failure rejects the complete file before rendering.
This includes invalid history, identifier collisions and missing or ambiguous assignments.
Known applicability conflicts warn and retain the selected notice. Malformed
shared JSON/configuration stops setup. After input is accepted, a failed notice does not stop the others.
Each run keeps its own originals, run.json and report.html under --output.
        """,
    )

    parser.add_argument(
        "input_file",
        type=Path,
        help="CSV cohort path, absolute or relative to the working directory",
    )
    parser.add_argument(
        "--input-encoding",
        choices=preprocess.CSV_ENCODINGS,
        help="CSV encoding; default tries UTF-8 (with or without BOM), Windows-1252, then Latin-1",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        dest="output_dir",
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_DIR,
        dest="config_dir",
        help=f"Config directory (default: {DEFAULT_CONFIG_DIR})",
    )
    parser.add_argument(
        "--templates",
        type=Path,
        default=None,
        dest="template_dir",
        help="Required template project directory for --notice-assignments.",
    )
    parser.add_argument(
        "--workers",
        type=_positive_workers,
        default=1,
        help="Concurrent notice renders (default: 1).",
    )
    parser.add_argument(
        "--no-progress", action="store_true", help="Suppress terminal progress output."
    )
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--notice-assignments",
        type=Path,
        help="JSON assignments with client_id and a template filename for each client.",
    )
    selection.add_argument(
        "--template",
        type=Path,
        dest="notice_template",
        help="One <version_id>.<language>.typ template file for every client.",
    )

    args = parser.parse_args()
    if args.notice_assignments is not None and args.template_dir is None:
        parser.error(
            "--notice-assignments requires --templates DIRECTORY; Core supplies no starter templates"
        )
    if args.notice_template is not None and args.template_dir is not None:
        parser.error("--template supplies its own directory; omit --templates")
    return args


@contextmanager
def run_logging(log_path: Path) -> Generator[None]:
    """Write this run's application messages without replacing caller logging."""
    logger = logging.getLogger("immuknow")
    previous_level = logger.level
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.info("Run started")
        yield
        logger.info("Run completed")
    except BaseException:
        logger.exception("Run failed")
        raise
    finally:
        logger.removeHandler(handler)
        handler.close()
        logger.setLevel(previous_level)


def run_pipeline(
    input_path: Path,
    output_dir: Path,
    *,
    notice_assignments: Path | None = None,
    notice_template: Path | None = None,
    config_dir: Path = DEFAULT_CONFIG_DIR,
    template_dir: Path | None = None,
    input_encoding: str | None = None,
    workers: int = 1,
    progress_stream: TextIO | None = None,
) -> Path:
    """Run a cohort, retain independent results, and return its authoritative record.

    Shared setup failures save ``failed_setup`` before propagating. Input failures
    return a ``rejected_input`` report without rendering. After acceptance,
    per-notice errors are recorded and the remaining notices continue. The CLI
    returns nonzero for a record containing failed entries or delivery steps.
    """
    if type(workers) is not int or workers < 1:
        raise ValueError("workers must be a positive integer")
    if (notice_assignments is None) == (notice_template is None):
        raise ValueError("Choose exactly one of notice_assignments or notice_template")
    if notice_template is not None and template_dir is not None:
        raise ValueError(
            "notice_template supplies its own directory; omit template_dir"
        )
    input_path, output_dir = input_path.resolve(), output_dir.resolve()
    config_dir = config_dir.resolve()
    if notice_template is not None:
        notice_template = notice_template.parent.resolve() / notice_template.name
        template_dir = notice_template.parent
    if template_dir is None:
        raise ValueError(
            "notice_assignments requires template_dir; supply a template project"
        )
    template_dir = template_dir.resolve()
    notice_assignments = notice_assignments.resolve() if notice_assignments else None
    for source in (input_path, config_dir, template_dir, notice_assignments):
        if source is not None:
            generate_notices.reject_overlap(source, output_dir)

    # Start the record before loading shared inputs so setup errors have evidence.
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    run_dir = output_directory.prepare_run_directory(output_dir, run_id)
    with run_lock(run_dir):
        build = current_build_info()
        record: dict[str, Any] = {
            "format_version": run_report.RUN_FORMAT_VERSION,
            "run_id": run_id,
            "version": {
                "application": version("ImmuKnow"),
                "compiler": None,
                "build": build,
            },
            "started_at": run_report.timestamp(),
            "finished_at": None,
            "status": "running",
            "input": {
                "source": str(input_path),
                "requested_encoding": input_encoding or "auto",
            },
            "configuration": {},
            "resources": {},
            "entries": [],
            "checks": [],
            "delivery_attempts": [],
            "warning_acceptances": [],
            "withheld_rows": [],
        }
        run_report.write_report(run_dir, record)
        setup_complete = False
        config: dict[str, Any] = {}
        with run_logging(run_dir / "logs" / "run.log"):
            try:
                # Freeze source and selected resources. All later reads use these bytes.
                preprocess.validate_csv_path(input_path)
                source_snapshot = run_dir / "resources" / "input.csv"
                shutil.copyfile(input_path, source_snapshot)
                record["input"] = {
                    **record["input"],
                    **run_report.artifact_record(source_snapshot, run_dir),
                }
                source_frame = preprocess.read_input(
                    source_snapshot, encoding=input_encoding
                )
                record["input"].update(
                    encoding=source_frame.attrs["encoding"],
                    delimiter=source_frame.attrs["delimiter"],
                )
                _record_source_rows(source_frame, record)
                run_report.write_report(run_dir, record)
                selected_notice = (
                    template_identity(notice_template) if notice_template else None
                )
                staged_config = run_dir / "resources" / "config"
                staged_templates = run_dir / "resources" / "templates"
                parameters = (config_dir / "parameters.yaml").read_bytes()
                config = parse_config(parameters)
                validation_policy.resolve_policy(config.get("validation", {}), record)
                timeouts = compile_notices.CompilerTimeouts.from_config(
                    config.get("typst", {}).get("timeouts_seconds", {})
                )
                config.setdefault("typst", {})["timeouts_seconds"] = asdict(timeouts)
                config["creation_timestamp"] = int(
                    datetime.fromisoformat(record["started_at"]).timestamp()
                )
                saved_config = deepcopy(config)
                saved_config.get("encryption", {}).pop("password", None)
                record["configuration"] = {
                    "source": str(config_dir),
                    "templates": str(template_dir),
                    "source_parameters_sha256": sha256(parameters).hexdigest(),
                    "redacted_fields": ["encryption.password"],
                    "effective": saved_config,
                }
                shutil.copytree(
                    config_dir,
                    staged_config,
                    ignore=shutil.ignore_patterns("parameters.yaml"),
                )
                school = config.get("school_validation", {})
                if school.get("enabled"):
                    reference = preprocess.school_reference_path(school, config_dir)
                    record["configuration"]["school_reference_source"] = str(reference)
                    if reference.is_relative_to(config_dir):
                        saved_reference = reference.relative_to(config_dir).as_posix()
                    else:
                        shutil.copyfile(
                            reference, run_dir / "resources" / "school-reference.json"
                        )
                        saved_reference = "../school-reference.json"
                    school["reference_file"] = saved_reference
                    saved_config["school_validation"]["reference_file"] = (
                        saved_reference
                    )
                (staged_config / "parameters.yaml").write_text(
                    yaml.safe_dump(saved_config), encoding="utf-8"
                )
                verify_components(template_dir)
                shutil.copytree(template_dir, staged_templates)
                verify_components(staged_templates)
                catalog = load_catalog(staged_config)
                manifest = {}
                if notice_assignments:
                    assignment_snapshot = run_dir / "resources" / "assignments.json"
                    shutil.copyfile(notice_assignments, assignment_snapshot)
                    record["input"] = {
                        **record["input"],
                        "assignments": run_report.artifact_record(
                            assignment_snapshot, run_dir
                        ),
                    }
                    manifest = load_manifest(assignment_snapshot, staged_templates)
                for entry in record["entries"]:
                    requested = config.get("encryption", {}).get("enabled", False)
                    entry["encryption"] = {
                        "requested": requested,
                        "status": "not_run" if requested else "not_requested",
                    }
                    selection = manifest.get(entry["client_id"])
                    if selection:
                        selection_fields = asdict(selection)
                        selection_fields["source"] = selection_fields.pop(
                            "assignment_source"
                        )
                        selection_fields.pop("client_id")
                        entry["assignment"].update(selection_fields)
                        entry["assignment"]["template"] = selection.template
                    elif notice_template and selected_notice is not None:
                        entry["assignment"].update(
                            source="template",
                            template=notice_template.name,
                            version_id=selected_notice[0],
                            language=selected_notice[1],
                            experiment_id=None,
                            experiment_arm=None,
                        )
                typst_settings = config.get("typst", {})
                typst_bin = os.environ.get(
                    "TYPST_BIN", typst_settings.get("bin", "typst")
                )
                compile_notices.check_compiler(typst_bin, timeout=timeouts.version)
                record["version"]["compiler"] = compile_notices.TYPST_VERSION
                record["resources"] = run_report.resource_manifest(
                    run_dir / "resources", run_dir
                )
                run_report.write_report(run_dir, record)

                # Preserve every row and its explicit assignment before rendering.
                prepared_result, reconciliation = preprocess.prepare_clients(
                    source_frame,
                    run_dir / "work",
                    config,
                    staged_config,
                    catalog,
                    manifest,
                    selected_notice,
                )
                del source_frame, manifest
                print_preflight_summary(reconciliation)
                _record_assignment_findings(record, reconciliation)
                del reconciliation
                for warning in prepared_result.warnings:
                    run_report.add_check(
                        record,
                        "data.preparation_warning",
                        "preparation",
                        "warn",
                        warning,
                    )
                by_row = {entry["row_key"]: entry for entry in record["entries"]}
                clients = prepared_result.clients
                if len(clients) != len(by_row) or {
                    client.sequence for client in clients
                } != set(by_row):
                    raise ValueError(
                        "Preparation must account for every source row exactly once"
                    )
                for client in clients:
                    entry = by_row[client.sequence]
                    entry["facts"] = {"prepared": _prepared_facts(client)}
                    entry["checks"].extend(
                        check.to_dict()
                        for check in prepared_result.row_checks[client.sequence]
                    )
                    if client.version_id and client.language:
                        entry["assignment"].update(
                            version_id=client.version_id,
                            language=client.language,
                            template=f"{client.version_id}.{client.language}.typ",
                        )
                del prepared_result
                failed_rows = [
                    entry["row_key"]
                    for entry in record["entries"]
                    if any(check["status"] == "fail" for check in entry["checks"])
                ]
                record["input"]["accepted"] = not (
                    failed_rows
                    or any(check["status"] == "fail" for check in record["checks"])
                )
                if not record["input"]["accepted"]:
                    run_report.add_check(
                        record,
                        "input.rejected",
                        "preparation",
                        "fail",
                        f"Input file rejected: {len(failed_rows)} source rows failed checks. Correct the reported problems and run again. No notices were generated.",
                        measurements={"failed_rows": failed_rows},
                    )
                    run_report.finish_run(record)
                    result = run_report.write_report(run_dir, record)
                    print(f"Input file rejected. Report: {run_dir / 'report.html'}")
                    return result
                setup_complete = True
                run_report.write_report(run_dir, record)

                # Write factual inputs once. Invalid internal structures are programming
                # failures, not source warnings to turn into plausible-looking notices.
                jobs = generate_notices.prepare_render_jobs(clients, run_dir, config)
                compile_notices.check_expected_notices(clients, jobs)
                successful: dict[str, tuple[ClientRecord, RenderJob]] = {}
                for client, job in zip(clients, jobs):
                    entry = by_row[client.sequence]
                    entry["facts"].update(run_report.artifact_record(job.data, run_dir))
                    entry["assignment"]["sha256"] = sha256(
                        job.template.read_bytes()
                    ).hexdigest()
                run_report.write_report(run_dir, record)
                checkpoint = run_report._OutcomeCheckpoint(run_dir, record)

                def incorporate(
                    client: ClientRecord,
                    job: RenderJob,
                    outcome: _RenderOutcome,
                    stage: StageProgress,
                ) -> None:
                    entry = by_row[client.sequence]
                    failed = False
                    try:
                        if outcome.compiled:
                            entry["checks"].extend(
                                check.to_dict() for check in outcome.diagnostics
                            )
                            run_report.add_check(
                                entry,
                                "rendering.completed",
                                "render",
                                "pass",
                                "Original PDF produced",
                            )
                            if outcome.summary is not None:
                                entry["render_summary"] = outcome.summary
                                for check in outcome.summary["checks"]:
                                    if check not in entry["checks"]:
                                        entry["checks"].append(check)
                            if outcome.error is not None or outcome.summary is None:
                                detail = (
                                    outcome.error.stderr
                                    if isinstance(
                                        outcome.error, subprocess.CalledProcessError
                                    )
                                    else str(
                                        outcome.error
                                        or "Required render evidence is missing"
                                    )
                                )
                                run_report.add_check(
                                    entry,
                                    "render.evidence_failed",
                                    "render",
                                    "fail",
                                    str(detail),
                                )
                                failed = True
                            entry["original"], pdf_checks = (
                                validate_pdfs.inspect_notice(job, run_dir)
                            )
                            entry["checks"].extend(
                                check.to_dict() for check in pdf_checks
                            )
                            if (
                                outcome.summary is not None
                                and outcome.summary["page_count"]
                                != entry["original"]["pages"]
                            ):
                                run_report.add_check(
                                    entry,
                                    "render.evidence_failed",
                                    "render",
                                    "fail",
                                    "Render evidence page count differs from the original PDF.",
                                )
                            failed = failed or any(
                                check["status"] == "fail" for check in entry["checks"]
                            )
                            successful[client.sequence] = (client, job)
                        elif outcome.error is not None:
                            raise outcome.error
                    except (
                        OSError,
                        subprocess.CalledProcessError,
                        PdfReadError,
                    ) as exc:
                        detail = str(exc)
                        if (
                            isinstance(exc, subprocess.CalledProcessError)
                            and exc.stderr
                        ):
                            detail += "\n" + exc.stderr
                        entry["original"]["status"] = "failed"
                        run_report.add_check(
                            entry, "rendering.failed", "render", "fail", detail
                        )
                        logging.getLogger("immuknow").error(
                            "Notice %s failed: %s", entry["row_key"], detail
                        )
                        failed = True
                    finally:
                        checkpoint.advance()
                        stage.advance(failed=failed or sys.exc_info()[0] is not None)
                    if outcome.error is not None and not outcome.expected:
                        raise outcome.error

                with StageProgress(
                    "Rendering", len(jobs), stream=progress_stream
                ) as stage:
                    executor = ThreadPoolExecutor(max_workers=workers)
                    pending = {}
                    iterator = iter(zip(clients, jobs))
                    failure = None
                    try:

                        def submit_next() -> None:
                            item = next(iterator, None)
                            if item is not None:
                                client, job = item
                                future = executor.submit(
                                    _render_notice,
                                    job,
                                    typst_bin,
                                    timeouts,
                                    workers > 1,
                                )
                                pending[future] = (client, job)

                        for _ in range(min(workers, len(jobs))):
                            submit_next()
                        while pending:
                            done, _ = wait(
                                pending, timeout=0.25, return_when=FIRST_COMPLETED
                            )
                            if not done:
                                stage.refresh()
                                continue
                            for future in done:
                                client, job = pending.pop(future)
                                incorporate(client, job, future.result(), stage)
                            for _ in done:
                                submit_next()
                    except BaseException as exc:
                        failure = exc
                        for future in pending:
                            future.cancel()
                    finally:
                        # Keep the lock and account for every active compiler before leaving.
                        executor.shutdown(wait=True, cancel_futures=True)
                        for future, (client, job) in pending.items():
                            if future.cancelled():
                                continue
                            try:
                                incorporate(client, job, future.result(), stage)
                            except BaseException as exc:
                                if failure is None:
                                    failure = exc
                    if failure is not None:
                        raise failure
                run_report.write_report(run_dir, record)

                # Preserve input order for encryption and delivery, regardless of completion order.
                successful_pairs = [
                    successful[client.sequence]
                    for client in clients
                    if client.sequence in successful
                ]
                requested_pairs = [
                    (client, job)
                    for client, job in successful_pairs
                    if by_row[client.sequence]["encryption"]["requested"]
                ]
                if requested_pairs:
                    checkpoint = run_report._OutcomeCheckpoint(run_dir, record)
                    with StageProgress(
                        "Encryption", len(requested_pairs), stream=progress_stream
                    ) as stage:
                        for client, job in requested_pairs:
                            entry = by_row[client.sequence]
                            failed = False
                            try:
                                destination = (
                                    run_dir / "encrypted" / f"{entry['row_key']}.pdf"
                                )
                                encryption_details = encrypt_notices.encrypt_notice(
                                    client, job.pdf, destination, config["encryption"]
                                )
                                entry["encryption"].update(
                                    status="completed",
                                    method=encryption_details,
                                    **run_report.artifact_record(destination, run_dir),
                                )
                            except (OSError, ValueError, PdfReadError) as exc:
                                failed = True
                                entry["encryption"]["status"] = "failed"
                                run_report.add_check(
                                    entry,
                                    "encryption.failed",
                                    "delivery",
                                    "fail",
                                    str(exc),
                                )
                            finally:
                                checkpoint.advance()
                                stage.advance(failed=failed)
                    run_report.write_report(run_dir, record)
                with StageProgress("Delivery", stream=progress_stream):
                    bundle_pdfs._bundle_run(run_dir, record)
                output_directory.cleanup_output(run_dir, config)
                run_report.finish_run(record)
                result = run_report.write_report(run_dir, record)
                produced = sum(
                    entry["original"]["status"] == "completed"
                    for entry in record["entries"]
                )
                print(
                    f"Run {record['status']}: {produced}/{len(record['entries'])} original PDFs. {run_dir / 'report.html'}"
                )
                return result
            except BaseException as exc:
                record["resources"] = {
                    **record["resources"],
                    **run_report.resource_manifest(run_dir / "resources", run_dir),
                }
                run_report.add_check(
                    record,
                    "run.failed",
                    "execution" if setup_complete else "setup",
                    "fail",
                    "Run interrupted"
                    if isinstance(exc, KeyboardInterrupt)
                    else str(exc),
                )
                for entry in record["entries"]:
                    if entry["original"]["status"] == "not_run":
                        entry["original"]["status"] = (
                            "failed" if setup_complete else "not_run"
                        )
                run_report.finish_run(record, failed_setup=not setup_complete)
                run_report.write_report(run_dir, record)
                print(
                    f"Run {record['status']}. Report: {run_dir / 'report.html'}",
                    file=sys.stderr,
                )
                raise


@dataclass(frozen=True)
class _RenderOutcome:
    compiled: bool
    diagnostics: tuple[CheckResult, ...]
    summary: dict[str, Any] | None
    error: BaseException | None
    expected: bool


def _render_notice(
    job: RenderJob,
    typst_bin: str,
    timeouts: compile_notices.CompilerTimeouts,
    concurrent: bool,
) -> _RenderOutcome:
    """Compile and evaluate one independent notice without touching the report."""
    options = {"jobs": 1} if concurrent else {}
    try:
        diagnostics = compile_notices.compile_render_job(
            job, typst_bin, timeout=timeouts.compile, **options
        )
    except BaseException as exc:
        return _RenderOutcome(
            False,
            (),
            None,
            exc,
            isinstance(exc, (OSError, subprocess.CalledProcessError)),
        )
    try:
        summary = compile_notices.evaluate_render_job(
            job, typst_bin, timeout=timeouts.evidence, **options
        )
        return _RenderOutcome(True, tuple(diagnostics), summary, None, True)
    except BaseException as exc:
        return _RenderOutcome(
            True,
            tuple(diagnostics),
            None,
            exc,
            isinstance(
                exc,
                (
                    OSError,
                    ValueError,
                    subprocess.CalledProcessError,
                ),
            ),
        )


def _record_source_rows(frame: pd.DataFrame, record: dict[str, Any]) -> None:
    """Capture unvalidated values and row keys before preparation can sort them."""
    for number, values in enumerate(frame.to_dict(orient="records"), start=1):
        record["entries"].append(
            {
                "row_key": f"row-{number:06d}",
                "source": {"row_number": number, "values": values},
                "client_id": str(values.get("client_id", "")).strip(),
                "assignment": {},
                "facts": None,
                "checks": [],
                "original": {"status": "not_run"},
                "encryption": {"requested": False, "status": "not_requested"},
                "routing": {"destination": None, "reason": "not_run"},
                "bundle": None,
            }
        )


def _record_assignment_findings(
    record: dict[str, Any], reconciliation: ReconciliationResult
) -> None:
    by_row: dict[str, list[dict[str, Any]]] = {}
    by_client: dict[str, list[dict[str, Any]]] = {}
    for entry in record["entries"]:
        by_row.setdefault(entry["row_key"], []).append(entry)
        by_client.setdefault(entry["client_id"], []).append(entry)
    for finding in reconciliation.findings:
        targets = (
            by_row.get(finding.row_key, [])
            if finding.row_key
            else by_client.get(finding.client_id, [])
        )
        for target in targets or [record]:
            run_report.add_check(
                target,
                f"assignment.{finding.kind}",
                "assignment",
                finding.status,
                finding.reason,
            )


def main() -> int:
    """Translate CLI options into one complete pipeline call."""
    args = parse_args()
    try:
        completed = run_pipeline(
            args.input_file,
            args.output_dir,
            config_dir=args.config_dir,
            template_dir=args.template_dir,
            notice_assignments=args.notice_assignments,
            notice_template=args.notice_template,
            input_encoding=args.input_encoding,
            workers=args.workers,
            progress_stream=None if args.no_progress else sys.stderr,
        )
        record = json.loads(completed.read_text(encoding="utf-8"))
        return (
            1
            if record["status"]
            in {"failed_setup", "rejected_input", "completed_with_failures"}
            else 0
        )
    except KeyboardInterrupt:
        print("Run interrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
