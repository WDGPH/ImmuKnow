"""Reevaluate saved originals and rebuild grouped bundles with findings CSVs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import bundle_pdfs, validation_policy


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild grouped bundles and findings CSVs from a saved run",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
        epilog="""
Inspect report.html and the original PDF first. Each warning in the latest
attempt's evaluation has a token bound to that run, row, PDF, evidence and rules.
Accept individual warnings using those exact tokens:
  immuknow-rebundle ./runs/<run-id> --accept-warning <token> --reason "Reviewed layout"
Repeat --accept-warning for each warning reviewed. Acceptance remains in run.json
and applies only while the evidence is unchanged. Failed original checks prevent
eligibility; accepting a warning cannot waive them. Unknown or stale tokens
are refused. No blanket warning allowance or force-delivery choice exists.

Use --withhold row-000001 (repeatable) to replace the set of withheld originals;
--clear-withheld clears that set. Omitting both retains the prior selection.
Withholding marks review status; it does not exclude pages from bundles.
It is separate from warning acceptance. Missing external identifiers
never require name matching: review is bound to the immutable source row.

All readable originals share one bundle set using the saved grouping and size.
Each PDF has a matching findings CSV with review status and page references.
Successful assembly does not mean every notice is eligible for delivery.
The previous bundle set survives a failed replacement. This command does not
reread source data, recompile notices or rerun encryption. Only run format 2 is
supported. Exit status describes this attempt; earlier failures remain recorded.
""",
    )
    parser.add_argument(
        "run_directory", type=Path, help="Saved run containing run.json and originals/"
    )
    parser.add_argument(
        "--accept-warning",
        action="append",
        default=[],
        metavar="TOKEN",
        help="Accept one current warning token after inspecting its PDF",
    )
    parser.add_argument("--reason", help="Required explanation for warning acceptance")
    parser.add_argument(
        "--policy",
        type=Path,
        help="Replace rule settings using a JSON file; omitted settings return to defaults",
    )
    withholding = parser.add_mutually_exclusive_group()
    withholding.add_argument(
        "--withhold",
        action="append",
        metavar="ROW_KEY",
        help="Mark rows as held for review; all remain in bundles (repeatable)",
    )
    withholding.add_argument(
        "--clear-withheld",
        action="store_true",
        help="Clear withheld rows; checks and warning acceptance still apply",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_dir = args.run_directory.resolve()
    try:
        attempt = bundle_pdfs.bundle_run(
            run_dir,
            accept=args.accept_warning,
            reason=args.reason,
            withhold=[] if args.clear_withheld else args.withhold,
            policy=validation_policy.read_policy(args.policy) if args.policy else None,
        )
        print(f"Rebundling {attempt['status']}. Report: {run_dir / 'report.html'}")
        return 0 if attempt["status"] == "completed" else 1
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
