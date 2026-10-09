"""Validate every expected compiled notice for structure and layout.

The render-job manifest supplies the complete PDF list. Validation writes an
audit summary and raises when an error-severity rule fails; layout warnings
remain available for review.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List

from pypdf import PdfReader


@dataclass
class ValidationResult:
    """Result of validating a single PDF file.

    Attributes
    ----------
    filename : str
        Name of the PDF file
    warnings : List[str]
        List of validation warnings (layout issues, unexpected page counts, etc.)
    passed : bool
        True if no warnings, False otherwise
    measurements : dict[str, int | float | str]
        Actual measurements extracted from PDF with proper types:

        - page_count (int): Number of pages
        - signature_page (int): Page where signature block ends
        - contact_height_inches (float): Contact table height in inches
        - client_id_found_page (int): Page where client ID was found
        - client_id_found_value (str): The actual client ID found
    """

    filename: str
    warnings: List[str]
    passed: bool
    measurements: dict[str, int | float | str]


@dataclass
class RuleResult:
    """Result of a single validation rule across all PDFs.

    Attributes
    ----------
    rule_name : str
        Name of the validation rule
    severity : str
        Rule severity: "disabled", "warn", or "error"
    passed_count : int
        Number of PDFs that passed this rule
    failed_count : int
        Number of PDFs that failed this rule
    """

    rule_name: str
    severity: str
    passed_count: int
    failed_count: int


@dataclass
class ValidationSummary:
    """Aggregate validation results for all PDFs.

    Attributes
    ----------
    total_pdfs : int
        Total number of PDFs validated
    passed_count : int
        Number of PDFs with no warnings
    warning_count : int
        Number of PDFs with warnings
    page_count_distribution : dict[int, int]
        Distribution of page counts (pages -> count)
    warning_types : dict[str, int]
        Count of warnings by type/category
    rule_results : List[RuleResult]
        Per-rule validation statistics
    results : List[ValidationResult]
        Per-file validation results
    """

    total_pdfs: int
    passed_count: int
    warning_count: int
    page_count_distribution: dict[int, int]
    warning_types: dict[str, int]
    rule_results: List[RuleResult]
    results: List[ValidationResult]


def find_client_id_in_text(page_text: str) -> str | None:
    """Find a 10-digit client ID in extracted PDF page text.

    Searches for any 10-digit number; assumes the first match is the client ID.
    May be preceded by "Client ID: " or "Identifiant du client: " (optional).

    Parameters
    ----------
    page_text : str
        Extracted text from a PDF page.

    Returns
    -------
    str | None
        10-digit client ID if found, None otherwise.
    """
    # Search for any 10-digit number (word boundary on both sides to avoid false matches)
    match = re.search(r"\b(\d{10})\b", page_text)
    if match:
        return match.group(1)
    return None


def extract_measurements_from_markers(page_text: str) -> dict[str, float]:
    """Extract dimension measurements from invisible text markers.

    Typst templates embed invisible markers with measurements like:
    MEASURE_CONTACT_HEIGHT:123.45

    Parameters
    ----------
    page_text : str
        Extracted text from a PDF page.

    Returns
    -------
    dict[str, float]
        Dictionary mapping dimension names to values in points.
        Example: {"measure_contact_height": 123.45}
    """
    measurements = {}

    # Pattern to match our invisible marker format: MEASURE_NAME:123.45
    pattern = r"MEASURE_(\w+):(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)"

    for match in re.finditer(pattern, page_text):
        key = "measure_" + match.group(1).lower()  # normalize to lowercase
        value = float(match.group(2))
        if key in measurements or not math.isfinite(value):
            raise ValueError(f"Duplicate or nonfinite layout measurement: {key}")
        measurements[key] = value

    return measurements


def validate_pdf_layout(
    pdf_path: Path,
    reader: PdfReader,
    enabled_rules: dict[str, str],
    client_id_map: dict[str, str] | None = None,
) -> tuple[List[str], dict[str, float | str]]:
    """Check PDF for layout issues using invisible markers and metadata.

    Parameters
    ----------
    pdf_path : Path
        Path to the PDF file being validated.
    reader : PdfReader
        Opened PDF reader instance.
    enabled_rules : dict[str, str]
        Validation rules configuration (rule_name -> "disabled"/"warn"/"error").
    client_id_map : dict[str, str], optional
        Mapping of PDF filename (without path) to expected client ID.
        If provided, client_id_presence validation uses this as source of truth.

    Returns
    -------
    tuple[List[str], dict[str, float]]
        Tuple of (warning messages, actual measurements).
        Measurements include signature_page, contact_height_inches, etc.
    """
    warnings = []
    measurements = {}

    texts = [page.extract_text() for page in reader.pages]
    if enabled_rules.get("signature_overflow", "warn") != "disabled":
        signature_pages = [
            number
            for number, text in enumerate(texts, 1)
            for _ in range(text.count("MARK_END_SIGNATURE_BLOCK"))
        ]
        if len(signature_pages) != 1:
            warnings.append(
                "signature_overflow: Expected exactly one signature measurement marker"
            )
        else:
            measurements["signature_page"] = signature_pages[0]
            if signature_pages[0] != 1:
                warnings.append(
                    f"signature_overflow: Signature block ends on page {signature_pages[0]} (expected page 1)"
                )

    envelope_rules = [
        name
        for name in ("envelope_window", "envelope_window_1_125")
        if enabled_rules.get(name, "disabled") != "disabled"
    ]
    if envelope_rules:
        try:
            values = extract_measurements_from_markers(texts[0])
        except ValueError as exc:
            values = {}
            for rule in envelope_rules:
                warnings.append(f"{rule}: {exc}")
        if "envelope_window_1_125" in envelope_rules:
            height = values.get("measure_contact_height")
            if height is None or height <= 0:
                warnings.append(
                    "envelope_window_1_125: Missing or invalid contact-height measurement"
                )
            else:
                measurements["contact_height_inches"] = height / 72.0
                if height > 81.01:
                    warnings.append(
                        f"envelope_window_1_125: Contact table height {height / 72:.2f}in exceeds envelope window (max 1.125in)"
                    )
        if "envelope_window" in envelope_rules:
            required = (
                "layout_version",
                "window_x",
                "window_y",
                "window_width",
                "window_height",
                "window_padding",
                "address_x",
                "address_y",
                "address_width",
                "address_height",
                "address_page",
            )
            missing = [key for key in required if "measure_" + key not in values]
            if missing:
                warnings.append(
                    "envelope_window: Missing geometry evidence: " + ", ".join(missing)
                )
            else:
                geometry = {key: values["measure_" + key] for key in required}
                measurements.update(geometry)
                x, y, width, height, padding = (
                    geometry["window_" + key]
                    for key in ("x", "y", "width", "height", "padding")
                )
                ax, ay, aw, ah = (
                    geometry["address_" + key] for key in ("x", "y", "width", "height")
                )
                page = reader.pages[0].mediabox
                valid = (
                    geometry["layout_version"] == 1
                    and geometry["address_page"] == 1
                    and min(x, y, padding, aw, ah) >= 0
                    and width > 2 * padding
                    and height > 2 * padding
                    and x + width <= float(page.width) + 0.01
                    and y + height <= float(page.height) + 0.01
                )
                if not valid:
                    warnings.append("envelope_window: Invalid window or page geometry")
                elif not (
                    ax >= x + padding - 0.01
                    and ay >= y + padding - 0.01
                    and ax + aw <= x + width - padding + 0.01
                    and ay + ah <= y + height - padding + 0.01
                ):
                    warnings.append(
                        "envelope_window: Address exceeds the window safety area; enlarge or reposition the window, or revise the address layout"
                    )

    if enabled_rules.get("client_id_presence", "disabled") != "disabled":
        expected = (client_id_map or {}).get(pdf_path.name)
        if not expected:
            warnings.append("client_id_presence: Missing expected client identity")
        else:
            found = [
                (number, find_client_id_in_text(text))
                for number, text in enumerate(texts, 1)
            ]
            found = [(number, value) for number, value in found if value is not None]
            if not found:
                warnings.append(
                    f"client_id_presence: Client ID {expected} not found in PDF"
                )
            elif found[0][1] != expected:
                warnings.append(
                    f"client_id_presence: Found ID {found[0][1]}, expected {expected}"
                )
            else:
                measurements["client_id_found_page"] = found[0][0]
                measurements["client_id_found_value"] = expected

    return warnings, measurements


def validate_pdf_structure(
    pdf_path: Path,
    enabled_rules: dict[str, str] | None = None,
    client_id_map: dict[str, str] | None = None,
) -> ValidationResult:
    """Validate a single PDF file for structure and layout.

    Parameters
    ----------
    pdf_path : Path
        Path to the PDF file to validate.
    enabled_rules : dict[str, str], optional
        Validation rules configuration (rule_name -> "disabled"/"warn"/"error").
    client_id_map : dict[str, str], optional
        Mapping of PDF filename to expected client ID (from preprocessed_clients.json).

    Returns
    -------
    ValidationResult
        Validation result with measurements, warnings, and pass/fail status.

    Raises
    ------
    Exception
        If PDF cannot be read (structural corruption).
    """
    warnings = []
    measurements = {}
    if enabled_rules is None:
        enabled_rules = {}

    # Read PDF and count pages
    reader = PdfReader(str(pdf_path))
    page_count = len(reader.pages)
    measurements["page_count"] = page_count

    # Check for exactly 2 pages (standard notice format)
    rule_setting = enabled_rules.get("exactly_two_pages", "warn")
    if rule_setting != "disabled":
        if page_count != 2:
            warnings.append(f"exactly_two_pages: has {page_count} pages (expected 2)")

    # Validate layout using markers
    layout_warnings, layout_measurements = validate_pdf_layout(
        pdf_path, reader, enabled_rules, client_id_map=client_id_map
    )
    warnings.extend(layout_warnings)
    measurements.update(layout_measurements)

    return ValidationResult(
        filename=pdf_path.name,
        warnings=warnings,
        passed=len(warnings) == 0,
        measurements=measurements,
    )


def compute_rule_results(
    results: List[ValidationResult], enabled_rules: dict[str, str]
) -> List[RuleResult]:
    """Compute per-rule pass/fail statistics.

    Parameters
    ----------
    results : List[ValidationResult]
        Validation results for all PDFs.
    enabled_rules : dict[str, str]
        Validation rules configuration (rule_name -> "disabled"/"warn"/"error").

    Returns
    -------
    List[RuleResult]
        Per-rule statistics with pass/fail counts.
    """
    # Count failures per rule
    rule_failures: Counter = Counter()
    for result in results:
        for rule_name in {
            warning.split(":")[0] if ":" in warning else "other"
            for warning in result.warnings
        }:
            rule_failures[rule_name] += 1

    # Build rule results for all configured rules
    rule_results = []
    for rule_name, severity in enabled_rules.items():
        failed_count = rule_failures.get(rule_name, 0)
        passed_count = len(results) - failed_count

        rule_results.append(
            RuleResult(
                rule_name=rule_name,
                severity=severity,
                passed_count=passed_count,
                failed_count=failed_count,
            )
        )

    return rule_results


def validate_pdfs(
    files: List[Path],
    enabled_rules: dict[str, str] | None = None,
    client_id_map: dict[str, str] | None = None,
) -> ValidationSummary:
    """Validate all PDF files and generate summary.

    Parameters
    ----------
    files : List[Path]
        PDF file paths to validate.
    enabled_rules : dict[str, str], optional
        Validation rules configuration (rule_name -> "disabled"/"warn"/"error").
    client_id_map : dict[str, str], optional
        Mapping of PDF filename to expected client ID (from preprocessed_clients.json).

    Returns
    -------
    ValidationSummary
        Aggregate validation results with statistics and per-file details.
    """
    if enabled_rules is None:
        enabled_rules = {}
    if client_id_map is None:
        client_id_map = {}

    results: List[ValidationResult] = []
    page_buckets: Counter = Counter()
    warning_type_counts: Counter = Counter()

    for pdf_path in files:
        result = validate_pdf_structure(
            pdf_path, enabled_rules=enabled_rules, client_id_map=client_id_map
        )
        results.append(result)
        page_count = int(result.measurements.get("page_count", 0))
        page_buckets[page_count] += 1

        # Count warning types
        for warning in result.warnings:
            warning_type = warning.split(":")[0] if ":" in warning else "other"
            warning_type_counts[warning_type] += 1

    passed_count = sum(1 for r in results if r.passed)
    warning_count = len(results) - passed_count

    # Compute per-rule statistics
    rule_results = compute_rule_results(results, enabled_rules)

    return ValidationSummary(
        total_pdfs=len(results),
        passed_count=passed_count,
        warning_count=warning_count,
        page_count_distribution=dict(sorted(page_buckets.items())),
        warning_types=dict(warning_type_counts),
        rule_results=rule_results,
        results=results,
    )


def print_validation_summary(
    summary: ValidationSummary,
    *,
    validation_json_path: Path | None = None,
) -> None:
    """Print human-readable validation summary to console.

    Parameters
    ----------
    summary : ValidationSummary
        Validation summary to print.
    validation_json_path : Path, optional
        Path to validation JSON for reference in output.
    """
    # Per-rule summary (all rules, including disabled)
    print("Validation rules:")
    for rule in summary.rule_results:
        status_str = f"- {rule.rule_name} [{rule.severity}]"
        count_str = f"✓ {rule.passed_count} passed"

        if rule.failed_count > 0:
            fail_label = "PDF" if rule.failed_count == 1 else "PDFs"
            count_str += f", ✗ {rule.failed_count} {fail_label} failed"

        print(f"  {status_str}: {count_str}")

    # Reference to detailed log
    if validation_json_path:
        try:
            relative_path = validation_json_path.relative_to(Path.cwd())
            print(f"\nDetailed validation results: {relative_path}")
        except ValueError:
            # If path is not relative to cwd (e.g., in temp dir), use absolute
            print(f"\nDetailed validation results: {validation_json_path}")


def write_validation_json(summary: ValidationSummary, output_path: Path) -> None:
    """Write validation summary to JSON file.

    Parameters
    ----------
    summary : ValidationSummary
        Validation summary to serialize.
    output_path : Path
        Path to output JSON file.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert to dict and serialize
    payload = asdict(summary)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def check_for_errors(
    summary: ValidationSummary, enabled_rules: dict[str, str]
) -> List[str]:
    """Check if any validation rules are set to 'error' and have failures.

    Parameters
    ----------
    summary : ValidationSummary
        Validation summary with warning counts by type.
    enabled_rules : dict[str, str]
        Validation rules configuration (rule_name -> "disabled"/"warn"/"error").

    Returns
    -------
    List[str]
        List of error messages for rules that failed with severity 'error'.
    """
    errors = []
    for rule_name, severity in enabled_rules.items():
        if severity == "error" and rule_name in summary.warning_types:
            count = summary.warning_types[rule_name]
            label = "PDF" if count == 1 else "PDFs"
            errors.append(f"{rule_name}: {count} {label} failed validation")
    return errors


def validate_notices(
    expected_pdfs: List[Path],
    enabled_rules: dict[str, str] | None = None,
    json_output: Path | None = None,
    client_id_map: dict[str, str] | None = None,
) -> ValidationSummary:
    """Validate every expected PDF and fail on any configured error.

    Writes a run-local diagnostic summary before raising a validation error.
    """
    enabled_rules = enabled_rules or {}

    if client_id_map is None:
        client_id_map = {}

    for pdf in expected_pdfs:
        if not pdf.is_file():
            raise FileNotFoundError(f"Expected notice PDF is missing: {pdf}")
    summary = validate_pdfs(
        expected_pdfs, enabled_rules=enabled_rules, client_id_map=client_id_map
    )

    if json_output:
        write_validation_json(summary, json_output)

    # Always print summary
    print_validation_summary(summary, validation_json_path=json_output)

    # Check for error-level failures
    errors = check_for_errors(summary, enabled_rules)
    if errors:
        error_msg = "PDF validation failed with errors:\n  " + "\n  ".join(errors)
        raise RuntimeError(error_msg)

    return summary
