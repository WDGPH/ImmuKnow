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
    ManifestRow,
    ReconciliationError,
    ReconciliationResult,
    load_manifest,
    print_preflight_summary,
)
from .config_loader import load_config
from .data_models import PreprocessResult
from .notice_versioning import NoticeVersionCatalog, load_catalog, template_identity

DEFAULT_INPUT_DIR = Path.cwd() / "input"
DEFAULT_OUTPUT_DIR = Path.cwd() / "output"
DEFAULT_TEMPLATES_DIR = Path(str(files("immuknow").joinpath("templates")))
DEFAULT_PHU_TEMPLATES_DIR = Path.cwd() / "phu_templates"
DEFAULT_CONFIG_DIR = Path(str(files("immuknow").joinpath("config")))


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run the ImmuKnow immunization notice generation pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s students.csv --notice-assignments assignments.json
  %(prog)s students.csv --notice-template ./my-phu/overdue_standard_v1.fr.typ
        """,
    )

    parser.add_argument(
        "input_file",
        type=str,
        help="CSV cohort filename or path (e.g., students.csv)",
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_DIR,
        dest="input_dir",
        help=f"Input directory (default: {DEFAULT_INPUT_DIR})",
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
        "--template",
        type=str,
        default=None,
        dest="template_dir",
        help="PHU template name within phu_templates/ (e.g., 'wdgph'). "
        "Use with --notice-assignments; defaults to packaged templates.",
    )
    parser.add_argument(
        "--templates",
        type=Path,
        default=None,
        dest="custom_templates",
        help="Path to an external directory of native Typst templates and assets.",
    )
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument(
        "--notice-assignments",
        type=Path,
        help="JSON assignments with client_id and a template filename for each client.",
    )
    selection.add_argument(
        "--notice-template",
        type=Path,
        help="One <version_id>.<language>.typ entry point for every client.",
    )

    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    """Validate command-line arguments and raise errors if invalid."""
    if args.notice_template is not None:
        if args.template_dir is not None or args.custom_templates is not None:
            raise ValueError(
                "--notice-template supplies its own directory; do not combine it "
                "with --template or --templates"
            )
        return
    # --- Resolve template directory ---
    custom_templates = getattr(args, "custom_templates", None)
    if custom_templates is not None:
        if args.template_dir is not None:
            raise ValueError("Choose either --template NAME or --templates PATH")
        args.template_dir = custom_templates.resolve()
    elif args.template_dir is None:
        args.template_dir = DEFAULT_TEMPLATES_DIR
    else:
        if (
            args.template_dir in (".", "..")
            or "/" in args.template_dir
            or "\\" in args.template_dir
        ):
            raise ValueError(
                f"Template name cannot contain path separators: {args.template_dir}\n"
                f"Expected a simple name like 'wdgph' or 'my_phu', not a path."
            )

        phu_template_path = DEFAULT_PHU_TEMPLATES_DIR / args.template_dir
        if not phu_template_path.exists():
            raise FileNotFoundError(
                f"PHU template directory not found: {phu_template_path}\n"
                f"Expected location: phu_templates/{args.template_dir}\n"
                f"Ensure the directory exists and contains required template files."
            )
        if not phu_template_path.is_dir():
            raise NotADirectoryError(
                f"PHU template path is not a directory: {phu_template_path}"
            )
        args.template_dir = phu_template_path

    if not args.template_dir.is_dir():
        raise NotADirectoryError(
            f"Template path is not a directory: {args.template_dir}"
        )


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


def prepare_clients(
    input_path: Path,
    output_dir: Path,
    run_id: str,
    config: dict,
    config_dir: Path,
    catalog: NoticeVersionCatalog,
    manifest: dict[str, ManifestRow],
    selected_notice: tuple[str, str] | None,
) -> PreprocessResult:
    """Validate source records and resolve the canonical notice cohort."""
    preprocess.configure_logging(output_dir, run_id)
    schema = config_dir / "input_schema.json"
    preprocess.validate_input(input_path, schema if schema.exists() else None)
    frame = preprocess.normalize_dataframe(preprocess.read_input(input_path))
    frame = preprocess.check_addresses_complete(
        frame, drop_incomplete=True, output_dir=output_dir
    )
    frame = preprocess.check_client_info_complete(
        frame,
        drop_incomplete=True,
        output_dir=output_dir,
    )
    frame, warnings = preprocess.run_phix_validation(
        frame, output_dir, config=config, config_dir=config_dir
    )
    if selected_notice is not None:
        version_id, language = selected_notice
        manifest = {
            client_id: ManifestRow(
                client_id,
                version_id,
                language,
                None,
                None,
                assignment_source="template",
            )
            for client_id in frame["client_id"]
        }
    reference = config_dir / "vaccine_reference.json"
    if not reference.exists():
        reference = DEFAULT_CONFIG_DIR / "vaccine_reference.json"
    result, reconciliation = preprocess.build_preprocess_result(
        frame,
        json.loads(reference.read_text(encoding="utf-8")),
        preprocess.REPLACE_UNSPECIFIED,
        config=config,
        config_dir=config_dir,
        catalog=catalog,
        manifest=manifest,
    )
    report_assignments(reconciliation, output_dir, run_id)
    return PreprocessResult(result.clients, warnings + result.warnings)


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
        result = prepare_clients(
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
        validate_args(args)
        completed = run_pipeline(
            args.input_dir / args.input_file,
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
