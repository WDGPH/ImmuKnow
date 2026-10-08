"""VIPER Pipeline Orchestrator.

This script orchestrates the end-to-end immunization notice generation pipeline.
It executes each step in sequence, handles errors, and provides detailed timing and
progress information.

**Error Handling Philosophy:**

The pipeline distinguishes between critical and optional steps:

- **Critical Steps** (Notice generation, Compilation, PDF validation) implement fail-fast:
    - Any error halts the pipeline immediately
    - No partial output; users get deterministic results
    - Pipeline exits with code 1; user must investigate and retry

- **Optional Steps** (QR codes, Encryption, Bundling) implement per-item recovery:
    - Individual item failures (PDF, client, bundle) are logged and skipped
    - Remaining items continue processing
    - Pipeline completes successfully even if some items failed
    - Users are shown summary of successes, skipped, and failed items

- **Infrastructure Errors** (missing files, config errors) always fail-fast:
    - Caught and raised immediately; no recovery attempts
    - Prevents confusing partial output caused by misconfiguration
    - Pipeline exits with code 1

**Exit Codes:**

- 0: Pipeline completed successfully
- 1: Pipeline failed (critical step error or infrastructure error)
- 2: User cancelled (output preparation step)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from importlib.resources import files
from typing import Optional

# Import pipeline steps
from . import bundle_pdfs, cleanup, compile_notices, validate_pdfs
from . import (
    encrypt_notice,
    generate_notices,
    generate_qr_codes,
    prepare_output,
    preprocess,
)
from .assignment_manifest import (
    ReconciliationResult,
    has_errors,
    load_manifest,
    print_preflight_summary,
)
from .config_loader import load_config
from .enums import Language
from .notice_versioning import NoticeVersionCatalog, load_catalog

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent
DEFAULT_INPUT_DIR = Path.cwd() / "input"
DEFAULT_OUTPUT_DIR = Path.cwd() / "output"
DEFAULT_TEMPLATES_DIR = Path(str(files("templates")))
DEFAULT_PHU_TEMPLATES_DIR = Path.cwd() / "phu_templates"
DEFAULT_CONFIG_DIR = Path(str(files("config")))


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run the VIPER immunization notice generation pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s students.xlsx en
  %(prog)s students.xlsx fr
  %(prog)s students.xlsx --notice-assignments assignments.json
        """,
    )

    parser.add_argument(
        "input_file",
        type=str,
        help="Name of the input file (e.g., students.xlsx)",
    )
    parser.add_argument(
        "language",
        nargs="?",
        choices=sorted(Language.all_codes()),
        default=None,
        help=f"Language for output ({', '.join(sorted(Language.all_codes()))}). "
        "Required unless --notice-assignments is provided.",
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
        "If not specified, pipeline is run in testing mode, defaulting to the templates/ directory.",
    )
    parser.add_argument(
        "--templates",
        type=Path,
        default=None,
        dest="custom_templates",
        help="Path to an external directory of native Typst templates and assets.",
    )
    parser.add_argument(
        "--notice-assignments",
        type=Path,
        default=None,
        dest="notice_assignments",
        help="Path to JSON assignment manifest for notice versioning.",
    )

    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    """Validate command-line arguments and raise errors if invalid."""
    # --- Language / manifest mutual validation ---
    if args.notice_assignments is None and args.language is None:
        raise ValueError("language is required when not using --notice-assignments")

    if args.notice_assignments is not None and args.language is not None:
        print(
            f"Warning: CLI language argument '{args.language}' is ignored in manifest "
            "mode. Language is governed by the manifest and catalog default_language."
        )
        args.language = None

    if args.notice_assignments is not None:
        if not args.notice_assignments.exists():
            raise FileNotFoundError(
                f"Assignment manifest not found: {args.notice_assignments}"
            )
        catalog_path = args.config_dir / "notice_versions.yaml"
        if not catalog_path.exists():
            raise ValueError(
                "--notice-assignments requires notice_versions.yaml in the config "
                f"directory ({args.config_dir})"
            )

    # --- Input file ---
    if args.input_file and not (args.input_dir / args.input_file).exists():
        raise FileNotFoundError(
            f"Input file not found: {args.input_dir / args.input_file}"
        )

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


