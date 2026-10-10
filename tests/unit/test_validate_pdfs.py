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

from immuknow import validate_pdfs


@pytest.mark.unit
class TestValidatePdfStructure:
    def test_validate_pdf_structure_basic(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "test.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.add_blank_page(width=612, height=792)
        with open(pdf_path, "wb") as f:
            writer.write(f)

        result = validate_pdfs.validate_pdf_structure(
            pdf_path,
            enabled_rules={
                "signature_overflow": "disabled",
            },
        )
        assert result.filename == "test.pdf"
        assert result.measurements["page_count"] == 2
        assert result.passed is True
        assert len(result.warnings) == 0

    def test_validate_pdf_structure_unexpected_pages(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "test.pdf"
        writer = PdfWriter()
        for _ in range(3):
            writer.add_blank_page(width=612, height=792)
        with open(pdf_path, "wb") as f:
            writer.write(f)

        result = validate_pdfs.validate_pdf_structure(
            pdf_path,
            enabled_rules={
                "signature_overflow": "disabled",
                "exactly_two_pages": "warn",
            },
        )
        assert result.measurements["page_count"] == 3
        assert result.passed is False
        assert len(result.warnings) == 1
        assert "exactly_two_pages" in result.warnings[0]

    def test_validate_pdf_structure_rule_disabled(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "test.pdf"
        writer = PdfWriter()
        for _ in range(3):
            writer.add_blank_page(width=612, height=792)
        with open(pdf_path, "wb") as f:
            writer.write(f)

        result = validate_pdfs.validate_pdf_structure(
            pdf_path,
            enabled_rules={
                "signature_overflow": "disabled",
                "exactly_two_pages": "disabled",
            },
        )
        assert result.measurements["page_count"] == 3
        assert result.passed  # No warning because rule is disabled
        assert not result.warnings


@pytest.mark.unit
class TestValidationSummary:
    def test_validate_pdfs_summary(self, tmp_path: Path) -> None:
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
            enabled_rules={
                "signature_overflow": "disabled",
                "exactly_two_pages": "warn",
            },
        )
        assert summary.total_pdfs == 3
        assert summary.passed_count == 2
        assert summary.warning_count == 1
        assert summary.page_count_distribution[2] == 2
        assert summary.page_count_distribution[3] == 1


@pytest.mark.unit
class TestWriteValidationJson:
    def test_write_validation_json(self, tmp_path: Path) -> None:
        summary = validate_pdfs.ValidationSummary(
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
    def test_main_with_json_output(self, tmp_path: Path) -> None:
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
        summary = validate_pdfs.validate_notices(
            expected_pdfs=sorted(pdf_dir.glob("*.pdf")),
            enabled_rules={
                "signature_overflow": "disabled",
                "exactly_two_pages": "warn",
            },
            json_output=json_path,
        )

        assert summary.total_pdfs == 2
        assert summary.passed_count == 2
        assert json_path.exists()

    def test_main_with_error_rule(self, tmp_path: Path) -> None:
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
            validate_pdfs.validate_notices(
                expected_pdfs=[pdf_path],
                enabled_rules={
                    "signature_overflow": "disabled",
                    "exactly_two_pages": "error",
                },
                json_output=None,
            )


@pytest.mark.unit
class TestExtractMeasurements:
    def test_extract_measurements_from_markers(self) -> None:
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
        page_text = "Just regular PDF content without any markers"
        measurements = validate_pdfs.extract_measurements_from_markers(page_text)
        assert measurements == {}

    def test_extract_measurements_partial_markers(self) -> None:
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
    def test_validation_includes_measurements(self, tmp_path: Path) -> None:
        pdf_path = tmp_path / "test.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.add_blank_page(width=612, height=792)

        with open(pdf_path, "wb") as f:
            writer.write(f)

        result = validate_pdfs.validate_pdf_structure(
            pdf_path,
            enabled_rules={
                "signature_overflow": "disabled",
                "exactly_two_pages": "warn",
            },
        )

        # Should have measurements including page_count
        assert result.measurements is not None
        assert "page_count" in result.measurements
        assert isinstance(result.measurements["page_count"], int)
        assert result.measurements["page_count"] == 2

    def test_rule_results_include_all_rules(self, tmp_path: Path) -> None:
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

        files = sorted(pdf_dir.glob("*.pdf"))
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
        pdf_path = tmp_path / "test.pdf"
        writer = PdfWriter()
        for _ in range(5):  # Create 5-page PDF
            writer.add_blank_page(width=612, height=792)
        with open(pdf_path, "wb") as f:
            writer.write(f)

        result = validate_pdfs.validate_pdf_structure(
            pdf_path,
            enabled_rules={
                "signature_overflow": "disabled",
                "exactly_two_pages": "warn",
            },
        )

        assert not result.passed
        assert len(result.warnings) == 1
        # Should include actual page count
        assert "has 5 pages" in result.warnings[0]
        assert "expected 2" in result.warnings[0]


@pytest.mark.unit
class TestClientIdValidation:
    def test_find_client_id_in_text(self) -> None:
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
                "signature_overflow": "disabled",
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
                "signature_overflow": "disabled",
                "client_id_presence": "disabled",
                "exactly_two_pages": "disabled",
            },
            client_id_map=client_id_map,
        )

        # Should have no warnings because all rules are disabled
        assert len(result.warnings) == 0
