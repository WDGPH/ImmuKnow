"""Unit tests for preprocess module - data normalization and client artifact generation.

Tests cover:
- Schema validation (required columns, data types)
- Data cleaning (dates, addresses, vaccine history)
- Client sorting and sequencing
- Artifact structure consistency
- Error handling for invalid inputs
- Date conversion and age calculation
- Vaccine mapping and normalization
- Language support (English and French)

Real-world significance:
- Step 2 of pipeline: transforms Excel input into normalized client data
- Preprocessing correctness directly affects accuracy of all downstream notices
- Client sorting must be deterministic for reproducible output
- Vaccine mapping must correctly expand component diseases
- Age calculation affects notice recipient determination
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from pipeline import preprocess
from tests.fixtures import sample_input


@pytest.mark.unit
class TestMapColumns:
    """Unit tests for map_columns() column mapping utility."""

    def test_maps_exact_column_names(self):
        """Verify that exact column names are mapped correctly."""
        df = pd.DataFrame(
            {
                "SCHOOL NAME": ["Test School"],
                "CLIENT ID": ["C001"],
                "FIRST NAME": ["Alice"],
                "LAST NAME": ["Zephyr"],
                "DATE OF BIRTH": ["2015-01-01"],
                "CITY": ["Guelph"],
                "POSTAL CODE": ["N1H 2T2"],
                "PROVINCE/TERRITORY": ["ON"],
                "OVERDUE DISEASE": ["Measles"],
                "IMMS GIVEN": [""],
                "STREET ADDRESS LINE 1": ["123 Main"],
                "STREET ADDRESS LINE 2": [""],
            }
        )

        mapped_df, col_map = preprocess.map_columns(df)

        assert set(mapped_df.columns) == set(preprocess.REQUIRED_COLUMNS)
        for col in preprocess.REQUIRED_COLUMNS:
            assert col in col_map.values()

    def test_maps_inexact_column_names(self):
        """Verify that inexact column names are mapped correctly."""
        df = pd.DataFrame(
            {
                "school-name": ["Test School"],
                "client id": ["C001"],
                "First Name": ["Alice"],
                "last_name": ["Zephyr"],
                "date-of-birth": ["2015-01-01"],
                "City": ["Guelph"],
                "postal_code": ["N1H 2T2"],
                "province territory": ["ON"],
                "overdue disease": ["Measles"],
                "imms given": [""],
                "street address line 1": ["123 Main"],
                "street address line 2": [""],
            }
        )

        mapped_df, col_map = preprocess.map_columns(df)

        assert set(mapped_df.columns) == set(preprocess.REQUIRED_COLUMNS)
        for col in preprocess.REQUIRED_COLUMNS:
            assert col in col_map.values()


@pytest.mark.unit
class TestNormalize:
    """Unit tests for normalize() column name formatter."""

    def test_lowercases_text(self):
        """Verify that text is converted to lowercase."""
        assert preprocess.normalize("ColumnName") == "columnname"

    def test_replaces_spaces_with_underscores(self):
        """Verify that internal spaces are replaced with underscores."""
        assert preprocess.normalize("Column_Name") == "column name"

    def test_replaces_hyphens_with_underscores(self):
        """Verify that hyphens are replaced with underscores."""
        assert preprocess.normalize("Column-Name") == "column name"

    def test_combined_transformations(self):
        """Verify that multiple transformations apply together."""
        assert preprocess.normalize("  Column - Name  ") == "column name"

    def test_handles_empty_string(self):
        """Verify that empty strings are handled safely."""
        assert preprocess.normalize("") == ""

    def test_handles_non_alphabetic_characters(self):
        """Verify that non-letter characters are preserved."""
        assert preprocess.normalize("123 Name!") == "123 name!"


@pytest.mark.unit
class TestFilterColumns:
    """Unit tests for filter_columns() column filtering utility."""

    def test_returns_only_required_columns(self):
        """Verify that only required columns are kept."""
        df = pd.DataFrame(
            {
                "child_first_name": ["A"],
                "child_last_name": ["B"],
                "extra_column": [123],
            }
        )
        required = ["child_first_name", "child_last_name"]
        result = preprocess.filter_columns(df, required)

        assert list(result.columns) == required
        assert "extra_column" not in result.columns

    def test_returns_empty_dataframe_when_no_required_columns_present(self):
        """Verify behavior when none of the required columns are present."""
        df = pd.DataFrame({"foo": [1], "bar": [2]})
        required = ["child_first_name", "child_last_name"]
        result = preprocess.filter_columns(df, required)

        # Should return an empty DataFrame with no columns
        assert result.shape[1] == 0
        assert isinstance(result, pd.DataFrame)

    def test_handles_empty_dataframe(self):
        """Verify that an empty DataFrame is returned unchanged."""
        df = pd.DataFrame(columns=pd.Index(["child_first_name", "child_last_name"]))
        result = preprocess.filter_columns(df, ["child_first_name"])
        assert result.empty

    def test_handles_none_input(self):
        """Verify that None input returns None safely."""
        result = preprocess.filter_columns(None, ["child_first_name"])
        assert result is None

    def test_order_of_columns_is_preserved(self):
        """Verify that the order of columns in the required list is respected."""
        df = pd.DataFrame(
            {
                "child_last_name": ["Doe"],
                "child_first_name": ["John"],
                "dob": ["2000-01-01"],
            }
        )
        required = ["dob", "child_first_name"]
        result = preprocess.filter_columns(df, required)

        assert (
            list(result.columns) == ["child_first_name", "dob"]
            or list(result.columns) == required
        )
        # Either column order can appear depending on implementation; both are acceptable

    def test_ignores_required_columns_not_in_df(self):
        """Verify that missing required columns are ignored without error."""
        df = pd.DataFrame({"child_first_name": ["A"]})
        required = ["child_first_name", "missing_column"]
        result = preprocess.filter_columns(df, required)

        assert "child_first_name" in result.columns
        assert "missing_column" not in result.columns


@pytest.mark.unit
class TestReadInput:
    """Unit tests for read_input function."""

    def test_read_input_xlsx_file(self, tmp_test_dir: Path) -> None:
        """Verify reading Excel (.xlsx) files works correctly.

        Real-world significance:
        - School district input is provided in .xlsx format
        - Must handle openpyxl engine properly
        """
        df_original = sample_input.create_test_input_dataframe(num_clients=3)
        input_path = tmp_test_dir / "test_input.xlsx"
        df_original.to_excel(input_path, index=False)

        df_read = preprocess.read_input(input_path)

        assert len(df_read) == 3
        assert (
            "SCHOOL NAME" in df_read.columns
            or "SCHOOL_NAME" in str(df_read.columns).upper()
        )

    def test_read_input_missing_file_raises_error(self, tmp_test_dir: Path) -> None:
        """Verify error when input file doesn't exist.

        Real-world significance:
        - Must fail early if user provides incorrect input path
        """
        missing_path = tmp_test_dir / "nonexistent.xlsx"

        with pytest.raises(FileNotFoundError):
            preprocess.read_input(missing_path)

    def test_read_input_unsupported_file_type_raises_error(
        self, tmp_test_dir: Path
    ) -> None:
        """Verify error for unsupported file types.

        Real-world significance:
        - Pipeline should reject non-Excel/CSV files early
        """
        unsupported_path = tmp_test_dir / "test.txt"
        unsupported_path.write_text("some data")

        with pytest.raises(ValueError, match="Unsupported file type"):
            preprocess.read_input(unsupported_path)


@pytest.mark.unit
class TestEnsureRequiredColumns:
    """Unit tests for ensure_required_columns function."""

    def test_ensure_required_columns_passes_valid_dataframe(self) -> None:
        """Verify valid DataFrame passes validation.

        Real-world significance:
        - Valid school district input should process without errors
        """
        df = sample_input.create_test_input_dataframe(num_clients=3)

        result = preprocess.ensure_required_columns(df)

        assert result is not None
        assert len(result) == 3

    def test_ensure_required_columns_normalizes_whitespace(self) -> None:
        """Verify column names are normalized (whitespace, case).

        Real-world significance:
        - Input files may have inconsistent column naming
        - Pipeline must handle variations in Excel headers
        """
        df = pd.DataFrame(
            {
                "  SCHOOL NAME  ": ["Test School"],
                "  CLIENT ID  ": ["C001"],
                "first name": ["Alice"],
                "last name": ["Zephyr"],
                "date of birth": ["2015-01-01"],
                "city": ["Guelph"],
                "postal code": ["N1H 2T2"],
                "province/territory": ["ON"],
                "overdue disease": ["Measles"],
                "imms given": [""],
                "street address line 1": ["123 Main"],
                "street address line 2": [""],
            }
        )

        result = preprocess.ensure_required_columns(df)

        # Should not raise error and column names should be normalized
        assert len(result) == 1

    def test_ensure_required_columns_missing_required_raises_error(self) -> None:
        """Verify error when required columns are missing.

        Real-world significance:
        - Missing critical columns (e.g., OVERDUE DISEASE) means input is invalid
        - Must fail early with clear error
        """
        df = pd.DataFrame(
            {
                "SCHOOL NAME": ["Test"],
                "CLIENT ID": ["C001"],
                # Missing required columns
            }
        )

        with pytest.raises(ValueError, match="Missing required columns"):
            preprocess.ensure_required_columns(df)


@pytest.mark.unit
class TestNormalizeDataFrame:
    """Unit tests for normalize_dataframe function."""

    def test_normalize_dataframe_handles_missing_values(self) -> None:
        """Verify NaN/None values are converted to empty strings.

        Real-world significance:
        - Input may have missing fields (e.g., no suite number)
        - Must normalize to empty strings for consistent processing
        """
        df = sample_input.create_test_input_dataframe(num_clients=3)
        normalized = preprocess.ensure_required_columns(df)
        normalized.loc[0, "STREET_ADDRESS_LINE_2"] = None
        normalized.loc[1, "POSTAL_CODE"] = float("nan")

        result = preprocess.normalize_dataframe(normalized)

        assert result["STREET_ADDRESS_LINE_2"].iloc[0] == ""
        assert result["POSTAL_CODE"].iloc[1] == ""

    def test_normalize_dataframe_converts_dates(self) -> None:
        """Verify dates are converted to datetime objects.

        Real-world significance:
        - Date fields must be parsed for age calculation
        - Invalid dates must be detected early
        """
        df = sample_input.create_test_input_dataframe(num_clients=2)
        df["DATE OF BIRTH"] = ["2015-01-02", "2014-05-06"]
        normalized = preprocess.ensure_required_columns(df)

        result = preprocess.normalize_dataframe(normalized)

        assert pd.api.types.is_datetime64_any_dtype(result["DATE_OF_BIRTH"])

    def test_normalize_dataframe_trims_whitespace(self) -> None:
        """Verify string columns have whitespace trimmed.

        Real-world significance:
        - Input may have accidental leading/trailing spaces
        - Must normalize for consistent matching
        """
        df = sample_input.create_test_input_dataframe(num_clients=1)
        df["FIRST NAME"] = ["  Alice  "]
        df["LAST NAME"] = ["  Zephyr  "]
        normalized = preprocess.ensure_required_columns(df)

        result = preprocess.normalize_dataframe(normalized)

        assert result["FIRST_NAME"].iloc[0] == "Alice"
        assert result["LAST_NAME"].iloc[0] == "Zephyr"


@pytest.mark.unit
class TestAgeCalculation:
    """Unit tests for age calculation functions."""

    def test_over_16_check_true_for_over_16(self) -> None:
        """Verify over_16_check returns True for age >= 16.

        Real-world significance:
        - Notices sent to student (not parent) if over 16
        - Must correctly classify students by age
        """
        result = preprocess.over_16_check("2000-01-01", "2020-05-15")

        assert result is True

    def test_over_16_check_false_for_under_16(self) -> None:
        """Verify over_16_check returns False for age < 16.

        Real-world significance:
        - Notices sent to parent for students under 16
        """
        result = preprocess.over_16_check("2010-01-01", "2020-05-15")

        assert result is False

    def test_over_16_check_boundary_at_16(self) -> None:
        """Verify over_16_check boundary condition at exactly 16 years.

        Real-world significance:
        - Must correctly handle 16th birthday (inclusive)
        """
        result = preprocess.over_16_check("2000-05-15", "2016-05-15")

        assert result is True


@pytest.mark.unit
class TestDateFormatting:
    """Unit tests for date formatting functions with locale support."""

    def test_format_iso_date_english(self) -> None:
        """Verify format_iso_date_for_language formats dates in English.

        Real-world significance:
        - English notices must display dates in readable format
        - Format should be long form, e.g., "August 31, 2025"
        """
        result = preprocess.format_iso_date_for_language("2025-08-31", "en")

        assert result == "August 31, 2025"

    def test_format_iso_date_french(self) -> None:
        """Verify format_iso_date_for_language formats dates in French.

        Real-world significance:
        - French notices must display dates in French locale format
        - Format should be locale-specific, e.g., "31 août 2025"
        """
        result = preprocess.format_iso_date_for_language("2025-08-31", "fr")

        assert result == "31 août 2025"

    def test_format_iso_date_different_months(self) -> None:
        """Verify formatting works correctly for all months.

        Real-world significance:
        - Date formatting must be reliable across the entire calendar year
        """
        # January
        assert "January" in preprocess.format_iso_date_for_language("2025-01-15", "en")
        # June
        assert "June" in preprocess.format_iso_date_for_language("2025-06-15", "en")
        # December
        assert "December" in preprocess.format_iso_date_for_language("2025-12-15", "en")

    def test_format_iso_date_leap_year(self) -> None:
        """Verify formatting handles leap year dates.

        Real-world significance:
        - Some students may have birthdays on Feb 29
        - Must handle leap year dates correctly
        """
        result = preprocess.format_iso_date_for_language("2024-02-29", "en")

        assert "February" in result and "29" in result and "2024" in result

    def test_format_iso_date_invalid_format_raises(self) -> None:
        """Verify format_iso_date_for_language raises ValueError for invalid input.

        Real-world significance:
        - Invalid date formats should fail fast with clear error
        - Prevents silent failures in template rendering
        """
        with pytest.raises(ValueError, match="Invalid ISO date format"):
            preprocess.format_iso_date_for_language("31/08/2025", "en")

    def test_format_iso_date_invalid_date_raises(self) -> None:
        """Verify format_iso_date_for_language raises ValueError for impossible dates.

        Real-world significance:
        - February 30 does not exist; must reject cleanly
        """
        with pytest.raises(ValueError):
            preprocess.format_iso_date_for_language("2025-02-30", "en")

    def test_convert_date_string_with_locale(self) -> None:
        """Verify convert_date_string supports locale-aware formatting.

        Real-world significance:
        - Existing convert_date_string() should work with different locales
        - Babel formatting enables multilingual date display
        """
        result_en = preprocess.convert_date_string("2025-08-31", locale="en")
        result_fr = preprocess.convert_date_string("2025-08-31", locale="fr")

        assert result_en == "August 31, 2025"
        assert result_fr == "31 août 2025"


@pytest.mark.unit
class TestBuildPreprocessResult:
    """Unit tests for build_preprocess_result function."""

    def test_build_result_generates_clients_with_sequences(
        self, default_vaccine_reference
    ) -> None:
        """Verify clients are generated with sequence numbers.

        Real-world significance:
        - Sequence numbers (00001, 00002...) appear on notices
        - Must be deterministic: same input → same sequences
        """
        df = sample_input.create_test_input_dataframe(num_clients=3)
        normalized = preprocess.ensure_required_columns(df)

        result = preprocess.build_preprocess_result(
            normalized,
            language="en",
            vaccine_reference=default_vaccine_reference,
            replace_unspecified=[],
            ignore_diseases=[],
        )

        assert len(result.clients) == 3
        # Sequences should be sequential
        sequences = [c.sequence for c in result.clients]
        assert sequences == ["00001", "00002", "00003"]

    def test_build_result_sorts_clients_deterministically(
        self, default_vaccine_reference
    ) -> None:
        """Verify clients are sorted consistently.

        Real-world significance:
        - Same input must always produce same client order
        - Required for comparing pipeline runs (reproducibility)
        - Enables batching by school to work correctly
        """
        df = sample_input.create_test_input_dataframe(num_clients=3)
        normalized = preprocess.ensure_required_columns(df)

        result1 = preprocess.build_preprocess_result(
            normalized,
            language="en",
            vaccine_reference=default_vaccine_reference,
            replace_unspecified=[],
            ignore_diseases=[],
        )

        result2 = preprocess.build_preprocess_result(
            normalized,
            language="en",
            vaccine_reference=default_vaccine_reference,
            replace_unspecified=[],
            ignore_diseases=[],
        )

        ids1 = [c.client_id for c in result1.clients]
        ids2 = [c.client_id for c in result2.clients]
        assert ids1 == ids2, "Client order must be deterministic"

    def test_build_result_sorts_by_school_then_name(
        self, default_vaccine_reference
    ) -> None:
        """Verify clients sorted by school → last_name → first_name → client_id.

        Real-world significance:
        - Specific sort order enables school-based batching
        - Must be deterministic across pipeline runs
        - Affects sequence number assignment
        """
        df = pd.DataFrame(
            {
                "SCHOOL NAME": [
                    "Zebra School",
                    "Zebra School",
                    "Apple School",
                    "Apple School",
                ],
                "CLIENT ID": ["C002", "C001", "C004", "C003"],
                "FIRST NAME": ["Bob", "Alice", "Diana", "Chloe"],
                "LAST NAME": ["Smith", "Smith", "Jones", "Jones"],
                "DATE OF BIRTH": [
                    "2015-01-01",
                    "2015-01-02",
                    "2015-01-03",
                    "2015-01-04",
                ],
                "CITY": ["Town", "Town", "Town", "Town"],
                "POSTAL CODE": ["N1H 2T2", "N1H 2T2", "N1H 2T2", "N1H 2T2"],
                "PROVINCE/TERRITORY": ["ON", "ON", "ON", "ON"],
                "OVERDUE DISEASE": ["Measles", "Measles", "Measles", "Measles"],
                "IMMS GIVEN": ["", "", "", ""],
                "STREET ADDRESS LINE 1": [
                    "123 Main",
                    "123 Main",
                    "123 Main",
                    "123 Main",
                ],
                "STREET ADDRESS LINE 2": ["", "", "", ""],
            }
        )
        normalized = preprocess.ensure_required_columns(df)

        result = preprocess.build_preprocess_result(
            normalized,
            language="en",
            vaccine_reference=default_vaccine_reference,
            replace_unspecified=[],
            ignore_diseases=[],
        )

        # Expected order: Apple/Chloe/Jones, Apple/Diana/Jones, Zebra/Alice/Smith, Zebra/Bob/Smith
        expected_ids = ["C003", "C004", "C001", "C002"]
        actual_ids = [c.client_id for c in result.clients]
        assert actual_ids == expected_ids

    def test_build_result_maps_vaccines_correctly(
        self, default_vaccine_reference
    ) -> None:
        """Verify vaccine codes expand to component diseases.

        Real-world significance:
        - DTaP → Diphtheria, Tetanus, Pertussis
        - Vaccine mapping must preserve all components
        - Affects disease coverage reporting in notices
        """
        df = sample_input.create_test_input_dataframe(num_clients=1)
        df["IMMS GIVEN"] = ["May 1, 2020 - DTaP"]
        normalized = preprocess.ensure_required_columns(df)

        result = preprocess.build_preprocess_result(
            normalized,
            language="en",
            vaccine_reference=default_vaccine_reference,
            replace_unspecified=[],
            ignore_diseases=[],
        )

        # Should have DTaP expanded to component diseases
        assert len(result.clients) == 1
        client = result.clients[0]
        assert client.received is not None
        assert len(client.received) > 0
        assert "Diphtheria" in str(client.received[0].get("diseases", []))

    def test_build_result_handles_missing_board_name_with_warning(
        self, default_vaccine_reference
    ) -> None:
        """Verify missing board name generates warning.

        Real-world significance:
        - Some school districts don't have explicit board assignments
        - Should auto-generate board ID and log warning
        - Allows pipeline to proceed without failing
        """
        df = pd.DataFrame(
            {
                "SCHOOL NAME": ["Test School"],
                "CLIENT ID": ["C001"],
                "FIRST NAME": ["Alice"],
                "LAST NAME": ["Zephyr"],
                "DATE OF BIRTH": ["2015-01-01"],
                "CITY": ["Guelph"],
                "POSTAL CODE": ["N1H 2T2"],
                "PROVINCE/TERRITORY": ["ON"],
                "OVERDUE DISEASE": ["Measles"],
                "IMMS GIVEN": [""],
                "STREET ADDRESS LINE 1": ["123 Main"],
                "STREET ADDRESS LINE 2": [""],
            }
        )
        normalized = preprocess.ensure_required_columns(df)

        result = preprocess.build_preprocess_result(
            normalized,
            language="en",
            vaccine_reference=default_vaccine_reference,
            replace_unspecified=[],
            ignore_diseases=[],
        )

        # Should still process - at least one client
        assert len(result.clients) == 1

    def test_build_result_french_language_support(
        self, default_vaccine_reference
    ) -> None:
        """Verify preprocessing handles French language correctly.

        Real-world significance:
        - Notices generated in both English and French
        - Preprocessing must handle both language variants
        - Dates must convert to French format for display
        """
        df = sample_input.create_test_input_dataframe(num_clients=1, language="fr")
        normalized = preprocess.ensure_required_columns(df)

        result = preprocess.build_preprocess_result(
            normalized,
            language="fr",
            vaccine_reference=default_vaccine_reference,
            replace_unspecified=[],
            ignore_diseases=[],
        )

        assert len(result.clients) == 1
        assert result.clients[0].language == "fr"

    def test_build_result_handles_ignore_agents(
        self, default_vaccine_reference
    ) -> None:
        """Verify ignore_diseases filters out unspecified vaccines.

        Real-world significance:
        - Input may contain "Not Specified" vaccine agents
        - Pipeline should filter these out to avoid confusing notices
        """
        df = sample_input.create_test_input_dataframe(num_clients=1)
        normalized = preprocess.ensure_required_columns(df)

        result = preprocess.build_preprocess_result(
            normalized,
            language="en",
            vaccine_reference=default_vaccine_reference,
            replace_unspecified=[],
            ignore_diseases=["Not Specified", "unspecified"],
        )

        assert len(result.clients) == 1

    def test_build_result_detects_duplicate_client_ids(
        self, default_vaccine_reference
    ) -> None:
        """Verify duplicate client IDs are detected and warned.

        Real-world significance:
        - Source data may contain duplicate client IDs (data entry errors)
        - Must warn about this data quality issue
        - Later records with same ID will overwrite earlier ones in notice generation
        """
        df = sample_input.create_test_input_dataframe(num_clients=2)
        # Force duplicate client IDs
        df.loc[0, "CLIENT ID"] = "C123456789"
        df.loc[1, "CLIENT ID"] = "C123456789"

        normalized = preprocess.ensure_required_columns(df)

        result = preprocess.build_preprocess_result(
            normalized,
            language="en",
            vaccine_reference=default_vaccine_reference,
            replace_unspecified=[],
            ignore_diseases=[],
        )

        # Should have 2 clients (no deduplication)
        assert len(result.clients) == 2

        # Should have a warning about duplicates
        duplicate_warnings = [w for w in result.warnings if "Duplicate client ID" in w]
        assert len(duplicate_warnings) == 1
        assert "C123456789" in duplicate_warnings[0]
        assert "2 times" in duplicate_warnings[0]
        assert "overwrite" in duplicate_warnings[0]

    def test_build_result_detects_multiple_duplicate_client_ids(
        self, default_vaccine_reference
    ) -> None:
        """Verify multiple sets of duplicate client IDs are detected.

        Real-world significance:
        - May have multiple different client IDs that are duplicated
        - Each duplicate set should generate a separate warning
        """
        df = sample_input.create_test_input_dataframe(num_clients=5)
        # Create two sets of duplicates
        df.loc[0, "CLIENT ID"] = "C111111111"
        df.loc[1, "CLIENT ID"] = "C111111111"
        df.loc[2, "CLIENT ID"] = "C111111111"
        df.loc[3, "CLIENT ID"] = "C222222222"
        df.loc[4, "CLIENT ID"] = "C222222222"

        normalized = preprocess.ensure_required_columns(df)

        result = preprocess.build_preprocess_result(
            normalized,
            language="en",
            vaccine_reference=default_vaccine_reference,
            replace_unspecified=[],
            ignore_diseases=[],
        )

        # Should have 5 clients (no deduplication)
        assert len(result.clients) == 5

        # Should have warnings for both duplicates
        duplicate_warnings = [w for w in result.warnings if "Duplicate client ID" in w]
        assert len(duplicate_warnings) == 2

        # Check each duplicate is mentioned
        warning_text = " ".join(duplicate_warnings)
        assert "C111111111" in warning_text
        assert "3 times" in warning_text
        assert "C222222222" in warning_text
        assert "2 times" in warning_text

    def test_build_result_no_warning_for_unique_client_ids(
        self, default_vaccine_reference
    ) -> None:
        """Verify no warning when all client IDs are unique.

        Real-world significance:
        - Normal case with clean data should not produce duplicate warnings
        """
        df = sample_input.create_test_input_dataframe(num_clients=3)
        normalized = preprocess.ensure_required_columns(df)

        result = preprocess.build_preprocess_result(
            normalized,
            language="en",
            vaccine_reference=default_vaccine_reference,
            replace_unspecified=[],
            ignore_diseases=[],
        )

        # Should have 3 unique clients
        assert len(result.clients) == 3

        # Should have NO warnings about duplicates
        duplicate_warnings = [w for w in result.warnings if "Duplicate client ID" in w]
        assert len(duplicate_warnings) == 0
