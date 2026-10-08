"""Run the complete notice workflow; expose the same callable through the CLI."""

from __future__ import annotations
import argparse
import json
import logging
import sys
from dataclasses import asdict
from contextlib import contextmanager
from collections.abc import Iterator
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
from .assignment_manifest import (
    ReconciliationError,
    ReconciliationResult,
    load_manifest,
    print_preflight_summary,
)
from .config_loader import load_config
from .data_models import PreprocessResult
from .notice_versioning import load_catalog, template_identity

# Pipeline stages follow the main workflow below; imports do not run the stages.
# isort: off
from . import (
    output_directory,
    preprocess,
    generate_qr_codes,
    generate_notices,
    compile_notices,
    validate_pdfs,
    encrypt_notice,
    bundle_pdfs,
)
# isort: on

DEFAULT_OUTPUT_DIR = Path.cwd() / "output"
DEFAULT_TEMPLATES_DIR = Path(str(files("immuknow").joinpath("templates")))
DEFAULT_CONFIG_DIR = Path(str(files("immuknow").joinpath("config")))


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run the ImmuKnow immunization notice generation pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
        epilog="""
Examples:
  %(prog)s students.csv --notice-assignments assignments.json
  %(prog)s students.csv --template ./my-phu/overdue_agents_v1.fr.typ
        """,
    )

    parser.add_argument(
        "input_file",
        type=Path,
        help="CSV cohort path, absolute or relative to the working directory",
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
        help="Template directory for --notice-assignments (default: packaged examples).",
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
        help="One <version_id>.<language>.typ entry point for every client.",
    )

    return parser.parse_args()


def report_assignments(
    result: ReconciliationResult, output_dir: Path, run_id: str
) -> Path | None:
    """Report policy findings and keep client-linked details in a private run file."""
    print_preflight_summary(result)
    if not result.findings:
        return None
    diagnostic = output_dir / "metadata" / f"assignment_findings_{run_id}.json"
    diagnostic.touch(mode=0o600, exist_ok=False)
    diagnostic.write_text(
        json.dumps([asdict(finding) for finding in result.findings], indent=2),
        encoding="utf-8",
    )
    return diagnostic


