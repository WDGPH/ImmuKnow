"""Run the complete notice workflow; expose the same callable through the CLI."""

from __future__ import annotations
import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
from . import (
    bundle_pdfs,
    cleanup,
    compile_notices,
    encrypt_notice,
    generate_notices,
    generate_qr_codes,
    prepare_output,
    preprocess,
    validate_pdfs,
)
from .assignment_manifest import (
    ReconciliationError,
    ReconciliationResult,
    load_manifest,
    print_preflight_summary,
)
from .config_loader import load_config
from .data_models import PreprocessResult
from .notice_versioning import load_catalog, template_identity

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
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
    before_run = config.get("pipeline", {}).get("before_run", {})
    if not prepare_output.prepare_output_directory(
        output_dir,
        output_dir / "logs",
        auto_remove=before_run.get("clear_output_directory", False),
    ):
        return None
    metadata_dir = output_dir / "metadata"
    metadata_dir.mkdir(exist_ok=True)
    artifact_dir = output_dir / "artifacts"
    try:
        result, reconciliation = preprocess.prepare_clients(
            input_path,
            output_dir,
            run_id,
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
    clients, _ = generate_qr_codes.generate_qr_codes(
        result.clients, artifact_dir, config
    )
    result = PreprocessResult(clients, result.warnings)
    artifact_path = preprocess.write_artifact(
        artifact_dir,
        run_id,
        result,
    )
    for warning in result.warnings:
        print(f"Warning: {warning}")
    jobs = generate_notices.prepare_render_jobs(
        clients,
        artifact_dir,
        template_dir,
        config,
        config_dir,
        run_id,
    )
    compile_notices.check_expected_notices(clients, jobs)
    compile_notices.compile_notices(jobs, artifact_dir, config)
    compile_notices.check_expected_notices(clients, jobs, require_files=True)
    validate_pdfs.validate_notices(
        [job.pdf for job in jobs],
        enabled_rules=config.get("pdf_validation", {}).get("rules", {}),
        json_output=metadata_dir / f"validation_{run_id}.json",
        client_id_map={job.pdf.name: job.client_id for job in jobs},
    )
    encrypted = (
        encrypt_notice.encrypt_expected_notices(clients, jobs, config)
        if config.get("encryption", {}).get("enabled", False)
        else []
    )
    bundles = bundle_pdfs.bundle_notices(clients, jobs, output_dir, run_id, config)
    completion = {
        "run_id": run_id,
        "input": str(input_path),
        "config": str(config_dir),
        "templates": str(template_dir),
        "notice_assignments": str(notice_assignments) if notice_assignments else None,
        "notice_template": str(notice_template) if notice_template else None,
        "cohort": str(artifact_path),
        "notices": [
            {
                "client_id": job.client_id,
                "sequence": job.sequence,
                "language": job.language,
                "version_id": job.version_id,
                "pdf": str(job.pdf),
            }
            for job in jobs
        ],
        "encrypted": [str(path) for path in encrypted],
        "bundles": [str(bundle.pdf_path) for bundle in bundles],
    }
    cleanup.cleanup_output(output_dir, config)
    completion_path = metadata_dir / f"completion_{run_id}.json"
    completion_path.write_text(json.dumps(completion, indent=2), encoding="utf-8")
    print(f"Pipeline completed successfully: {len(clients)} notices. {completion_path}")
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
