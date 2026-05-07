"""Unit tests for PHIX validation module.

Tests cover:
- Loading and parsing PHIX reference Excel files
- Exact matching against reference list (no fuzzy fallback)
- Different unmatched_behavior modes (warn, error, skip)
- Edge cases (empty data, missing columns)
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from pipeline.validate_phix import (
    PHIXFacility,
    PHIXMatchResult,
    clear_cache,
    load_phix_reference,
    match_facility,
    normalize_facility_name,
    parse_facility_entry,
    validate_facilities,
)


@pytest.fixture(autouse=True)
def reset_cache():
    """Clear PHIX reference cache before and after each test."""
    clear_cache()
    yield
    clear_cache()


@pytest.fixture
def sample_phix_excel(tmp_path: Path) -> Path:
    """Create a sample PHIX reference Excel file for testing."""
    data = {
        "Test PHU 1": [
            "Lincoln Elementary School - SCH001",
            "Maple High School - SCH002",
            "Sunshine Childcare Centre - DAY001",
            None,  # Empty row
        ],
        "Test PHU 2": [
            "Oak Valley Public School - SCH003",
            "Bright Futures Daycare - DAY002",
            None,
            None,
        ],
    }
    df = pd.DataFrame(data)
    excel_path = tmp_path / "test_phix_reference.xlsx"
    df.to_excel(excel_path, sheet_name="Schools & Day Cares", index=False)
    return excel_path


@pytest.fixture
def sample_phu_mapping(tmp_path: Path) -> Path:
    """Create a sample PHU alias mapping file."""
    mapping_path = tmp_path / "phu_aliases.yaml"
    mapping_path.write_text(
        """
phu_aliases:
  test_phu_1:
    display_name: Test PHU 1
    aliases:
      - Test PHU 1
  test_phu_2:
    display_name: Test PHU 2
    aliases:
      - Test PHU 2
        """.strip(),
        encoding="utf-8",
    )
    return mapping_path


class TestParseFacilityEntry:
    """Tests for parse_facility_entry function."""

    def test_parse_standard_entry(self):
        """Parse standard 'NAME - ID' format."""
        facility = parse_facility_entry(
            "ANNA MCCREA PUBLIC SCHOOL - 019186", "Test PHU"
        )
        assert facility is not None
        assert facility.name == "ANNA MCCREA PUBLIC SCHOOL"
        assert facility.phix_id == "019186"
        assert facility.phu == "Test PHU"

    def test_parse_entry_with_multiple_dashes(self):
        """Parse entry where name contains dashes."""
        facility = parse_facility_entry(
            "ST. MARY'S CO-OP - PRE-SCHOOL - DAY123", "PHU"
        )
        assert facility is not None
        # Should split on last " - "
        assert facility.name == "ST. MARY'S CO-OP - PRE-SCHOOL"
        assert facility.phix_id == "DAY123"

    def test_parse_entry_no_id(self):
        """Parse entry without ID separator."""
        facility = parse_facility_entry("Some School Name", "PHU")
        assert facility is not None
        assert facility.name == "Some School Name"
        assert facility.phix_id == ""

    def test_parse_empty_entry(self):
        """Empty entries return None."""
        assert parse_facility_entry("", "PHU") is None
        assert parse_facility_entry(None, "PHU") is None  # type: ignore[arg-type]
        assert parse_facility_entry("   ", "PHU") is None

    def test_parse_nan_entry(self):
        """NaN values return None."""
        assert parse_facility_entry(float("nan"), "PHU") is None  # type: ignore[arg-type]


class TestNormalizeFacilityName:
    """Tests for normalize_facility_name function."""

    def test_uppercase_conversion(self):
        """Names are converted to uppercase."""
        assert normalize_facility_name("Lincoln School") == "LINCOLN SCHOOL"

    def test_whitespace_normalization(self):
        """Extra whitespace is collapsed."""
        assert normalize_facility_name("  Lincoln   School  ") == "LINCOLN SCHOOL"

    def test_empty_string(self):
        """Empty string returns empty."""
        assert normalize_facility_name("") == ""
        assert normalize_facility_name("   ") == ""


class TestLoadPhixReference:
    """Tests for load_phix_reference function."""

    def test_load_valid_file(self, sample_phix_excel: Path):
        """Load and parse valid PHIX reference file."""
        ref = load_phix_reference(sample_phix_excel)

        assert "facilities" in ref
        assert "by_name" in ref
        assert "phus" in ref
        assert "by_name_phu" in ref

        # Should have 5 facilities (excluding None rows)
        assert len(ref["facilities"]) == 5
        assert len(ref["phus"]) == 2

    def test_caching(self, sample_phix_excel: Path):
        """Second load returns cached data."""
        ref1 = load_phix_reference(sample_phix_excel)
        ref2 = load_phix_reference(sample_phix_excel)

        # Should be same object (cached)
        assert ref1 is ref2

    def test_file_not_found(self, tmp_path: Path):
        """Missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="PHIX reference file not found"):
            load_phix_reference(tmp_path / "nonexistent.xlsx")


