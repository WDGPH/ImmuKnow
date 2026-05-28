"""Validate compiled PDFs for layout, structure, and quality issues.

Performs comprehensive validation of compiled PDF files including page counts,
layout checks (signature placement), and structural integrity. Outputs validation
results to JSON metadata for downstream processing and optional console warnings.

**Input Contract:**
- Reads PDF files from output/pdf_individual/ directory
- Assumes PDFs are valid (created by compilation step)
- Assumes each PDF corresponds to one client notice

**Output Contract:**
- Writes validation results to JSON: output/metadata/{language}_validation_{run_id}.json
- Records per-PDF validations: page counts, layout warnings, structural issues
- Aggregate statistics: total PDFs, warnings by type, pass/fail counts
- Optional console output (controlled by config: pdf_validation.print_warnings)

**Error Handling:**
- Invalid/corrupt PDFs raise immediately (fail-fast; quality validation step)
- Missing PDF files raise immediately (infrastructure error)
- Layout warnings are non-fatal (logged but don't halt pipeline)
- All PDFs must be readable; validation results may contain warnings (quality step)

**Validation Contract:**

What this module validates:
- PDF files are readable and structurally valid (uses PdfReader)
- Page count statistics and distribution
- Layout markers (signature block placement using MARK_END_SIGNATURE_BLOCK)
- Expected vs actual page counts (configurable tolerance)

What this module assumes (validated upstream):
- PDF files exist and are complete (created by compile step)
- PDF filenames match expected pattern (from notice generation)
- Output metadata directory can be created (general I/O)

Note: This is a validation/QA step. Structural PDF errors halt pipeline (fail-fast),
but layout warnings are non-fatal and logged for review.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List

from pypdf import PdfReader

from .config_loader import load_config


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
    language : str | None
        Language code if filtered (e.g., 'en' or 'fr')
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

    language: str | None
    total_pdfs: int
    passed_count: int
    warning_count: int
    page_count_distribution: dict[int, int]
    warning_types: dict[str, int]
    rule_results: List[RuleResult]
    results: List[ValidationResult]


def discover_pdfs(target: Path) -> List[Path]:
    """Discover all PDF files at the given target path.

    Parameters
    ----------
    target : Path
        Either a directory containing PDFs or a single PDF file.

    Returns
    -------
    List[Path]
        Sorted list of PDF file paths.

    Raises
    ------
    FileNotFoundError
        If target is neither a PDF file nor a directory containing PDFs.
    """
    if target.is_dir():
        return sorted(target.glob("*.pdf"))
    if target.is_file() and target.suffix.lower() == ".pdf":
        return [target]
    raise FileNotFoundError(f"No PDF(s) found at {target}")


def filter_by_language(files: List[Path], language: str | None) -> List[Path]:
    """Filter PDF files by language prefix in filename.

    Parameters
    ----------
    files : List[Path]
        PDF file paths to filter.
    language : str | None
        Language code to filter by (e.g., 'en' or 'fr'). If None, returns all files.

    Returns
    -------
    List[Path]
        Filtered list of PDF paths, or all files if language is None.
    """
    if not language:
        return list(files)
    prefix = f"{language}_"
    return [path for path in files if path.name.startswith(prefix)]


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
    import re

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
    import re

    measurements = {}

    # Pattern to match our invisible marker format: MEASURE_NAME:123.45
    pattern = r"MEASURE_(\w+):([\d.]+)"

    for match in re.finditer(pattern, page_text):
        key = "measure_" + match.group(1).lower()  # normalize to lowercase
        value = float(match.group(2))
        measurements[key] = value

    return measurements


def validate_pdf_layout(
    pdf_path: Path,
    reader: PdfReader,
    enabled_rules: dict[str, str],
    client_id_map: dict[str, str] | None = None,
    client_metadata_map: dict[str, dict[str, object]] | None = None,
) -> tuple[List[str], dict[str, float]]:
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
    client_metadata_map : dict[str, dict], optional
        Additional per-client metadata (PHIX validation scope, school name, etc.)
        injected into per-PDF measurements for audit trails.

    Returns
    -------
    tuple[List[str], dict[str, float]]
        Tuple of (warning messages, actual measurements).
        Measurements include signature_page, contact_height_inches, etc.
    """
    warnings = []
    measurements = {}

    # Check signature block marker placement
    rule_setting = enabled_rules.get("signature_overflow", "warn")
    if rule_setting != "disabled":
        for page_num, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text()
                if "MARK_END_SIGNATURE_BLOCK" in page_text:
                    measurements["signature_page"] = page_num
                    if page_num != 1:
                        warnings.append(
                            f"signature_overflow: Signature block ends on page {page_num} "
                            f"(expected page 1)"
                        )
                    break
            except Exception:
                # If text extraction fails, skip this check
                pass

    # Check contact table dimensions (envelope window validation)
    envelope_rule = enabled_rules.get("envelope_window_1_125", "disabled")
    if envelope_rule != "disabled":
        # Envelope window constraint: 1.125 inches max height
        max_height_inches = 1.125

        # Look for contact table measurements in page 1
        try:
            page_text = reader.pages[0].extract_text()
            extracted_measurements = extract_measurements_from_markers(page_text)

            contact_height_pt = extracted_measurements.get("measure_contact_height")
            if contact_height_pt:
                # Convert from points to inches (72 points = 1 inch)
                height_inches = contact_height_pt / 72.0
                measurements["contact_height_inches"] = height_inches

                if height_inches > max_height_inches:
                    warnings.append(
                        f"envelope_window_1_125: Contact table height {height_inches:.2f}in "
                        f"exceeds envelope window (max {max_height_inches}in)"
                    )
        except Exception:
            # If measurement extraction fails, skip this check
            pass

    # Check client ID presence (markerless: search for 10-digit number in text)
    client_id_rule = enabled_rules.get("client_id_presence", "disabled")
    if client_id_rule != "disabled" and client_id_map:
        try:
            # Get expected client ID from the mapping (source of truth: preprocessed_clients.json)
            expected_client_id = client_id_map.get(pdf_path.name)
            if expected_client_id:
                # Search all pages for the client ID
                found_client_id = None
                for page_num, page in enumerate(reader.pages, start=1):
                    page_text = page.extract_text()
                    found_id = find_client_id_in_text(page_text)
                    if found_id:
                        found_client_id = found_id
                        measurements["client_id_found_page"] = page_num
                        break

                # Warn if ID not found or doesn't match
                if found_client_id is None:
                    warnings.append(
                        f"client_id_presence: Client ID {expected_client_id} not found in PDF"
                    )
                elif found_client_id != expected_client_id:
                    warnings.append(
                        f"client_id_presence: Found ID {found_client_id}, expected {expected_client_id}"
                    )
                else:
                    # Store the found ID for debugging
                    measurements["client_id_found_value"] = found_client_id
        except Exception:
            # If client ID check fails, skip silently (parsing error)
            pass

    if client_metadata_map:
        meta = client_metadata_map.get(pdf_path.name, {})
        phix_meta = meta.get("phix_validation") or {}
        target_phu_code = meta.get("phix_target_phu_code") or phix_meta.get("target_phu_code")
        target_phu_label = meta.get("phix_target_phu_label") or phix_meta.get("target_phu_label")
        matched_phu_code = phix_meta.get("phu_code")
        matched_phu_name = phix_meta.get("phu_name")
        match_type = phix_meta.get("match_type")
        match_confidence = phix_meta.get("confidence", 0)
        facility_name = meta.get("school_name")

        measurements["phix_target_phu_code"] = target_phu_code or ""
        measurements["phix_target_phu_label"] = target_phu_label or ""
        measurements["phix_matched_phu_code"] = matched_phu_code or ""
        measurements["phix_matched_phu_name"] = matched_phu_name or ""
        measurements["phix_match_type"] = match_type or ""
        try:
            measurements["phix_match_confidence"] = int(match_confidence or 0)
        except (TypeError, ValueError):
            measurements["phix_match_confidence"] = 0
        if facility_name:
            measurements["phix_facility_school"] = facility_name

        if (
            target_phu_code
            and matched_phu_code
            and target_phu_code != matched_phu_code
        ):
            warnings.append(
                "phix_target_phu: Facility PHU code "
                f"{matched_phu_code} does not match template PHU {target_phu_code}"
            )

    return warnings, measurements


