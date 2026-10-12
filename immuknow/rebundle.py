"""Rebuild a saved run's bundles from unchanged original PDFs and explicit choices."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import bundle_pdfs, run_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebundle saved originals without rereading facts or recompiling notices",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
        epilog="""
Example:
  immuknow-rebundle ./runs/<run-id> --overrides ./runs/<run-id>/overrides.json

Overrides are a UTF-8 JSON object:
{
  "allow_delivery_warnings": ["data.school_unmatched"],
  "clients": {"1234567890": "delivery", "1234567891": "review"}
}

An explicit client destination wins. Otherwise, any warning not allowed for
delivery selects review. Warnings always remain in the report. IDs must be
unique ten-digit source IDs; unknown IDs, warning-code typos and duplicate
JSON keys are rejected. A choice cannot invent a PDF or complete failed checks.
Review bundles add a sheet and red mark to copies. Delivery always uses the
unchanged originals. This command verifies hashes, preserves the previous set
if replacement fails, and never reruns encryption. Source CSV and authored
project directories are not needed. Only run format version 1 is supported.
Exit status describes this rebundling attempt; earlier failures remain recorded.
""",
    )
    parser.add_argument(
        "run_directory",
        type=Path,
        help="Saved run directory containing run.json and originals/",
    )
    parser.add_argument(
        "--overrides",
        type=Path,
        help="Override JSON path (default: <run-directory>/overrides.json)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = args.run_directory.resolve()
    try:
        record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        if (
            not isinstance(record, dict)
            or record.get("format_version") != run_report.RUN_FORMAT_VERSION
        ):
            raise ValueError(
                "Unsupported run format; rebundling requires format version 1"
            )
        attempt = bundle_pdfs.bundle_run(run_dir, record, args.overrides)
        print(f"Rebundling {attempt['status']}. Report: {run_dir / 'report.html'}")
        return 0 if attempt["status"] == "completed" else 1
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