class TestMatchFacility:
    """Tests for match_facility function."""
    def test_exact_match(self, sample_phix_excel: Path):
        """Exact match returns 100% confidence."""
        ref = load_phix_reference(sample_phix_excel)

        result = match_facility("Lincoln Elementary School - SCH001", ref)
        assert result.matched is True
        assert result.phix_id == "SCH001"
        assert result.confidence == 100
        assert result.match_type == "exact"
        assert result.phu_name == "Test PHU 1"

    def test_no_phix_match(self, sample_phix_excel: Path):
        """Exact match returns 100% confidence."""
        ref = load_phix_reference(sample_phix_excel)

        result = match_facility("Lincoln Elementary School", ref)
        assert result.matched is True
        assert result.phix_id == "SCH001"
        assert result.confidence == 100
        assert result.match_type == "no_phix_id"
        assert result.phu_name == "Test PHU 1"

    def test_wrong_phix_match(self, sample_phix_excel: Path):
        """Exact match returns 100% confidence."""
        ref = load_phix_reference(sample_phix_excel)

        result = match_facility("Lincoln Elementary School - SCH002", ref)
        assert result.matched is False
        assert result.phix_id == "SCH001"
        assert result.confidence == 100
        assert result.match_type == "wrong_phix_id"
        assert result.phu_name == "Test PHU 1"

    def test_exact_match_case_insensitive(self, sample_phix_excel: Path):
        """Exact match is case-insensitive."""
        ref = load_phix_reference(sample_phix_excel)

        result = match_facility("LINCOLN ELEMENTARY SCHOOL", ref)
        assert result.matched is True
        assert result.confidence == 100

    def test_similar_name_not_matched(self, sample_phix_excel: Path):
        """Slight typos do not match (exact-only policy)."""
        ref = load_phix_reference(sample_phix_excel)

        # Slight typo that would match fuzzy
        result = match_facility("Lincoln Elementry School", ref)
        assert result.matched is False

    def test_empty_input(self, sample_phix_excel: Path):
        """Empty input returns no match."""
        ref = load_phix_reference(sample_phix_excel)

        result = match_facility("", ref)
        assert result.matched is False

        result = match_facility("   ", ref)
        assert result.matched is False