def print_header(input_file: str) -> None:
    """Print the pipeline header."""
    print()
    print("🚀 Starting VIPER Pipeline")
    print(f"🗂️  Input File: {input_file}")
    print()


def print_step(step_num: int, description: str) -> None:
    """Print a step header."""
    print()
    print(f"{'=' * 60}")
    print(f"Step {step_num}: {description}")
    print(f"{'=' * 60}")


def print_step_complete(step_num: int, description: str, duration: float) -> None:
    """Print step completion message."""
    print(f"✅ Step {step_num}: {description} complete in {duration:.1f} seconds.")


def run_step_1_prepare_output(
    output_dir: Path,
    log_dir: Path,
    config_dir: Path,
) -> bool:
    """Step 1: Prepare output directory."""
    print_step(1, "Preparing output directory")

    config = load_config(config_dir / "parameters.yaml")
    before_run_config = config.get("pipeline", {}).get("before_run", {})
    auto_remove = before_run_config.get("clear_output_directory", False)

    success = prepare_output.prepare_output_directory(
        output_dir=output_dir,
        log_dir=log_dir,
        auto_remove=auto_remove,
    )

    if not success:
        return False

    return True


def run_step_2_preprocess(
    input_dir: Path,
    input_file: str,
    output_dir: Path,
    language: Optional[str],
    run_id: str,
    config_dir: Path,
    catalog: Optional[NoticeVersionCatalog] = None,
    manifest: Optional[dict] = None,
) -> tuple[int, Optional[ReconciliationResult]]:
    """Step 2: Preprocessing.

    Returns:
        Tuple of (total_clients, reconciliation_result).
        reconciliation_result is None in fixed mode.
    """
    print_step(2, "Preprocessing")

    log_path = preprocess.configure_logging(output_dir, run_id)

    input_path = input_dir / input_file
    df_raw = preprocess.read_input(input_path)
    schema_path = config_dir / "input_schema.json"
    preprocess.validate_input(input_path, schema_path if schema_path.exists() else None)
    df = preprocess.normalize_dataframe(df_raw)

    assignment_mode = "manifest" if catalog is not None else "fixed"
    default_version = catalog.default_version if catalog is not None else None

    # Check that addresses are complete, return only complete rows
    df = preprocess.check_addresses_complete(
        df, drop_incomplete=True, output_dir=output_dir
    )
    df = preprocess.check_client_info_complete(
        df, assignment_mode, drop_incomplete=True, output_dir=output_dir
    )

    df, phix_warnings = preprocess.run_phix_validation(
        df, output_dir, config_dir / "parameters.yaml"
    )

    vaccine_reference_path = config_dir / "vaccine_reference.json"
    if not vaccine_reference_path.exists():
        vaccine_reference_path = preprocess.VACCINE_REFERENCE_PATH
    vaccine_reference = json.loads(vaccine_reference_path.read_text(encoding="utf-8"))

    preprocess_result, reconciliation_result = preprocess.build_preprocess_result(
        df,
        language,
        vaccine_reference,
        preprocess.REPLACE_UNSPECIFIED,
        config_path=config_dir / "parameters.yaml",
        catalog=catalog,
        manifest=manifest,
    )

    cohort_languages = {client.language for client in preprocess_result.clients}
    cohort_language = (
        next(iter(cohort_languages)) if len(cohort_languages) == 1 else None
    )

    artifact_path = preprocess.write_artifact(
        output_dir / "artifacts",
        cohort_language,
        run_id,
        preprocess_result,
        assignment_mode=assignment_mode,
        default_version=default_version,
    )

    # Write per-client assignment metadata file in manifest mode
    if catalog is not None and reconciliation_result is not None:
        preprocess.write_assignment_metadata(
            output_dir / "metadata",
            run_id,
            catalog,
            reconciliation_result,
            preprocess_result.clients,
        )

    print(f"📄 Preprocessed artifact: {artifact_path}")
    print(f"Preprocess log written to {log_path}")
    all_warnings = phix_warnings + preprocess_result.warnings
    if all_warnings:
        print("Warnings detected during preprocessing:")
        for warning in all_warnings:
            print(f" - {warning}")

    total_clients = len(preprocess_result.clients)
    print(f"👥 Clients normalized: {total_clients}")
    return total_clients, reconciliation_result