@contextmanager
def run_logging(log_path: Path) -> Iterator[None]:
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
    except Exception:
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
) -> Path | None:
    """Run one complete notice cohort and return its completion record.

    Select exactly one assignment manifest or notice template. Configuration
    and resources are selected once per call. A cancelled output
    cleanup returns None; any failed preparation, rendering, validation, or
    delivery operation raises and leaves no successful completion record.
    """
    # 1. Resolve inputs and check paths before clearing previous output.
    if (notice_assignments is None) == (notice_template is None):
        raise ValueError("Choose exactly one of notice_assignments or notice_template")
    selected_notice = None
    if notice_template is not None:
        if template_dir is not None:
            raise ValueError(
                "notice_template supplies its own directory; omit template_dir"
            )
        notice_template = notice_template.parent.resolve() / notice_template.name
        selected_notice = template_identity(notice_template)
        template_dir = notice_template.parent
    input_path, output_dir = input_path.resolve(), output_dir.resolve()
    config_dir = config_dir.resolve()
    template_dir = (template_dir or DEFAULT_TEMPLATES_DIR).resolve()
    # Check the source path before clearing output; read and validate its data later.
    preprocess.validate_csv_path(input_path)
    if not template_dir.is_dir():
        raise NotADirectoryError(f"Template path is not a directory: {template_dir}")
    for source in (input_path, config_dir, template_dir):
        generate_notices.reject_overlap(source, output_dir)
    if notice_assignments is not None:
        notice_assignments = notice_assignments.resolve()
        generate_notices.reject_overlap(notice_assignments, output_dir)
    config = load_config(config_dir / "parameters.yaml")
    catalog = load_catalog(config_dir)
    manifest = (
        load_manifest(notice_assignments, template_dir)
        if notice_assignments is not None
        else {}
    )
    if selected_notice is not None and selected_notice[0] not in catalog.versions:
        raise ValueError(
            f"Selected version {selected_notice[0]!r} is absent from notice_versions.yaml"
        )
    # 2. Prepare the output directory and start this run's log.
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    before_run = config.get("pipeline", {}).get("before_run", {})
    if not output_directory.prepare_output_directory(
        output_dir,
        output_dir / "logs",
        auto_remove=before_run.get("clear_output_directory", False),
    ):
        return None
    with run_logging(output_dir / "logs" / f"run_{run_id}.log"):
        metadata_dir = output_dir / "metadata"
        metadata_dir.mkdir(exist_ok=True)
        artifact_dir = output_dir / "artifacts"
        # 3. Prepare client records and confirm every notice assignment.
        try:
            prepared_result, reconciliation = preprocess.prepare_clients(
                input_path,
                output_dir,
                config,
                config_dir,
                catalog,
                manifest,
                selected_notice,
            )
        except ReconciliationError as exc:
            diagnostic = report_assignments(exc.result, output_dir, run_id)
            raise ValueError(
                f"Notice assignment preflight failed. Sensitive assignment diagnostics: {diagnostic}"
            ) from exc
        report_assignments(reconciliation, output_dir, run_id)
        # 4. Add optional QR links and save the prepared client records.
        clients, _ = generate_qr_codes.generate_qr_codes(
            prepared_result.clients, artifact_dir, config
        )
        prepared_result = PreprocessResult(clients, prepared_result.warnings)
        prepared_clients_path = preprocess.write_artifact(
            artifact_dir,
            run_id,
            prepared_result,
        )
        for warning in prepared_result.warnings:
            print(f"Warning: {warning}")
        # 5. Prepare one template and data file per notice, then compile PDFs.
        render_jobs = generate_notices.prepare_render_jobs(
            clients,
            artifact_dir,
            template_dir,
            config,
            config_dir,
            run_id,
        )
        compile_notices.check_expected_notices(clients, render_jobs)
        compile_notices.compile_notices(render_jobs, artifact_dir, config)
        compile_notices.check_expected_notices(clients, render_jobs, require_files=True)
        # 6. Check the completed PDFs before delivering any notices.
        validate_pdfs.validate_notices(
            [job.pdf for job in render_jobs],
            enabled_rules=config.get("pdf_validation", {}).get("rules", {}),
            json_output=metadata_dir / f"validation_{run_id}.json",
            client_id_map={job.pdf.name: job.client_id for job in render_jobs},
        )
        # 7. Make optional encrypted copies and grouped PDF bundles.
        encrypted_pdfs = (
            encrypt_notice.encrypt_expected_notices(clients, render_jobs, config)
            if config.get("encryption", {}).get("enabled", False)
            else []
        )
        bundle_results = bundle_pdfs.bundle_notices(
            clients, render_jobs, output_dir, run_id, config
        )
        # 8. Record the outputs; publish completion only after cleanup succeeds.
        completion = {
            "run_id": run_id,
            "input": str(input_path),
            "config": str(config_dir),
            "templates": str(template_dir),
            "notice_assignments": str(notice_assignments)
            if notice_assignments
            else None,
            "notice_template": str(notice_template) if notice_template else None,
            "cohort": str(prepared_clients_path),
            "notices": [
                {
                    "client_id": job.client_id,
                    "sequence": job.sequence,
                    "language": job.language,
                    "version_id": job.version_id,
                    "pdf": str(job.pdf),
                }
                for job in render_jobs
            ],
            "encrypted": [str(path) for path in encrypted_pdfs],
            "bundles": [str(bundle.pdf_path) for bundle in bundle_results],
        }
        output_directory.cleanup_output(output_dir, config)
        completion_path = metadata_dir / f"completion_{run_id}.json"
        completion_path.write_text(json.dumps(completion, indent=2), encoding="utf-8")
        print(
            f"Pipeline completed successfully: {len(clients)} notices. {completion_path}"
        )
        return completion_path


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
        )
        return 0 if completed is not None else 2
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