class TestValidateFacilities:
    """Tests for validate_facilities function."""

    def test_validate_all_matched(self, sample_phix_excel: Path, tmp_path: Path):
        """All facilities matched returns no warnings."""
        df = pd.DataFrame({
            "SCHOOL_NAME": ["Lincoln Elementary School - SCH001", "Maple High School - SCH002"],
            "OTHER_COL": ["A", "B"],
        })

        result_df, warnings = validate_facilities(df, sample_phix_excel, tmp_path)

        assert len(result_df) == 2
        assert "PHIX_ID" in result_df.columns
        assert "PHIX_MATCH_CONFIDENCE" in result_df.columns
        assert result_df.iloc[0]["PHIX_ID"] == "SCH001"
        assert "PHIX_MATCHED_PHU" in result_df.columns
        assert result_df.iloc[0]["PHIX_MATCHED_PHU"] == "Test PHU 1"
        assert "PHIX_TARGET_PHU_CODE" in result_df.columns
        assert pd.isna(result_df["PHIX_TARGET_PHU_CODE"]).all()
        assert len(warnings) == 0

    def test_validate_scoped_to_target_phu(
        self,
        sample_phix_excel: Path,
        sample_phu_mapping: Path,
        tmp_path: Path,
    ):
        """Facilities outside target PHU remain unmatched."""
        df = pd.DataFrame(
            {
                "SCHOOL_NAME": [
                    "Lincoln Elementary School - SCH001",  # PHU 1
                    "Oak Valley Public School - SCH003",  # PHU 2
                ],
            }
        )

        result_df, warnings = validate_facilities(
            df,
            sample_phix_excel,
            tmp_path,
            target_phu_codes=["test_phu_2"],
            phu_mapping_path=sample_phu_mapping,
        )

        assert result_df.iloc[0]["PHIX_MATCH_TYPE"] == "none"
        assert result_df.iloc[0]["PHIX_ID"] is None
        assert result_df.iloc[1]["PHIX_ID"] == "SCH003"
        assert result_df.iloc[1]["PHIX_MATCHED_PHU_CODE"] == "test_phu_2"
        assert result_df.iloc[1]["PHIX_TARGET_PHU_CODE"] == "test_phu_2"
        assert len(warnings) == 1  # unmatched facility warning
        unmatched_csv = tmp_path / "unmatched_facilities.csv"
        assert unmatched_csv.exists()

    def test_validate_missing_mapping_for_target(
        self, sample_phix_excel: Path, tmp_path: Path
    ):
        """Target PHU requires mapping file."""
        df = pd.DataFrame({"SCHOOL_NAME": ["Lincoln Elementary School"]})

        with pytest.raises(ValueError, match="phu_mapping_file"):
            validate_facilities(
                df,
                sample_phix_excel,
                tmp_path,
                target_phu_codes=["test_phu_1"],
            )

    def test_validate_unknown_template_code(
        self, sample_phix_excel: Path, sample_phu_mapping: Path, tmp_path: Path
    ):
        """Unknown template code raises descriptive error."""
        df = pd.DataFrame({"SCHOOL_NAME": ["Lincoln Elementary School"]})

        with pytest.raises(ValueError, match="not defined"):
            validate_facilities(
                df,
                sample_phix_excel,
                tmp_path,
                target_phu_codes=["unknown_code"],
                phu_mapping_path=sample_phu_mapping,
            )

    def test_validate_missing_phu_alias(
        self, sample_phix_excel: Path, tmp_path: Path
    ):
        """Missing PHU alias in mapping is surfaced."""
        df = pd.DataFrame({"SCHOOL_NAME": ["Lincoln Elementary School"]})
        mapping_path = tmp_path / "phu_aliases_partial.yaml"
        mapping_path.write_text(
            """
phu_aliases:
  test_phu_1:
    display_name: Example Display
    aliases:
      - Unknown Alias
            """.strip(),
            encoding="utf-8",
        )

        with pytest.raises(ValueError, match="No PHIX columns mapped"):
            validate_facilities(
                df,
                sample_phix_excel,
                tmp_path,
                target_phu_codes=["test_phu_1"],
                phu_mapping_path=mapping_path,
            )

    def test_validate_with_unmatched_warn(
        self, sample_phix_excel: Path, tmp_path: Path
    ):
        """Unmatched facilities with warn behavior logs warning."""
        df = pd.DataFrame({
            "SCHOOL_NAME": ["Lincoln Elementary School - SCH001", "Unknown School XYZ"],
        })

        result_df, warnings = validate_facilities(
            df,
            sample_phix_excel,
            tmp_path,
            unmatched_behavior="warn",
        )

        assert len(result_df) == 2  # All records kept
        assert len(warnings) == 1
        assert "facilities had no PHIX name match" in warnings[0]

        # Check unmatched CSV was written
        unmatched_csv = tmp_path / "unmatched_facilities.csv"
        assert unmatched_csv.exists()

    def test_validate_with_unmatched_error(
        self, sample_phix_excel: Path, tmp_path: Path
    ):
        """Unmatched facilities with error behavior raises."""
        df = pd.DataFrame({
            "SCHOOL_NAME": ["Lincoln Elementary School - SCH001", "Unknown School XYZ"],
        })

        with pytest.raises(ValueError, match="failed strict PHIX validation"):
            validate_facilities(
                df,
                sample_phix_excel,
                tmp_path,
                unmatched_behavior="error",
            )

    def test_validate_with_unmatched_skip(
        self, sample_phix_excel: Path, tmp_path: Path
    ):
        """Unmatched facilities with skip behavior filters them out."""
        df = pd.DataFrame({
            "SCHOOL_NAME": ["Lincoln Elementary School - SCH001", "Unknown School XYZ"],
        })

        result_df, warnings = validate_facilities(
            df,
            sample_phix_excel,
            tmp_path,
            unmatched_behavior="skip",
        )

        assert len(result_df) == 1  # Unknown filtered out
        assert result_df.iloc[0]["SCHOOL_NAME"] == "Lincoln Elementary School - SCH001"
        assert len(warnings) == 2  # unmatched warning + filtered warning

    def test_validate_missing_column(
        self, sample_phix_excel: Path, tmp_path: Path
    ):
        """Missing school column skips validation gracefully."""
        df = pd.DataFrame({
            "OTHER_COL": ["A", "B"],
        })

        result_df, warnings = validate_facilities(
            df, sample_phix_excel, tmp_path,
            school_column="SCHOOL_NAME",
        )

        assert len(result_df) == 2
        assert "PHIX_ID" not in result_df.columns
        assert len(warnings) == 0

    def test_validate_empty_dataframe(
        self, sample_phix_excel: Path, tmp_path: Path
    ):
        """Empty DataFrame returns empty with no errors."""
        df = pd.DataFrame({"SCHOOL_NAME": []})

        result_df, warnings = validate_facilities(
            df, sample_phix_excel, tmp_path
        )

        assert len(result_df) == 0
        assert len(warnings) == 0

    def test_validate_multiple_columns(self, sample_phix_excel, tmp_path):
        """Multiple facility columns can be validated in one call."""
        df = pd.DataFrame({
            "SCHOOL_NAME": ["Lincoln Elementary School - SCH001", "Unknown School"],
            "DAYCARE_NAME": ["Sunshine Childcare Centre - DAY001", "Unknown Daycare"],
        })

        result_df, warnings = validate_facilities(
            df,
            sample_phix_excel,
            tmp_path,
            school_column=["SCHOOL_NAME", "DAYCARE_NAME"],
            unmatched_behavior="warn",
        )

        # Both columns should be validated
        assert "PHIX_ID" in result_df.columns
        # First row schools/daycare should match
        assert result_df.loc[0, "PHIX_ID"] is not None
        # Warnings should be generated for unmatched facilities
        assert len(warnings) >= 2  # One for each unmatched column
        assert all("facilities had no PHIX name match" in w for w in warnings)


class TestPHIXFacilityDataclass:
    """Tests for PHIXFacility dataclass."""

    def test_hash_equality(self):
        """Two facilities with same data have same hash."""
        f1 = PHIXFacility(phix_id="123", name="Test", phu="PHU1")
        f2 = PHIXFacility(phix_id="123", name="Test", phu="PHU1")

        assert hash(f1) == hash(f2)

    def test_hash_difference(self):
        """Different facilities have different hashes."""
        f1 = PHIXFacility(phix_id="123", name="Test", phu="PHU1")
        f2 = PHIXFacility(phix_id="456", name="Test", phu="PHU1")

        assert hash(f1) != hash(f2)


class TestPHIXMatchResultDataclass:
    """Tests for PHIXMatchResult dataclass."""

    def test_default_values(self):
        """Verify default values."""
        result = PHIXMatchResult(input_name="Test", matched=False)

        assert result.phix_id is None
        assert result.phix_name is None
        assert result.phu_name is None
        assert result.phu_code is None
        assert result.confidence == 0
        assert result.match_type == "none"