def run_step_3_generate_qr_codes(
    output_dir: Path,
    run_id: str,
    config_dir: Path,
) -> int:
    """Step 3: Generating QR code PNG files (optional).

    Returns:
        Number of QR codes generated (0 if disabled or no clients).
    """
    print_step(3, "Generating QR codes")

    config = load_config(config_dir / "parameters.yaml")

    qr_config = config.get("qr", {})
    qr_enabled = qr_config.get("enabled", True)

    if not qr_enabled:
        print("QR code generation disabled in configuration")
        return 0

    artifact_path = output_dir / "artifacts" / f"preprocessed_clients_{run_id}.json"
    artifacts_dir = output_dir / "artifacts"
    parameters_path = config_dir / "parameters.yaml"

    generated = generate_qr_codes.generate_qr_codes(
        artifact_path,
        artifacts_dir,
        parameters_path,
    )
    if generated:
        print(
            f"Generated {len(generated)} QR code PNG file(s) in {artifacts_dir}/qr_codes/"
        )
    return len(generated)


def run_step_4_generate_notices(
    output_dir: Path,
    run_id: str,
    template_dir: Path,
    config_dir: Path,
) -> None:
    """Step 4: Generating Typst templates.

    Parameters
    ----------
    output_dir : Path
        Output directory for artifacts
    run_id : str
        Unique run identifier
    template_dir : Path
        Directory containing language templates and optional assets
    config_dir : Path
        Configuration directory

    Notes
    -----
    Assets (logo.png, signature.png) are optional. They are only required if
    the template actually references them. If a template references an asset
    that doesn't exist, generation will fail with a clear error message.
    """
    print_step(4, "Preparing notice data")

    artifact_path = output_dir / "artifacts" / f"preprocessed_clients_{run_id}.json"
    artifacts_dir = output_dir / "artifacts"

    jobs = generate_notices.prepare_render_jobs(
        artifact_path,
        artifacts_dir,
        template_dir,
        config_path=config_dir / "parameters.yaml",
    )
    print(f"Prepared {len(jobs)} notice payloads and render jobs in {artifacts_dir}")


def run_step_5_compile_notices(
    output_dir: Path,
    config_dir: Path,
    template_dir: Path,
) -> None:
    """Step 5: Compiling Typst templates to PDFs.

    Parameters
    ----------
    output_dir : Path
        Output directory containing artifacts and PDFs
    config_dir : Path
        Configuration directory
    template_dir : Path
        Template directory (used as Typst --root for imports)
    """
    print_step(5, "Compiling Typst templates")

    load_config(config_dir / "parameters.yaml")

    artifacts_dir = output_dir / "artifacts"
    pdf_dir = output_dir / "pdf_individual"
    parameters_path = config_dir / "parameters.yaml"

    compiled = compile_notices.compile_with_config(
        artifacts_dir,
        pdf_dir,
        parameters_path,
        template_dir,
    )
    if compiled:
        print(f"Compiled {compiled} Typst file(s) to PDFs in {pdf_dir}.")


def run_step_6_validate_pdfs(
    output_dir: Path,
    run_id: str,
    config_dir: Path,
) -> None:
    """Step 6: Validating compiled PDFs."""
    print_step(6, "Validating compiled PDFs")

    pdf_dir = output_dir / "pdf_individual"
    metadata_dir = output_dir / "metadata"
    validation_json = metadata_dir / f"validation_{run_id}.json"
    artifacts_dir = output_dir / "artifacts"
    jobs = generate_notices.read_render_jobs(artifacts_dir, require_compiled=True)
    client_id_map = {job.pdf.name: job.client_id for job in jobs}

    validate_pdfs.main(
        pdf_dir,
        json_output=validation_json,
        client_id_map=client_id_map,
        config_dir=config_dir,
        expected_pdfs=[job.pdf for job in jobs],
    )