def validate_pdf_structure(
    pdf_path: Path,
    enabled_rules: dict[str, str] | None = None,
    client_id_map: dict[str, str] | None = None,
    client_metadata_map: dict[str, dict[str, object]] | None = None,
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
    client_metadata_map : dict[str, dict], optional
        Per-PDF metadata (PHIX validation scope, school name, etc.) to include in
        measurements and warnings.

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
        pdf_path,
        reader,
        enabled_rules,
        client_id_map=client_id_map,
        client_metadata_map=client_metadata_map,
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
        for warning in result.warnings:
            rule_name = warning.split(":")[0] if ":" in warning else "other"
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
    client_metadata_map: dict[str, dict[str, object]] | None = None,
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
    client_metadata_map : dict[str, dict], optional
        Per-PDF metadata (PHIX validation scope, school name, etc.).

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
            pdf_path,
            enabled_rules=enabled_rules,
            client_id_map=client_id_map,
            client_metadata_map=client_metadata_map,
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
        language=None,  # Set by caller
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


def main(
    target: Path,
    language: str | None = None,
    enabled_rules: dict[str, str] | None = None,
    json_output: Path | None = None,
    client_id_map: dict[str, str] | None = None,
    config_dir: Path | None = None,
    client_metadata_map: dict[str, dict[str, object]] | None = None,
) -> ValidationSummary:
    """Main entry point for PDF validation.

    Parameters
    ----------
    target : Path
        PDF file or directory containing PDFs.
    language : str, optional
        Optional language prefix to filter PDF filenames (e.g., 'en').
    enabled_rules : dict[str, str], optional
        Validation rules configuration (rule_name -> "disabled"/"warn"/"error").
        If not provided and config_dir is given, loads from config_dir/parameters.yaml.
    json_output : Path, optional
        Optional path to write validation summary as JSON.
    client_id_map : dict[str, str], optional
        Mapping of PDF filename to expected client ID (from preprocessed_clients.json).
    config_dir : Path, optional
        Path to config directory containing parameters.yaml.
        Used to load enabled_rules if not explicitly provided.
        If not provided, uses default location (config/parameters.yaml in project root).
    client_metadata_map : dict[str, dict], optional
        Additional metadata (PHIX validation scope, school name, etc.) to inject
        into per-PDF measurements for downstream auditing.

    Returns
    -------
    ValidationSummary
        Validation summary with all results and statistics.

    Raises
    ------
    RuntimeError
        If any validation rule with severity 'error' fails.
    """
    # Load enabled_rules from config if not provided
    if enabled_rules is None:
        config_path = None if config_dir is None else config_dir / "parameters.yaml"
        config = load_config(config_path)
        validation_config = config.get("pdf_validation", {})
        enabled_rules = validation_config.get("rules", {})

    if client_id_map is None:
        client_id_map = {}
    if client_metadata_map is None:
        client_metadata_map = {}

    files = discover_pdfs(target)
    filtered = filter_by_language(files, language)
    summary = validate_pdfs(
        filtered,
        enabled_rules=enabled_rules,
        client_id_map=client_id_map,
        client_metadata_map=client_metadata_map,
    )
    summary.language = language

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


if __name__ == "__main__":
    import sys

    print(
        "⚠️  Direct invocation: This module is typically executed via orchestrator.py.\n"
        "   Re-running a single step is valid when pipeline artifacts are retained on disk,\n"
        "   allowing you to skip earlier steps and regenerate output.\n"
        "   Note: Output will overwrite any previous files.\n"
        "\n"
        "   For typical usage, run: uv run viper <input> <language>\n",
        file=sys.stderr,
    )
    sys.exit(1)
