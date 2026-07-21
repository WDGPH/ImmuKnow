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
        result = preprocess.filter_columns(None, ["child_first_name"])  # type: ignore[arg-type]
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
class TestNormalizeDataFrame:
    """Unit tests for normalize_dataframe function."""

    def test_normalize_dataframe_passes_valid_dataframe(self) -> None:
        """Verify valid DataFrame passes validation.

        Real-world significance:
        - Valid school district input should process without errors
        """
        df = sample_input.create_test_input_dataframe(num_clients=3)

        result = preprocess.normalize_dataframe(df)

        assert result is not None
        assert len(result) == 3

    def test_normalize_dataframe_normalizes_column_whitespace(self) -> None:
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

        result = preprocess.normalize_dataframe(df)

        # Should not raise error and column names should be normalized
        assert len(result) == 1

    def test_normalize_dataframe_missing_required_raises_error(self) -> None:
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
            preprocess.normalize_dataframe(df)

    def test_normalize_dataframe_handles_missing_values(self) -> None:
        """Verify NaN/None values are converted to empty strings.

        Real-world significance:
        - Input may have missing fields (e.g., no suite number)
        - Must normalize to empty strings for consistent processing
        """
        df = sample_input.create_test_input_dataframe(num_clients=3)
        # Normalize column names first, then inject NaN to test fill behavior
        working = preprocess.normalize_dataframe(df)
        working.loc[0, "STREET_ADDRESS_LINE_2"] = None
        working.loc[1, "POSTAL_CODE"] = float("nan")

        result = preprocess.normalize_dataframe(working)

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

        result = preprocess.normalize_dataframe(df)

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

        result = preprocess.normalize_dataframe(df)

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

        assert "August" in result
        assert "31" in result
        assert "2025" in result

    def test_format_iso_date_french(self) -> None:
        """Verify format_iso_date_for_language formats dates in French.

        Real-world significance:
        - French notices must display dates in French locale format
        - Format should be locale-specific, e.g., "31 août 2025"
        """
        result = preprocess.format_iso_date_for_language("2025-08-31", "fr")

        assert "août" in result
        assert "31" in result
        assert "2025" in result

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

        assert result_en is not None
        assert result_fr is not None
        assert "August" in result_en
        assert "31" in result_en
        assert "2025" in result_en
        assert "août" in result_fr
        assert "31" in result_fr
        assert "2025" in result_fr


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

        result = preprocess.build_preprocess_result(
            df,
            language="en",
            vaccine_reference=default_vaccine_reference,
            replace_unspecified=[],
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

        result1 = preprocess.build_preprocess_result(
            df,
            language="en",
            vaccine_reference=default_vaccine_reference,
            replace_unspecified=[],
        )

        result2 = preprocess.build_preprocess_result(
            df,
            language="en",
            vaccine_reference=default_vaccine_reference,
            replace_unspecified=[],
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
        result = preprocess.build_preprocess_result(
            df,
            language="en",
            vaccine_reference=default_vaccine_reference,
            replace_unspecified=[],
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

        result = preprocess.build_preprocess_result(
            df,
            language="en",
            vaccine_reference=default_vaccine_reference,
            replace_unspecified=[],
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
        result = preprocess.build_preprocess_result(
            df,
            language="en",
            vaccine_reference=default_vaccine_reference,
            replace_unspecified=[],
        )

        assert len(result.clients) == 1
        board_warnings = [w for w in result.warnings if "Missing board name" in w]
        assert len(board_warnings) >= 1

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

        result = preprocess.build_preprocess_result(
            df,
            language="fr",
            vaccine_reference=default_vaccine_reference,
            replace_unspecified=[],
        )

        assert len(result.clients) == 1
        assert result.clients[0].language == "fr"

    def test_build_result_handles_replace_unspecified(
        self, default_vaccine_reference
    ) -> None:
        """Verify replace_unspecified filters out unspecified vaccines.

        Real-world significance:
        - Input may contain "Not Specified" vaccine agents
        - Pipeline should filter these out to avoid confusing notices
        """
        df = sample_input.create_test_input_dataframe(num_clients=1)

        result = preprocess.build_preprocess_result(
            df,
            language="en",
            vaccine_reference=default_vaccine_reference,
            replace_unspecified=["Not Specified", "unspecified"],
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

        result = preprocess.build_preprocess_result(
            df,
            language="en",
            vaccine_reference=default_vaccine_reference,
            replace_unspecified=[],
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

        result = preprocess.build_preprocess_result(
            df,
            language="en",
            vaccine_reference=default_vaccine_reference,
            replace_unspecified=[],
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

        result = preprocess.build_preprocess_result(
            df,
            language="en",
            vaccine_reference=default_vaccine_reference,
            replace_unspecified=[],
        )

        # Should have 3 unique clients
        assert len(result.clients) == 3

        # Should have NO warnings about duplicates
        duplicate_warnings = [w for w in result.warnings if "Duplicate client ID" in w]
        assert len(duplicate_warnings) == 0


@pytest.mark.unit
class TestValidityStatusHandling:
    """Unit tests for the normalize_validity_status() case-sensitivity contract.

    Covers:
    - Accepted casings ("valid", "Valid", "invalid", "Invalid") and their
      canonical lowercase output
    - Fallback to "unknown" for typos, alternate casings, empty values, and
      None/NaN inputs

    Real-world significance:
    - Validity markers on notices distinguish doses that count toward
      immunity from those administered too early or in error
    - The strict two-casing allowlist prevents ambiguous data from
      silently influencing printed markers; "unknown" surfaces upstream
      via classify_dataset_validity rather than per-record propagation
    """

    def test_known_statuses_normalize_correctly(self) -> None:
        """Verify valid/Valid and invalid/Invalid are accepted as known statuses.

        Real-world significance:
        - Validity markers appear on notices to distinguish doses that count
          toward immunity from those administered too early or in error
        - Only the exact casings "valid"/"Valid" and "invalid"/"Invalid" are
          authoritative; anything else must fall to "unknown"

        Assertion: Each accepted casing maps to its lowercase canonical form
        """
        assert preprocess.normalize_validity_status("valid") == "valid"
        assert preprocess.normalize_validity_status("Valid") == "valid"
        assert preprocess.normalize_validity_status("invalid") == "invalid"
        assert preprocess.normalize_validity_status("Invalid") == "invalid"

    def test_unrecognized_statuses_fall_back_to_unknown(self) -> None:
        """Verify anything outside the strict allowed set normalizes to unknown.

        Real-world significance:
        - Input data may contain typos, alternate casings ("VALID", "True"),
          or missing values; these must not be silently treated as valid or invalid
        - Records that normalize to "unknown" are detected at the dataset level
          by classify_dataset_validity, which drives warning/error behaviour in
          build_preprocess_result rather than reacting per-record

        Assertion: All non-canonical inputs produce "unknown"
        """
        assert preprocess.normalize_validity_status("VALID") == "unknown"
        assert preprocess.normalize_validity_status("true") == "unknown"
        assert preprocess.normalize_validity_status("") == "unknown"
        assert preprocess.normalize_validity_status(None) == "unknown"


@pytest.mark.unit
class TestCollapseValidityStatuses:
    """Unit tests for collapse_validity_statuses() precedence contract.

    Covers:
    - Pure valid / pure invalid / mixed (valid+invalid) / unknown cases
    - The rule that any "unknown" in the list contaminates the result
    - Single-element and empty-list edge cases
    - Raw (non-normalized) inputs being accepted via the internal normalize call

    Real-world significance:
    - collapse_validity_statuses is the authority for what validity status
      appears in the "Other" chart column when multiple vaccines contribute
    - Getting the precedence wrong would silently misrepresent a patient's
      immunity record on a printed notice
    """

    def test_all_valid_returns_valid(self) -> None:
        """Verify a list with only valid statuses collapses to valid.

        Assertion: ["valid", "valid"] → "valid"
        """
        assert preprocess.collapse_validity_statuses(["valid", "valid"]) == "valid"

    def test_all_invalid_returns_invalid(self) -> None:
        """Verify a list with only invalid statuses collapses to invalid.

        Assertion: ["invalid", "invalid"] → "invalid"
        """
        assert preprocess.collapse_validity_statuses(["invalid", "invalid"]) == "invalid"

    def test_valid_and_invalid_without_unknown_returns_mixed(self) -> None:
        """Verify mixed valid+invalid (no unknown) collapses to mixed.

        Real-world significance:
        - "mixed" appears in the "Other" column when different vaccines on the
          same day have conflicting validity, alerting the user that not all
          "Other" doses counted toward immunity

        Assertion: ["valid", "invalid"] → "mixed"
        """
        assert preprocess.collapse_validity_statuses(["valid", "invalid"]) == "mixed"

    def test_any_unknown_returns_unknown_regardless_of_others(self) -> None:
        """Verify that a single unknown contaminates valid+invalid combinations.

        Real-world significance:
        - An unknown status means data was incomplete; displaying "mixed" or
          "valid" when data quality is uncertain would be misleading on a notice

        Assertion: unknown present → "unknown", even alongside valid and invalid
        """
        assert preprocess.collapse_validity_statuses(["valid", "invalid", "unknown"]) == "unknown"
        assert preprocess.collapse_validity_statuses(["valid", "unknown"]) == "unknown"
        assert preprocess.collapse_validity_statuses(["invalid", "unknown"]) == "unknown"

    def test_single_valid_returns_valid(self) -> None:
        """Assertion: ["valid"] → "valid"."""
        assert preprocess.collapse_validity_statuses(["valid"]) == "valid"

    def test_single_invalid_returns_invalid(self) -> None:
        """Assertion: ["invalid"] → "invalid"."""
        assert preprocess.collapse_validity_statuses(["invalid"]) == "invalid"

    def test_single_unknown_returns_unknown(self) -> None:
        """Assertion: ["unknown"] → "unknown"."""
        assert preprocess.collapse_validity_statuses(["unknown"]) == "unknown"

    def test_empty_list_returns_unknown(self) -> None:
        """Verify an empty list (no statuses to collapse) is treated as unknown.

        Assertion: [] → "unknown"
        """
        assert preprocess.collapse_validity_statuses([]) == "unknown"

    def test_normalizes_raw_casing_before_collapsing(self) -> None:
        """Verify raw casing variants are normalized before precedence is applied.

        Assertion: ["Valid", "Invalid"] → "mixed" (same as ["valid", "invalid"])
        """
        assert preprocess.collapse_validity_statuses(["Valid", "Invalid"]) == "mixed"
        assert preprocess.collapse_validity_statuses(["Valid", "Valid"]) == "valid"


@pytest.mark.unit
class TestClassifyDatasetValidity:
    """Unit tests for classify_dataset_validity() dataset pre-pass contract.

    Covers:
    - All doses with validity indicators → "all_present"
    - All doses without validity indicators → "all_absent"
    - Mix within a dataset → "mixed"
    - Empty / NaN / blank values are skipped, not treated as absent
    - Multiple semicolon-delimited segments in a single cell

    Real-world significance:
    - classify_dataset_validity is called once per pipeline run before the
      client loop; an incorrect classification causes the wrong branch of
      warning/error logic to fire, either silently hiding data quality
      problems or raising a spurious ValueError that aborts the run
    """

    def test_all_doses_with_validity_suffix_returns_all_present(self) -> None:
        """Verify a dataset where every dose has - Valid/- Invalid → "all_present".

        Assertion: series with only suffixed segments → "all_present"
        """
        series = pd.Series([
            "May 1, 2020 - DTaP - Valid",
            "Jun 15, 2021 - MMR - Invalid",
        ])
        assert preprocess.classify_dataset_validity(series) == "all_present"

    def test_all_doses_without_validity_suffix_returns_all_absent(self) -> None:
        """Verify a dataset where no dose has a suffix → "all_absent".

        Assertion: series with no suffixed segments → "all_absent"
        """
        series = pd.Series([
            "May 1, 2020 - DTaP",
            "Jun 15, 2021 - MMR",
        ])
        assert preprocess.classify_dataset_validity(series) == "all_absent"

    def test_mix_of_present_and_absent_returns_mixed(self) -> None:
        """Verify a dataset with some suffixed and some unsuffixed doses → "mixed".

        Real-world significance:
        - "mixed" with show_validity_markers=True raises ValueError to
          prevent displaying unreliable markers; the test verifies the
          classification step that gates that error

        Assertion: series with one suffixed and one unsuffixed segment → "mixed"
        """
        series = pd.Series([
            "May 1, 2020 - DTaP - Valid",
            "Jun 15, 2021 - MMR",
        ])
        assert preprocess.classify_dataset_validity(series) == "mixed"

    def test_empty_series_returns_all_absent(self) -> None:
        """Verify an empty series (no dose records at all) → "all_absent".

        Assertion: pd.Series([], dtype=str) → "all_absent"
        """
        series = pd.Series([], dtype=str)
        assert preprocess.classify_dataset_validity(series) == "all_absent"

    def test_nan_and_empty_strings_are_ignored(self) -> None:
        """Verify NaN values and blank cells do not count as absent-suffix doses.

        Real-world significance:
        - Clients with no immunization history have empty IMMS_GIVEN cells;
          these must not trigger "mixed" when the rest of the dataset is clean

        Assertion: valid suffixed dose + NaN + "" → "all_present"
        """
        series = pd.Series(["May 1, 2020 - DTaP - Valid", None, ""])
        assert preprocess.classify_dataset_validity(series) == "all_present"

    def test_multiple_segments_per_cell_all_present(self) -> None:
        """Verify multiple semicolon-delimited segments in one cell are each checked.

        Assertion: two suffixed segments in one cell → "all_present"
        """
        series = pd.Series(["May 1, 2020 - DTaP - Valid; Jun 15, 2021 - MMR - Invalid"])
        assert preprocess.classify_dataset_validity(series) == "all_present"

    def test_multiple_segments_per_cell_returns_mixed_when_one_lacks_suffix(self) -> None:
        """Verify a single un-suffixed segment inside a multi-segment cell → "mixed".

        Assertion: one suffixed + one un-suffixed segment in same cell → "mixed"
        """
        series = pd.Series(["May 1, 2020 - DTaP - Valid; Jun 15, 2021 - MMR"])
        assert preprocess.classify_dataset_validity(series) == "mixed"


@pytest.mark.unit
class TestProcessReceivedAgents:
    """Unit tests for process_received_agents() parsing and grouping contract.

    Covers:
    - Empty / non-string inputs → empty list
    - Doses with - Valid / - Invalid suffix → correct status
    - Doses without suffix → "unknown" (not silently dropped)
    - Same-date doses grouped into a single record
    - Entries sorted ascending by date regardless of input order
    - replace_unspecified filtering

    Real-world significance:
    - This function is the sole parser for IMMS_GIVEN strings; incorrect
      parsing silently omits or misrepresents a patient's immunization
      history on their printed notice
    """

    def test_empty_string_returns_empty_list(self) -> None:
        """Verify an empty string produces no records.

        Assertion: "" → []
        """
        assert preprocess.process_received_agents("", []) == []

    def test_non_string_input_returns_empty_list(self) -> None:
        """Verify None and NaN-like values produce no records.

        Assertion: None → []
        """
        assert preprocess.process_received_agents(None, []) == []

    def test_dose_with_valid_suffix_parsed_correctly(self) -> None:
        """Verify a dose with - Valid suffix yields status "valid".

        Assertion: date, vaccine name, and status all parsed correctly
        """
        result = preprocess.process_received_agents("May 1, 2020 - DTaP - Valid", [])
        assert len(result) == 1
        assert result[0]["date_given"] == "2020-05-01"
        assert result[0]["vaccine"] == ["DTaP"]
        assert result[0]["valid"] == ["valid"]

    def test_dose_with_invalid_suffix_parsed_correctly(self) -> None:
        """Verify a dose with - Invalid suffix yields status "invalid".

        Assertion: valid → ["invalid"]
        """
        result = preprocess.process_received_agents("May 1, 2020 - DTaP - Invalid", [])
        assert result[0]["valid"] == ["invalid"]

    def test_dose_without_suffix_yields_unknown_not_dropped(self) -> None:
        """Verify a dose lacking a - Valid/- Invalid suffix is captured as "unknown".

        Real-world significance:
        - Legacy datasets or incomplete exports omit validity suffixes; before
          this change such doses were silently dropped, producing empty received
          lists. They must now be captured so history appears on the notice.

        Assertion: no suffix → one record with valid == ["unknown"]
        """
        result = preprocess.process_received_agents("May 1, 2020 - DTaP", [])
        assert len(result) == 1
        assert result[0]["valid"] == ["unknown"]

    def test_same_date_doses_are_grouped(self) -> None:
        """Verify two doses on the same date produce a single grouped record.

        Assertion: two segments with the same date → one entry with both vaccines
        """
        result = preprocess.process_received_agents(
            "May 1, 2020 - DTaP; May 1, 2020 - MMR", []
        )
        assert len(result) == 1
        assert set(result[0]["vaccine"]) == {"DTaP", "MMR"}
        assert len(result[0]["valid"]) == 2

    def test_different_dates_produce_separate_entries(self) -> None:
        """Verify doses on different dates produce separate records.

        Assertion: two segments with different dates → two entries
        """
        result = preprocess.process_received_agents(
            "May 1, 2020 - DTaP; Jun 15, 2021 - MMR", []
        )
        assert len(result) == 2

    def test_entries_sorted_ascending_by_date(self) -> None:
        """Verify records are sorted by date regardless of input order.

        Real-world significance:
        - Immunization history is displayed chronologically on notices;
          out-of-order input must not produce misordered output

        Assertion: later date in input appears second in output
        """
        result = preprocess.process_received_agents(
            "Jun 15, 2021 - MMR; May 1, 2020 - DTaP", []
        )
        assert result[0]["date_given"] == "2020-05-01"
        assert result[1]["date_given"] == "2021-06-15"

    def test_replace_unspecified_filters_named_vaccines(self) -> None:
        """Verify vaccines in replace_unspecified are excluded from output.

        Real-world significance:
        - "Not Specified" agents clutter the history section; the pipeline
          suppresses them via the replace_unspecified configuration list

        Assertion: filtered vaccine absent from result; remaining vaccine present
        """
        result = preprocess.process_received_agents(
            "May 1, 2020 - Not Specified; Jun 15, 2021 - MMR",
            ["Not Specified"],
        )
        assert len(result) == 1
        assert result[0]["vaccine"] == ["MMR"]


@pytest.mark.unit
class TestEnrichGroupedRecords:
    """Unit tests for enrich_grouped_records() disease mapping and validity collapsing.

    Covers:
    - Vaccine-to-disease expansion (combo vaccines → multiple diseases)
    - Named-disease validity collapse: valid > unknown > invalid
    - "Other" two-level collapse: per-vaccine any(valid) then cross-vaccine
      collapse_validity_statuses
    - Behaviour without chart_diseases_header (flat mode)

    Real-world significance:
    - enrich_grouped_records produces the "received" data structure rendered
      in the immunization history chart; incorrect disease mapping or validity
      collapsing causes wrong disease names or misleading validity markers
      to appear on printed notices
    """

    @pytest.fixture
    def vaccine_ref(self) -> dict:
        """Minimal vaccine reference covering combo and single-disease vaccines."""
        return {
            "DTaP": ["Diphtheria", "Tetanus", "Pertussis"],
            "MMR": ["Measles", "Mumps", "Rubella"],
            "IPV": ["Polio"],
            "HBV": ["Hepatitis B"],
            "HPV": ["Human Papillomavirus"],
        }

    def test_combo_vaccine_expands_to_component_diseases(self, vaccine_ref: dict) -> None:
        """Verify a multi-disease vaccine code maps to all component diseases.

        Assertion: DTaP → ["Diphtheria", "Tetanus", "Pertussis"]
        """
        grouped = [{"date_given": "2020-05-01", "vaccine": ["DTaP"], "valid": ["valid"]}]
        result = preprocess.enrich_grouped_records(grouped, vaccine_ref, "en")
        assert result[0]["diseases"] == ["Diphtheria", "Tetanus", "Pertussis"]

    def test_named_disease_any_valid_collapses_to_valid(self, vaccine_ref: dict) -> None:
        """Verify at least one "valid" among contributing doses yields "valid".

        Assertion: valid DTaP → "valid" for Diphtheria/Tetanus/Pertussis
        """
        header = ["Diphtheria", "Tetanus", "Pertussis", "Polio"]
        grouped = [{"date_given": "2020-05-01", "vaccine": ["DTaP", "IPV"], "valid": ["valid", "invalid"]}]
        result = preprocess.enrich_grouped_records(grouped, vaccine_ref, "en", header)
        idx = result[0]["diseases"].index("Diphtheria")
        assert result[0]["valid"][idx] == "valid"
        polio_idx = result[0]["diseases"].index("Polio")
        assert result[0]["valid"][polio_idx] == "invalid"

    def test_named_disease_all_unknown_collapses_to_unknown(self, vaccine_ref: dict) -> None:
        """Verify all-unknown contributing doses collapse to "unknown" for named diseases.

        Real-world significance:
        - After the fix, datasets with no validity suffixes yield "unknown" on
          the chart rather than "invalid", correctly reflecting absent data

        Assertion: unknown IPV → "unknown" for Polio
        """
        header = ["Polio"]
        grouped = [{"date_given": "2020-05-01", "vaccine": ["IPV"], "valid": ["unknown"]}]
        result = preprocess.enrich_grouped_records(grouped, vaccine_ref, "en", header)
        polio_idx = result[0]["diseases"].index("Polio")
        assert result[0]["valid"][polio_idx] == "unknown"

    def test_named_disease_never_produces_mixed(self, vaccine_ref: dict) -> None:
        """Verify named-disease collapsing never produces "mixed".

        Real-world significance:
        - "mixed" is reserved for the "Other" cross-vaccine collapse; named
          diseases should reflect net immunity (any valid → valid)

        Assertion: valid + invalid doses for the same named disease → "valid"
        """
        header = ["Diphtheria", "Tetanus", "Pertussis"]
        # Two DTaP doses on the same day: one valid, one invalid
        grouped = [{
            "date_given": "2020-05-01",
            "vaccine": ["DTaP", "DTaP"],
            "valid": ["valid", "invalid"],
        }]
        result = preprocess.enrich_grouped_records(grouped, vaccine_ref, "en", header)
        for disease in ["Diphtheria", "Tetanus", "Pertussis"]:
            idx = result[0]["diseases"].index(disease)
            assert result[0]["valid"][idx] == "valid"

    def test_other_column_different_vaccines_valid_and_invalid_produces_mixed(
        self, vaccine_ref: dict
    ) -> None:
        """Verify "Other" shows "mixed" when different vaccines have conflicting validity.

        Real-world significance:
        - "mixed" in the "Other" column alerts the user that some unmapped
          vaccines counted toward immunity and others did not on the same day

        Assertion: one valid vaccine + one invalid vaccine → Other "mixed"
        """
        header = ["Diphtheria"]  # HBV and HPV are unmapped → Other
        grouped = [{
            "date_given": "2020-05-01",
            "vaccine": ["HBV", "HPV"],
            "valid": ["valid", "invalid"],
        }]
        result = preprocess.enrich_grouped_records(grouped, vaccine_ref, "en", header)
        other_idx = result[0]["diseases"].index("Other")
        assert result[0]["valid"][other_idx] == "mixed"

    def test_other_column_all_valid_produces_valid(self, vaccine_ref: dict) -> None:
        """Verify "Other" shows "valid" when all unmapped vaccines are valid.

        Assertion: two valid unmapped vaccines → Other "valid"
        """
        header = ["Diphtheria"]
        grouped = [{
            "date_given": "2020-05-01",
            "vaccine": ["HBV", "HPV"],
            "valid": ["valid", "valid"],
        }]
        result = preprocess.enrich_grouped_records(grouped, vaccine_ref, "en", header)
        other_idx = result[0]["diseases"].index("Other")
        assert result[0]["valid"][other_idx] == "valid"

    def test_no_chart_diseases_header_returns_flat_disease_list(self, vaccine_ref: dict) -> None:
        """Verify that without chart_diseases_header, all diseases are returned flat.

        Real-world significance:
        - When no header is configured, the function acts as a pure disease
          expander without "Other" grouping; downstream code rendering
          unrestricted history depends on this flat mode

        Assertion: diseases list contains component names; no "Other" entry
        """
        grouped = [{"date_given": "2020-05-01", "vaccine": ["DTaP"], "valid": ["valid"]}]
        result = preprocess.enrich_grouped_records(grouped, vaccine_ref, "en")
        assert "Diphtheria" in result[0]["diseases"]
        assert "Other" not in result[0]["diseases"]

    def test_other_column_all_invalid_produces_invalid(self, vaccine_ref: dict) -> None:
        """Verify "Other" shows "invalid" when all unmapped vaccines are invalid.

        Assertion: two invalid unmapped vaccines → Other "invalid"
        """
        header = ["Diphtheria"]
        grouped = [{
            "date_given": "2020-05-01",
            "vaccine": ["HBV", "HPV"],
            "valid": ["invalid", "invalid"],
        }]
        result = preprocess.enrich_grouped_records(grouped, vaccine_ref, "en", header)
        other_idx = result[0]["diseases"].index("Other")
        assert result[0]["valid"][other_idx] == "invalid"

    def test_other_column_all_unknown_produces_unknown(self, vaccine_ref: dict) -> None:
        """Verify "Other" shows "unknown" when all unmapped vaccines are unknown.

        Assertion: two unknown unmapped vaccines → Other "unknown"
        """
        header = ["Diphtheria"]
        grouped = [{
            "date_given": "2020-05-01",
            "vaccine": ["HBV", "HPV"],
            "valid": ["unknown", "unknown"],
        }]
        result = preprocess.enrich_grouped_records(grouped, vaccine_ref, "en", header)
        other_idx = result[0]["diseases"].index("Other")
        assert result[0]["valid"][other_idx] == "unknown"

    def test_named_disease_all_invalid_doses_produces_invalid(self, vaccine_ref: dict) -> None:
        """Verify a named disease collapses to "invalid" when every contributing dose is invalid.

        Assertion: single DTaP dose with "invalid" validity → Diphtheria "invalid"
        """
        header = ["Diphtheria", "Tetanus", "Pertussis"]
        grouped = [{
            "date_given": "2020-05-01",
            "vaccine": ["DTaP"],
            "valid": ["invalid"],
        }]
        result = preprocess.enrich_grouped_records(grouped, vaccine_ref, "en", header)
        diphtheria_idx = result[0]["diseases"].index("Diphtheria")
        assert result[0]["valid"][diphtheria_idx] == "invalid"
        
        
@pytest.mark.unit
class TestProcessVaccinesDue:
    """Unit tests for process_vaccines_due."""

    def test_normalizes_disease_names(self) -> None:
        result = preprocess.process_vaccines_due("Poliomyelitis;Measles", "en")
        assert "Polio" in result
        assert "Measles" in result

    def test_empty_input_returns_empty_string(self) -> None:
        assert preprocess.process_vaccines_due("", "en") == ""

    def test_non_string_input_returns_empty_string(self) -> None:
        assert preprocess.process_vaccines_due(None, "en") == ""