def run_step_7_encrypt_pdfs(
    output_dir: Path,
    run_id: str,
    config_dir: Path,
) -> None:
    """Step 7: Encrypting PDF notices (optional)."""
    print_step(7, "Encrypting PDF notices")

    artifacts_dir = output_dir / "artifacts"
    json_file = artifacts_dir / f"preprocessed_clients_{run_id}.json"

    encrypt_notice.encrypt_expected_notices(
        json_file,
        artifacts_dir,
        config_dir / "parameters.yaml",
    )


def run_step_8_bundle_pdfs(
    output_dir: Path,
    run_id: str,
    config_dir: Path,
) -> list:
    """Step 8: Bundling PDFs (optional).

    Returns:
        List of BundleResult objects containing manifest paths.
    """
    print_step(8, "Bundling PDFs")

    config = load_config(config_dir / "parameters.yaml")

    parameters_path = config_dir / "parameters.yaml"

    results = bundle_pdfs.bundle_pdfs_with_config(
        output_dir,
        None,
        run_id,
        parameters_path,
    )
    if results:
        print(f"Created {len(results)} bundles in {output_dir / 'pdf_combined'}")

        bundling_config = config.get("bundling", {})
        bundle_size = bundling_config.get("bundle_size", 0)
        group_by = bundling_config.get("group_by")

        print(f"📦 Bundle size:             {bundle_size}")
        if group_by == "school":
            print("🏫 Bundle scope:            School")
        elif group_by == "board":
            print("🏢 Bundle scope:            Board")
        else:
            print("🏷️  Bundle scope:            Sequential")

        if results:
            print("📋 Bundle manifests:")
            for result in results:
                print(f"    - {result.manifest_path}")

    return results


def run_step_9_cleanup(
    output_dir: Path,
    config_dir: Path,
) -> None:
    """Step 9: Cleanup intermediate files."""
    print_step(9, "Cleanup")

    parameters_path = config_dir / "parameters.yaml"
    cleanup.main(output_dir, parameters_path)
    print("✅ Cleanup completed successfully.")


def print_summary(
    step_times: list[tuple[str, float]],
    total_duration: float,
    total_clients: int,
) -> None:
    """Print the pipeline summary."""
    print()
    print(f"{'=' * 60}")
    print("🎉 Pipeline completed successfully!")
    print(f"{'=' * 60}")
    print()
    print("🕒 Time Summary:")
    for step_name, duration in step_times:
        print(f"  - {step_name:<25} {duration:.1f}s")
    print(f"  - {'─' * 25} {'─' * 6}")
    print(f"  - {'Total Time':<25} {total_duration:.1f}s")
    print()
    print(f"👥 Clients processed:      {total_clients}")


