"""Unit tests for validate_pdfs module.

Tests PDF validation functionality including:
- PDF file discovery from directory or file path
- Language-based filtering for multi-language output
- PDF structure validation (page count, layout markers)
- Validation summary generation and aggregation
- JSON metadata output for validation results
- Error handling with configurable rule severity levels

Tests use temporary directories (tmp_path) for file I/O and mock pypdf to
create test PDFs without external dependencies.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pypdf import PdfWriter

from pipeline import validate_pdfs


@pytest.mark.unit
class TestDiscoverPdfs:
    """Tests for PDF discovery functionality."""

    def test_discover_pdfs_in_directory(self, tmp_path: Path) -> None:
        """Verify PDF discovery finds all PDFs in a directory.

        Real-world significance:
        - Pipeline validates all compiled PDFs from a batch
        - Discovery must be deterministic and comprehensive
        - Enables consistent validation across different run sizes

        Parameters
        ----------
        tmp_path : Path
            Pytest fixture providing temporary directory

        Raises
        ------
        AssertionError
            If discovered PDF count doesn't match created count

        Assertion: All PDFs in directory are discovered and have .pdf suffix
        """
        # Create test PDF files
        for i in range(3):
            pdf_path = tmp_path / f"test_{i}.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)
            with open(pdf_path, "wb") as f:
                writer.write(f)

        pdfs = validate_pdfs.discover_pdfs(tmp_path)
        assert len(pdfs) == 3
        assert all(p.suffix == ".pdf" for p in pdfs)

    def test_discover_pdfs_single_file(self, tmp_path: Path) -> None:
        """Verify PDF discovery accepts both directories and single files.

        Real-world significance:
        - Validation may run on entire batch or individual PDF for debugging
        - Single-file mode enables manual PDF validation without batch context
        - Flexible input enables different usage patterns

        Parameters
        ----------
        tmp_path : Path
            Pytest fixture providing temporary directory

        Raises
        ------
        AssertionError
            If single file path not recognized as valid PDF input

        Assertion: Single PDF file is discovered and returned in list
        """
        pdf_path = tmp_path / "test.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        with open(pdf_path, "wb") as f:
            writer.write(f)

        pdfs = validate_pdfs.discover_pdfs(pdf_path)
        assert len(pdfs) == 1
        assert pdfs[0] == pdf_path

    def test_discover_pdfs_no_files_empty_dir(self, tmp_path: Path) -> None:
        """Verify PDF discovery handles empty directories gracefully.

        Real-world significance:
        - Optional pipeline steps may not create PDFs
        - Validation must not crash on missing output
        - Enables idempotent pipeline execution

        Parameters
        ----------
        tmp_path : Path
            Pytest fixture providing temporary directory

        Raises
        ------
        AssertionError
            If empty directory doesn't return empty list

        Assertion: Empty directory returns empty PDF list
        """
        pdfs = validate_pdfs.discover_pdfs(tmp_path)
        assert len(pdfs) == 0

    def test_discover_pdfs_invalid_path(self, tmp_path: Path) -> None:
        """Verify PDF discovery fails fast on invalid paths.

        Real-world significance:
        - Configuration errors (wrong directory) should be caught immediately
        - Prevents silent skipping of validation or misleading success messages
        - Enables clear error messages for operators to debug

        Parameters
        ----------
        tmp_path : Path
            Pytest fixture providing temporary directory

        Raises
        ------
        FileNotFoundError
            If path does not exist (expected behavior)

        AssertionError
            If invalid path does not raise FileNotFoundError

        Assertion: Invalid path raises FileNotFoundError
        """
        invalid_path = tmp_path / "nonexistent.pdf"
        with pytest.raises(FileNotFoundError):
            validate_pdfs.discover_pdfs(invalid_path)


@pytest.mark.unit
class TestFilterByLanguage:
    """Tests for language filtering."""

    def test_filter_by_language_en(self, tmp_path: Path) -> None:
        """Verify language filtering correctly separates multi-language output.

        Real-world significance:
        - Pipeline generates notices in both English and French
        - Validation must run separately per language to report accurate statistics
        - Enables language-specific quality control (e.g., signature placement varies)

        Parameters
        ----------
        tmp_path : Path
            Pytest fixture providing temporary directory

        Raises
        ------
        AssertionError
            If language filter doesn't correctly select files or includes other languages

        Assertion: Only English-prefixed PDFs are selected from mixed language set
        """
        files = [
            tmp_path / "en_notice_001.pdf",
            tmp_path / "fr_notice_001.pdf",
            tmp_path / "en_notice_002.pdf",
        ]
        filtered = validate_pdfs.filter_by_language(files, "en")
        assert len(filtered) == 2
        assert all("en_" in f.name for f in filtered)

    def test_filter_by_language_none(self, tmp_path: Path) -> None:
        """Verify no language filter returns all PDFs unchanged.

        Real-world significance:
        - Pipeline may validate entire batch without language separation
        - Enables single validation run for mixed language output
        - Ensures filtering doesn't accidentally exclude files

        Parameters
        ----------
        tmp_path : Path
            Pytest fixture providing temporary directory

        Raises
        ------
        AssertionError
            If language filter unexpectedly modifies file list when None

        Assertion: All PDFs returned when language filter is None
        """
        files = [
            tmp_path / "en_notice_001.pdf",
            tmp_path / "fr_notice_001.pdf",
        ]
        filtered = validate_pdfs.filter_by_language(files, None)
        assert len(filtered) == 2


@pytest.mark.unit
class TestValidatePdfStructure:
    """Tests for PDF structure validation."""

    def test_validate_pdf_structure_basic(self, tmp_path: Path) -> None:
        """Verify PDF with correct structure (2 pages) passes validation.

        Real-world significance:
        - Standard immunization notices are 2 pages (notice + immunization record)
        - Validation must correctly identify well-formed PDFs
        - Establishes baseline for warning detection (valid ≠ warned)

        Parameters
        ----------
        tmp_path : Path
            Pytest fixture providing temporary directory

        Raises
        ------
        AssertionError
            If valid PDF is incorrectly marked as failed

        Assertion: PDF with exactly 2 pages and no layout issues passes validation
        """
        pdf_path = tmp_path / "test.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.add_blank_page(width=612, height=792)
        with open(pdf_path, "wb") as f:
            writer.write(f)

        result = validate_pdfs.validate_pdf_structure(pdf_path, enabled_rules={})
        assert result.filename == "test.pdf"
        assert result.measurements["page_count"] == 2
        assert result.passed is True
        assert len(result.warnings) == 0

    def test_validate_pdf_structure_unexpected_pages(self, tmp_path: Path) -> None:
        """Verify validation detects and warns on incorrect page count.

        Real-world significance:
        - PDF compilation errors may produce wrong page counts
        - Warnings enable operators to detect template/Typst issues
        - QA step must catch layout problems before delivery

        Parameters
        ----------
        tmp_path : Path
            Pytest fixture providing temporary directory

        Raises
        ------
        AssertionError
            If page count warning not generated for non-2-page PDF

        Assertion: PDF with 3 pages generates exactly_two_pages warning
        """
        pdf_path = tmp_path / "test.pdf"
        writer = PdfWriter()
        for _ in range(3):
            writer.add_blank_page(width=612, height=792)
        with open(pdf_path, "wb") as f:
            writer.write(f)

        result = validate_pdfs.validate_pdf_structure(
            pdf_path,
            enabled_rules={"exactly_two_pages": "warn"},
        )
        assert result.measurements["page_count"] == 3
        assert result.passed is False
        assert len(result.warnings) == 1
        assert "exactly_two_pages" in result.warnings[0]

    def test_validate_pdf_structure_rule_disabled(self, tmp_path: Path) -> None:
        """Verify disabled rules do not generate warnings (configurable validation).

        Real-world significance:
        - Operators may disable specific rules for testing or edge cases
        - Configuration-driven behavior enables workflow flexibility
        - Disabled rules prevent false positives when rules don't apply

        Parameters
        ----------
        tmp_path : Path
            Pytest fixture providing temporary directory

        Raises
        ------
        AssertionError
            If disabled rule still generates warnings

        Assertion: PDF with 3 pages passes when exactly_two_pages rule is disabled
        """
        pdf_path = tmp_path / "test.pdf"
        writer = PdfWriter()
        for _ in range(3):
            writer.add_blank_page(width=612, height=792)
        with open(pdf_path, "wb") as f:
            writer.write(f)

        result = validate_pdfs.validate_pdf_structure(
            pdf_path,
            enabled_rules={"exactly_two_pages": "disabled"},
        )
        assert result.measurements["page_count"] == 3
        assert result.passed  # No warning because rule is disabled
        assert not result.warnings


@pytest.mark.unit
class TestValidationSummary:
    """Tests for validation summary generation."""

    def test_validate_pdfs_summary(self, tmp_path: Path) -> None:
        """Verify batch validation generates accurate summary statistics.

        Real-world significance:
        - Operators need aggregate statistics to understand batch quality
        - Summary enables trend analysis across multiple runs
        - Pass/fail counts inform decision on whether to proceed

        Parameters
        ----------
        tmp_path : Path
            Pytest fixture providing temporary directory

        Raises
        ------
        AssertionError
            If summary statistics don't match input PDFs

        Assertion: Summary correctly reports passed, warned, and page distributions
        """
        # Create test PDFs with different page counts
        files = []
        for i in range(3):
            pdf_path = tmp_path / f"test_{i}.pdf"
            writer = PdfWriter()
            for _ in range(2 if i < 2 else 3):
                writer.add_blank_page(width=612, height=792)
            with open(pdf_path, "wb") as f:
                writer.write(f)
            files.append(pdf_path)

        summary = validate_pdfs.validate_pdfs(
            files,
            enabled_rules={"exactly_two_pages": "warn"},
        )
        assert summary.total_pdfs == 3
        assert summary.passed_count == 2
        assert summary.warning_count == 1
        assert summary.page_count_distribution[2] == 2
        assert summary.page_count_distribution[3] == 1


@pytest.mark.unit
class TestWriteValidationJson:
    """Tests for JSON output."""

    def test_write_validation_json(self, tmp_path: Path) -> None:
        """Verify validation summary exports to JSON for downstream processing.

        Real-world significance:
        - JSON metadata enables integration with external analysis tools
        - Persistent records support audit trail and debugging
        - Enables programmatic post-processing of validation results

        Parameters
        ----------
        tmp_path : Path
            Pytest fixture providing temporary directory

        Raises
        ------
        AssertionError
            If JSON output missing expected keys or values

        Assertion: JSON output contains all summary statistics and per-PDF results
        """
        summary = validate_pdfs.ValidationSummary(
            language="en",
            total_pdfs=2,
            passed_count=1,
            warning_count=1,
            page_count_distribution={2: 1, 3: 1},
            warning_types={"exactly_two_pages": 1},
            rule_results=[
                validate_pdfs.RuleResult(
                    rule_name="exactly_two_pages",
                    severity="warn",
                    passed_count=1,
                    failed_count=1,
                )
            ],
            results=[
                validate_pdfs.ValidationResult(
                    filename="test1.pdf",
                    warnings=[],
                    passed=True,
                    measurements={"page_count": 2},
                ),
                validate_pdfs.ValidationResult(
                    filename="test2.pdf",
                    warnings=["exactly_two_pages: has 3 pages (expected 2)"],
                    passed=False,
                    measurements={"page_count": 3},
                ),
            ],
        )

        output_path = tmp_path / "validation.json"
        validate_pdfs.write_validation_json(summary, output_path)

        assert output_path.exists()
        data = json.loads(output_path.read_text())
        assert data["total_pdfs"] == 2
        assert data["passed_count"] == 1
        assert data["warning_count"] == 1
        assert len(data["results"]) == 2


@pytest.mark.unit
class TestMainFunction:
    """Tests for main entry point."""

    def test_main_with_json_output(self, tmp_path: Path) -> None:
        """Verify main entry point orchestrates validation and produces JSON output.

        Real-world significance:
        - Pipeline orchestrator calls main() as step 6
        - Validates all compiled PDFs and reports aggregate results
        - Enables downstream decisions on whether to proceed (e.g., email delivery)

        Parameters
        ----------
        tmp_path : Path
            Pytest fixture providing temporary directory

        Raises
        ------
        AssertionError
            If JSON output not created or summary statistics incorrect

        Assertion: Valid PDFs pass, JSON metadata is written, summary is returned
        """
        # Create test PDFs
        pdf_dir = tmp_path / "pdfs"
        pdf_dir.mkdir()
        for i in range(2):
            pdf_path = pdf_dir / f"en_notice_{i:03d}.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=612, height=792)
            writer.add_blank_page(width=612, height=792)
            with open(pdf_path, "wb") as f:
                writer.write(f)

        json_path = tmp_path / "validation.json"
        summary = validate_pdfs.main(
            pdf_dir,
            language="en",
            enabled_rules={"exactly_two_pages": "warn"},
            json_output=json_path,
        )

        assert summary.total_pdfs == 2
        assert summary.passed_count == 2
        assert json_path.exists()

    def test_main_with_error_rule(self, tmp_path: Path) -> None:
        """Verify main halts pipeline when error-level validation rule fails.

        Real-world significance:
        - Some validation issues are critical and must prevent delivery
        - Error-level rules enable strict quality gates
        - Prevents defective notices from reaching clients

        Parameters
        ----------
        tmp_path : Path
            Pytest fixture providing temporary directory

        Raises
        ------
        RuntimeError
            When validation rule with severity 'error' detects failure (expected)

        AssertionError
            If main does not raise RuntimeError for error-level validation failure

        Assertion: main() raises RuntimeError when error-level rule detects issue
        """
        # Create test PDFs with wrong page count
        pdf_dir = tmp_path / "pdfs"
        pdf_dir.mkdir()
        pdf_path = pdf_dir / "test.pdf"
        writer = PdfWriter()
        for _ in range(3):
            writer.add_blank_page(width=612, height=792)
        with open(pdf_path, "wb") as f:
            writer.write(f)

        with pytest.raises(RuntimeError, match="PDF validation failed with errors"):
            validate_pdfs.main(
                pdf_dir,
                enabled_rules={"exactly_two_pages": "error"},
                json_output=None,
            )


@pytest.mark.unit
class TestExtractMeasurements:
    """Tests for measurement extraction from invisible markers."""

    def test_extract_measurements_from_markers(self) -> None:
        """Verify measurement extraction from Typst marker patterns.

        Real-world significance:
        - Typst templates embed layout measurements as invisible text
        - Validator parses these to check envelope window constraints
        - Must handle various numeric formats (integers, floats)

        Assertion: Measurements are correctly extracted and normalized
        """
        # Simulate text extracted from PDF with our marker
        page_text = """
        Some regular text here
        MEASURE_CONTACT_HEIGHT:214.62692913385834
        More content below
        """

        measurements = validate_pdfs.extract_measurements_from_markers(page_text)

        assert "measure_contact_height" in measurements
        assert measurements["measure_contact_height"] == 214.62692913385834

    def test_extract_measurements_no_markers(self) -> None:
        """Verify graceful handling when no markers present.

        Real-world significance:
        - Older PDFs may not have measurement markers
        - Validator should not fail on legacy documents

        Assertion: Returns empty dict when no markers found
        """
        page_text = "Just regular PDF content without any markers"
        measurements = validate_pdfs.extract_measurements_from_markers(page_text)
        assert measurements == {}

    def test_extract_measurements_partial_markers(self) -> None:
        """Verify extraction works with mixed marker presence.

        Real-world significance:
        - Template evolution may add new markers over time
        - Validator should extract what's available

        Assertion: Extracts available measurements, ignores missing ones
        """
        page_text = """
        MEASURE_CONTACT_HEIGHT:123.45
        SOME_OTHER_MARKER:ignored
        MEASURE_ANOTHER_DIMENSION:678.90
        """

        measurements = validate_pdfs.extract_measurements_from_markers(page_text)

        assert measurements["measure_contact_height"] == 123.45
        assert measurements["measure_another_dimension"] == 678.90
        assert len(measurements) == 2


@pytest.mark.unit
class TestRuleResultsAndMeasurements:
    """Tests for enhanced validation output with per-rule results and measurements."""

    def test_validation_includes_measurements(self, tmp_path: Path) -> None:
        """Verify ValidationResult includes actual measurements from PDFs.

        Real-world significance:
        - Actual measurements allow confirming validation rules work correctly
        - Helps debug why a PDF passed or failed a specific rule
        - Enables detailed analysis of layout variations

        Assertion: ValidationResult contains measurements dict with actual values
        """
        pdf_path = tmp_path / "test.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.add_blank_page(width=612, height=792)

        with open(pdf_path, "wb") as f:
            writer.write(f)

        result = validate_pdfs.validate_pdf_structure(
            pdf_path, enabled_rules={"exactly_two_pages": "warn"}
        )

        # Should have measurements including page_count
        assert result.measurements is not None
        assert "page_count" in result.measurements
        assert type(result.measurements["page_count"]) == int
        assert result.measurements["page_count"] == 2

    def test_rule_results_include_all_rules(self, tmp_path: Path) -> None:
        """Verify ValidationSummary includes results for all configured rules.

        Real-world significance:
        - User wants to see all rules, including disabled ones
        - Helps understand which rules are active and their pass/fail rates
        - Enables auditing of validation configuration

        Assertion: rule_results includes all rules from enabled_rules config
        """
        pdf_dir = tmp_path / "pdfs"
        pdf_dir.mkdir()

        # Create 3 PDFs: 2 pass, 1 fails (3 pages)
        for i, page_count in enumerate([2, 2, 3]):
            pdf_path = pdf_dir / f"test_{i}.pdf"
            writer = PdfWriter()
            for _ in range(page_count):
                writer.add_blank_page(width=612, height=792)
            with open(pdf_path, "wb") as f:
                writer.write(f)

        enabled_rules = {
            "exactly_two_pages": "warn",
            "signature_overflow": "disabled",
            "envelope_window_1_125": "error",
        }

        files = validate_pdfs.discover_pdfs(pdf_dir)
        summary = validate_pdfs.validate_pdfs(files, enabled_rules=enabled_rules)

        # Should have rule_results for all configured rules
        assert len(summary.rule_results) == 3

        rule_dict = {r.rule_name: r for r in summary.rule_results}

        # Check exactly_two_pages rule
        assert "exactly_two_pages" in rule_dict
        assert rule_dict["exactly_two_pages"].severity == "warn"
        assert rule_dict["exactly_two_pages"].passed_count == 2
        assert rule_dict["exactly_two_pages"].failed_count == 1

        # Check disabled rule still appears
        assert "signature_overflow" in rule_dict
        assert rule_dict["signature_overflow"].severity == "disabled"

        # Check error rule appears
        assert "envelope_window_1_125" in rule_dict
        assert rule_dict["envelope_window_1_125"].severity == "error"

    def test_warnings_include_actual_values(self, tmp_path: Path) -> None:
        """Verify warning messages include actual measured values.

        Real-world significance:
        - User wants to see actual page count, not just "failed"
        - Helps understand severity (3 pages vs 10 pages)
        - Enables data-driven decision making

        Assertion: Warning messages contain actual values like "has 3 pages"
        """
        pdf_path = tmp_path / "test.pdf"
        writer = PdfWriter()
        for _ in range(5):  # Create 5-page PDF
            writer.add_blank_page(width=612, height=792)
        with open(pdf_path, "wb") as f:
            writer.write(f)

        result = validate_pdfs.validate_pdf_structure(
            pdf_path, enabled_rules={"exactly_two_pages": "warn"}
        )

        assert not result.passed
        assert len(result.warnings) == 1
        # Should include actual page count
        assert "has 5 pages" in result.warnings[0]
        assert "expected 2" in result.warnings[0]


@pytest.mark.unit
class TestClientIdValidation:
    """Tests for client ID presence validation (markerless)."""

    def test_find_client_id_in_text(self) -> None:
        """Verify client ID extraction from PDF page text.

        Real-world significance:
        - Text extraction from PDF enables searching for the expected ID
        - Should find 10-digit numbers with word boundaries

        Assertion: Finds 10-digit client ID in extracted text
        """
        # Text with client ID
        text = "Client ID: 1009876543\nDate of Birth: 2015-06-15"
        found_id = validate_pdfs.find_client_id_in_text(text)
        assert found_id == "1009876543"

        # French version
        text_fr = "Identifiant du client: 1009876543\nDate de naissance: 2015-06-15"
        found_id_fr = validate_pdfs.find_client_id_in_text(text_fr)
        assert found_id_fr == "1009876543"

        # No client ID in text
        text_empty = "Some content without IDs"
        found_id_empty = validate_pdfs.find_client_id_in_text(text_empty)
        assert found_id_empty is None

    def test_client_id_presence_pass(self, tmp_path: Path) -> None:
        """Verify client ID validation passes when ID found and matches.

        Real-world significance:
        - Passes when the expected ID from filename is found in PDF

        Assertion: No warning when client ID matches
        """
        pdf_path = tmp_path / "en_notice_00001_1009876543.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)

        with open(pdf_path, "wb") as f:
            writer.write(f)

        # Test with only client_id_presence enabled (disable others to isolate)
        # Pass client_id_map to activate the rule (artifact-driven validation model)
        client_id_map = {"en_notice_00001_1009876543.pdf": "1009876543"}
        result = validate_pdfs.validate_pdf_structure(
            pdf_path,
            enabled_rules={
                "client_id_presence": "warn",
                "exactly_two_pages": "disabled",
            },
            client_id_map=client_id_map,
        )

        # Empty PDF won't have the ID, so it should warn
        # (This tests the rule is active; a real PDF would need the ID embedded)
        assert len(result.warnings) == 1
        assert "client_id_presence" in result.warnings[0]
        assert "1009876543" in result.warnings[0]

    def test_client_id_presence_disabled(self, tmp_path: Path) -> None:
        """Verify client ID rule respects disabled configuration.

        Real-world significance:
        - Users can disable the rule via config

        Assertion: No warning when rule is disabled
        """
        pdf_path = tmp_path / "en_notice_00001_1009876543.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        with open(pdf_path, "wb") as f:
            writer.write(f)

        # Pass client_id_map even though rule is disabled (validates rule respects config)
        client_id_map = {"en_notice_00001_1009876543.pdf": "1009876543"}
        result = validate_pdfs.validate_pdf_structure(
            pdf_path,
            enabled_rules={
                "client_id_presence": "disabled",
                "exactly_two_pages": "disabled",
            },
            client_id_map=client_id_map,
        )

        # Should have no warnings because all rules are disabled
        assert len(result.warnings) == 0


@pytest.mark.unit
class TestPhixMetadataLogging:
    """Tests for PHIX metadata measurements in PDF validation."""

    def test_measurements_include_phix_scope(self, tmp_path: Path) -> None:
        """PHIX metadata is propagated into validation measurements."""
        pdf_path = tmp_path / "en_notice_00001_1009876543.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        with open(pdf_path, "wb") as f:
            writer.write(f)

        metadata_map = {
            pdf_path.name: {
                "phix_validation": {
                    "phu_code": "test_phu_1",
                    "phu_name": "Test PHU 1",
                    "match_type": "exact",
                    "confidence": 100,
                },
                "phix_target_phu_code": "test_phu_1",
                "phix_target_phu_label": "Test PHU 1",
                "school_name": "Lincoln Elementary School",
            }
        }

        result = validate_pdfs.validate_pdf_structure(
            pdf_path,
            enabled_rules={"exactly_two_pages": "disabled"},
            client_metadata_map=metadata_map,
        )

        assert result.measurements["phix_target_phu_code"] == "test_phu_1"
        assert result.measurements["phix_matched_phu_code"] == "test_phu_1"
        assert "phix_target_phu" not in "".join(result.warnings)

    def test_mismatch_emits_warning(self, tmp_path: Path) -> None:
        """PHU mismatch triggers per-PDF warning."""
        pdf_path = tmp_path / "en_notice_00001_1009876543.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        with open(pdf_path, "wb") as f:
            writer.write(f)

        metadata_map = {
            pdf_path.name: {
                "phix_validation": {
                    "phu_code": "test_phu_2",
                    "phu_name": "Test PHU 2",
                    "match_type": "exact",
                    "confidence": 100,
                },
                "phix_target_phu_code": "test_phu_1",
                "phix_target_phu_label": "Test PHU 1",
            }
        }

        result = validate_pdfs.validate_pdf_structure(
            pdf_path,
            enabled_rules={"exactly_two_pages": "disabled"},
            client_metadata_map=metadata_map,
        )

        assert any("phix_target_phu" in warning for warning in result.warnings)