def main() -> int:
    """Run the pipeline orchestrator."""
    try:
        args = parse_args()
        validate_args(args)
    except (ValueError, SystemExit) as exc:
        if isinstance(exc, ValueError):
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        raise

    output_dir = args.output_dir.resolve()
    config_dir = args.config_dir.resolve()
    log_dir = output_dir / "logs"
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    try:
        config = load_config(config_dir / "parameters.yaml")
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    encryption_enabled = config.get("encryption", {}).get("enabled", False)
    notice_versioning_cfg = config.get("notice_versioning", {})
    extra_manifest_rows_policy = notice_versioning_cfg.get(
        "extra_manifest_rows", "error"
    )

    # Load catalog and manifest before Step 1 so infrastructure errors fail fast.
    catalog: Optional[NoticeVersionCatalog] = None
    manifest: Optional[dict] = None
    if args.notice_assignments:
        catalog = load_catalog(config_dir)
        manifest = load_manifest(args.notice_assignments)

    # Effective language for steps 3/6/7/8 that need a single language tag.
    # In manifest mode args.language is None; fall back to catalog default.

    print_header(args.input_file)

    total_start = time.time()
    step_times = []
    total_clients = 0

    try:
        # Step 1: Prepare output directory
        step_start = time.time()
        if not run_step_1_prepare_output(output_dir, log_dir, config_dir):
            return 2
        step_duration = time.time() - step_start
        step_times.append(("Output Preparation", step_duration))
        print_step_complete(1, "Output directory prepared", step_duration)

        # Step 2: Preprocessing
        step_start = time.time()
        total_clients, reconciliation_result = run_step_2_preprocess(
            args.input_dir,
            args.input_file,
            output_dir,
            args.language,
            run_id,
            config_dir,
            catalog=catalog,
            manifest=manifest,
        )
        step_duration = time.time() - step_start
        step_times.append(("Preprocessing", step_duration))
        print_step_complete(2, "Preprocessing", step_duration)

        # Preflight gate (manifest mode only)
        if reconciliation_result is not None:
            print_preflight_summary(reconciliation_result)
            if has_errors(reconciliation_result, extra_manifest_rows_policy):
                print(
                    "\n❌ Manifest preflight failed. Correct the errors above and retry.",
                    file=sys.stderr,
                )
                return 1

        # Step 3: Generating QR Codes (optional)
        step_start = time.time()
        qr_count = run_step_3_generate_qr_codes(
            output_dir,
            run_id,
            config_dir,
        )
        step_duration = time.time() - step_start
        if qr_count > 0:
            step_times.append(("QR Code Generation", step_duration))
            print_step_complete(3, "QR code generation", step_duration)
        else:
            print("QR code generation skipped (disabled or no clients).")

        # Step 4: Generating Notices
        step_start = time.time()
        run_step_4_generate_notices(
            output_dir,
            run_id,
            args.template_dir,
            config_dir,
        )
        step_duration = time.time() - step_start
        step_times.append(("Notice Data Preparation", step_duration))
        print_step_complete(4, "Notice data preparation", step_duration)

        # Step 5: Compiling Notices
        step_start = time.time()
        run_step_5_compile_notices(
            output_dir,
            config_dir,
            args.template_dir,
        )
        step_duration = time.time() - step_start
        step_times.append(("Template Compilation", step_duration))
        print_step_complete(5, "Compilation", step_duration)

        # Step 6: Validating PDFs
        step_start = time.time()
        run_step_6_validate_pdfs(output_dir, run_id, config_dir)
        step_duration = time.time() - step_start
        step_times.append(("PDF Validation", step_duration))
        print_step_complete(6, "PDF validation", step_duration)

        # Step 7: Encrypting PDFs (optional)
        if encryption_enabled:
            step_start = time.time()
            run_step_7_encrypt_pdfs(output_dir, run_id, config_dir)
            step_duration = time.time() - step_start
            step_times.append(("PDF Encryption", step_duration))
            print_step_complete(7, "Encryption", step_duration)

        # Step 8: Bundling PDFs (optional, independent of encryption)
        bundling_config = config.get("bundling", {})
        bundle_size = bundling_config.get("bundle_size", 0)

        if bundle_size > 0:
            step_start = time.time()
            run_step_8_bundle_pdfs(
                output_dir,
                run_id,
                config_dir,
            )
            step_duration = time.time() - step_start
            step_times.append(("PDF Bundling", step_duration))
            print_step_complete(8, "Bundling", step_duration)
        else:
            print_step(8, "Bundling")
            print("Bundling skipped (bundle_size set to 0).")

        # Step 9: Cleanup
        run_step_9_cleanup(output_dir, config_dir)

        total_duration = time.time() - total_start

        print_summary(
            step_times,
            total_duration,
            total_clients,
        )

        return 0

    except Exception as exc:
        print(f"\n❌ Pipeline failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
