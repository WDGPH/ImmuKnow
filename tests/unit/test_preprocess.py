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


def _make_conforming_df(**overrides) -> pd.DataFrame:
    """Build a minimal DataFrame with all required input columns."""
    row = {
        "School Type": ["Public"],
        "School Name": ["Test School"],
        "Client Id": ["C001"],
        "First Name": ["Alice"],
        "Last Name": ["Zephyr"],
        "Age": ["10"],
        "Date of Birth": ["2015-01-01"],
        "Street Address Line 1": ["123 Main St"],
        "Street Address Line 2": [""],
        "City": ["Guelph"],
        "Province/Territory": ["ON"],
        "Postal Code": ["N1H 2T2"],
        "Overdue Disease": ["Measles"],
        "Overdue Agent": ["MMR"],
        "Imms Given": [""],
        "Birth Year": ["2015"],
    }
    row.update(overrides)
    return pd.DataFrame(row)


@pytest.mark.unit
class TestMapColumns:
    """Unit tests for map_columns() strict column mapping."""

    def test_renames_required_columns_to_internal_keys(self):
        df = _make_conforming_df()
        result = preprocess.map_columns(df)
        assert set(preprocess.REQUIRED_COLUMN_MAP.values()).issubset(set(result.columns))

    def test_province_territory_maps_to_province(self):
        df = _make_conforming_df()
        result = preprocess.map_columns(df)
        assert "PROVINCE" in result.columns
        assert "Province/Territory" not in result.columns

    def test_drops_unknown_columns(self):
        df = _make_conforming_df()
        df["Extra Column"] = ["surprise"]
        result = preprocess.map_columns(df)
        assert "Extra Column" not in result.columns
        assert "EXTRA_COLUMN" not in result.columns

    def test_includes_optional_column_when_present(self):
        df = _make_conforming_df()
        df["Board Name"] = ["District Board"]
        result = preprocess.map_columns(df)
        assert "BOARD_NAME" in result.columns

    def test_omits_optional_column_when_absent(self):
        df = _make_conforming_df()
        result = preprocess.map_columns(df)
        assert "BOARD_NAME" not in result.columns

    def test_raises_on_missing_required_column(self):
        df = _make_conforming_df()
        df = df.drop(columns=["School Name"])
        with pytest.raises(ValueError, match="missing required columns"):
            preprocess.map_columns(df)

    def test_raises_listing_all_missing_columns(self):
        df = _make_conforming_df()
        df = df.drop(columns=["School Name", "First Name"])
        with pytest.raises(ValueError, match="missing required columns"):
            preprocess.map_columns(df)


@pytest.mark.unit
class TestFormatVaccineDueList:
    """Unit tests for overdue-vaccine dose formatting."""

    def test_empty_dose_suffix_displays_only_disease(self) -> None:
        """Verify an empty dose suffix displays only the disease name.

        Real-world significance:
        - Source exports can contain a separator without a dose number
        - One malformed entry must not stop preprocessing for every client

        Assertion: Blank and whitespace-only suffixes are removed from display
        """
        result = preprocess.format_vaccine_due_list(["Polio - ", "MMR -    "])

        assert result == ["Polio", "MMR"]

    def test_empty_suffix_preserves_later_invalid_dose_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Verify an empty suffix does not suppress later invalid-dose logging.

        Real-world significance:
        - A malformed entry can appear before other invalid values in one export
        - Existing warnings for out-of-range dose numbers must remain available

        Assertion: The empty suffix is hidden and the later warning is emitted
        """
        result = preprocess.format_vaccine_due_list(["Polio - ", "MMR - 10"])

        assert result == ["Polio", "MMR - 10"]
        assert "invalid dose number: MMR - 10" in caplog.text

    def test_requires_dose_bearing_schema(self) -> None:
        """Reject dose display when the input has no dose-bearing schema.

        Real-world significance:
        - Enabling dose display promises recipients a specific overdue dose
        - Ordinary disease-only input cannot fulfill that configuration

        Assertion: Formatting a disease-only entry raises a configuration error
        """
        with pytest.raises(ValueError, match="include_dose requires overdue entries"):
            preprocess.format_vaccine_due_list(["Polio"])

    def test_hides_supplied_doses_and_preserves_ordinary_entries(self) -> None:
        """Hide dose fields while preserving ordinary overdue entries.

        Real-world significance:
        - Sites that disable dose display may use either supported input schema
        - Recipients should see the same disease list without supplied dose numbers

        Assertion: Dose fields are removed and disease-only entries are unchanged
        """
        result = preprocess.hide_vaccine_due_doses(["Polio - 2", "MMR"])

        assert result == ["Polio", "MMR"]



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
        assert "School Name" in df_read.columns

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
        """Verify valid DataFrame passes normalization without errors."""
        df = preprocess.map_columns(sample_input.create_test_input_dataframe(num_clients=3))

        result = preprocess.normalize_dataframe(df)

        assert result is not None
        assert len(result) == 3

    def test_normalize_dataframe_handles_missing_values(self) -> None:
        """Verify NaN/None values in string columns are filled."""
        df = preprocess.map_columns(sample_input.create_test_input_dataframe(num_clients=3))
        df.loc[0, "STREET_ADDRESS_LINE_2"] = None
        df.loc[1, "POSTAL_CODE"] = float("nan")

        result = preprocess.normalize_dataframe(df)

        assert result["STREET_ADDRESS_LINE_2"].iloc[0] == ""
        assert result["POSTAL_CODE"].iloc[1] == ""

    def test_normalize_dataframe_converts_dates(self) -> None:
        """Verify DATE_OF_BIRTH is parsed to datetime."""
        df = preprocess.map_columns(sample_input.create_test_input_dataframe(num_clients=2))
        df["DATE_OF_BIRTH"] = ["2015-01-02", "2014-05-06"]

        result = preprocess.normalize_dataframe(df)

        assert pd.api.types.is_datetime64_any_dtype(result["DATE_OF_BIRTH"])

    def test_normalize_dataframe_trims_whitespace(self) -> None:
        """Verify string columns have leading/trailing whitespace stripped."""
        df = preprocess.map_columns(sample_input.create_test_input_dataframe(num_clients=1))
        df["FIRST_NAME"] = ["  Alice  "]
        df["LAST_NAME"] = ["  Zephyr  "]

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
        df = preprocess.map_columns(sample_input.create_test_input_dataframe(num_clients=3))

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
        df = preprocess.map_columns(sample_input.create_test_input_dataframe(num_clients=3))

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
        df = preprocess.map_columns(pd.DataFrame(
            {
                "School Type": ["Public", "Public", "Public", "Public"],
                "School Name": ["Zebra School", "Zebra School", "Apple School", "Apple School"],
                "Client Id": ["C002", "C001", "C004", "C003"],
                "First Name": ["Bob", "Alice", "Diana", "Chloe"],
                "Last Name": ["Smith", "Smith", "Jones", "Jones"],
                "Age": ["10", "10", "10", "10"],
                "Date of Birth": ["2015-01-01", "2015-01-02", "2015-01-03", "2015-01-04"],
                "Street Address Line 1": ["123 Main", "123 Main", "123 Main", "123 Main"],
                "Street Address Line 2": ["", "", "", ""],
                "City": ["Town", "Town", "Town", "Town"],
                "Province/Territory": ["ON", "ON", "ON", "ON"],
                "Postal Code": ["N1H 2T2", "N1H 2T2", "N1H 2T2", "N1H 2T2"],
                "Overdue Disease": ["Measles", "Measles", "Measles", "Measles"],
                "Overdue Agent": ["MMR", "MMR", "MMR", "MMR"],
                "Imms Given": ["", "", "", ""],
                "Birth Year": ["2015", "2015", "2015", "2015"],
            }
        ))
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
        df = preprocess.map_columns(sample_input.create_test_input_dataframe(num_clients=1))
        df["IMMS_GIVEN"] = ["May 1, 2020 - DTaP"]

        result = preprocess.build_preprocess_result(
            df,
            language="en",
            vaccine_reference=default_vaccine_reference,
            replace_unspecified=[],
        )

        # Should have DTaP expanded to component diseases in columns dict
        assert len(result.clients) == 1
        client = result.clients[0]
        assert client.received is not None
        assert len(client.received) > 0
        columns = client.received[0].get("columns")
        assert isinstance(columns, dict) and "Diphtheria" in columns

    def test_build_result_uses_explicit_config_path(
        self, tmp_path: Path, default_vaccine_reference
    ) -> None:
        """Verify an explicit config controls dose display and validity markers.

        Real-world significance:
        - A selected site configuration must override repository defaults
        - Disabling dose display must remove supplied dose numbers from notices

        Assertion: The dose is hidden and the selected marker warning is emitted
        """
        config_path = tmp_path / "parameters.yaml"
        config_path.write_text(
            "\n".join(
                [
                    "preprocess:",
                    "  include_dose: false",
                    "  show_validity_markers: true",
                ]
            ),
            encoding="utf-8",
        )
        df = preprocess.map_columns(sample_input.create_test_input_dataframe(num_clients=1))
        df["OVERDUE_DISEASE"] = ["DTaP - 2"]
        df["IMMS_GIVEN"] = ["May 1, 2020 - DTaP"]

        result = preprocess.build_preprocess_result(
            df,
            language="en",
            vaccine_reference=default_vaccine_reference,
            replace_unspecified=[],
            config_path=config_path,
        )

        assert result.clients[0].vaccines_due_list == ["DTaP"]
        assert any(
            "no validity data was detected in the dataset" in warning
            for warning in result.warnings
        )

    def test_build_result_handles_missing_board_name_with_warning(
        self, default_vaccine_reference
    ) -> None:
        """Verify missing board name generates warning.

        Real-world significance:
        - Some school districts don't have explicit board assignments
        - Should auto-generate board ID and log warning
        - Allows pipeline to proceed without failing
        """
        df = preprocess.map_columns(pd.DataFrame(
            {
                "School Type": ["Public"],
                "School Name": ["Test School"],
                "Client Id": ["C001"],
                "First Name": ["Alice"],
                "Last Name": ["Zephyr"],
                "Age": ["10"],
                "Date of Birth": ["2015-01-01"],
                "Street Address Line 1": ["123 Main"],
                "Street Address Line 2": [""],
                "City": ["Guelph"],
                "Province/Territory": ["ON"],
                "Postal Code": ["N1H 2T2"],
                "Overdue Disease": ["Measles"],
                "Overdue Agent": ["MMR"],
                "Imms Given": [""],
                "Birth Year": ["2015"],
            }
        ))
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
        df = preprocess.map_columns(sample_input.create_test_input_dataframe(num_clients=1, language="fr"))

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
        df = preprocess.map_columns(sample_input.create_test_input_dataframe(num_clients=1))

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
        df = preprocess.map_columns(sample_input.create_test_input_dataframe(num_clients=2))
        # Force duplicate client IDs
        df.loc[0, "CLIENT_ID"] = "C123456789"
        df.loc[1, "CLIENT_ID"] = "C123456789"

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
        df = preprocess.map_columns(sample_input.create_test_input_dataframe(num_clients=5))
        # Create two sets of duplicates
        df.loc[0, "CLIENT_ID"] = "C111111111"
        df.loc[1, "CLIENT_ID"] = "C111111111"
        df.loc[2, "CLIENT_ID"] = "C111111111"
        df.loc[3, "CLIENT_ID"] = "C222222222"
        df.loc[4, "CLIENT_ID"] = "C222222222"

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
        df = preprocess.map_columns(sample_input.create_test_input_dataframe(num_clients=3))

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

    @pytest.mark.parametrize("suffix", ["valid", "invalid"])
    def test_lowercase_validity_suffix_returns_all_present(self, suffix: str) -> None:
        """Verify each supported lowercase suffix is recognized as present.

        Real-world significance:
        - Source exports may use lowercase validity markers; misclassifying
          them as absent can incorrectly reject a consistently marked dataset

        Assertion: Each lowercase suffix classifies the dataset as all_present
        """
        series = pd.Series([f"May 1, 2020 - DTaP - {suffix}"])
        assert preprocess.classify_dataset_validity(series) == "all_present"

    @pytest.mark.parametrize("suffix", ["VALID", "INVALID", "vAlid", "iNvalid"])
    def test_unsupported_validity_casing_returns_all_absent(self, suffix: str) -> None:
        """Verify unsupported casing is not recognized as a validity suffix.

        Real-world significance:
        - Unapproved casing must not silently influence validity markers on
          notices because its meaning has not met the source-data contract

        Assertion: Each unsupported suffix classifies the dataset as all_absent
        """
        series = pd.Series([f"May 1, 2020 - DTaP - {suffix}"])
        assert preprocess.classify_dataset_validity(series) == "all_absent"

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
class TestParseDoseSegments:
    """Unit tests for parse_dose_segments() parsing contract.

    Covers:
    - Empty / non-string inputs → empty list
    - Doses with - Valid / - Invalid suffix → correct status
    - Doses without suffix → "unknown" (not silently dropped)
    - Multiple doses on the same date returned as separate flat entries
    - Entries sorted ascending by date regardless of input order
    - replace_unspecified filtering

    Real-world significance:
    - This function is the sole parser for IMMS_GIVEN strings; incorrect
      parsing silently omits or misrepresents a patient's immunization
      history on their printed notice.
    """

    def test_empty_string_returns_empty_list(self) -> None:
        """Assertion: "" → []"""
        assert preprocess.parse_dose_segments("", []) == []

    def test_non_string_input_returns_empty_list(self) -> None:
        """Assertion: None → []"""
        assert preprocess.parse_dose_segments(None, []) == []

    def test_dose_with_valid_suffix_parsed_correctly(self) -> None:
        """Verify date, vaccine name, and validity are all parsed correctly."""
        result = preprocess.parse_dose_segments("May 1, 2020 - DTaP - Valid", [])
        assert len(result) == 1
        assert result[0]["date_given"] == "2020-05-01"
        assert result[0]["vaccine"] == "DTaP"
        assert result[0]["validity"] == "valid"

    def test_dose_with_invalid_suffix_parsed_correctly(self) -> None:
        """Assertion: - Invalid suffix → validity == "invalid"."""
        result = preprocess.parse_dose_segments("May 1, 2020 - DTaP - Invalid", [])
        assert result[0]["validity"] == "invalid"

    @pytest.mark.parametrize(
        ("suffix", "expected_status"),
        [("valid", "valid"), ("invalid", "invalid")],
    )
    def test_lowercase_validity_suffix_parsed_correctly(
        self, suffix: str, expected_status: str
    ) -> None:
        """Verify lowercase suffixes are removed and normalized when parsed.

        Real-world significance:
        - Lowercase validity markers must control the notice marker instead of
          becoming part of the displayed vaccine name

        Assertion: Vaccine is DTaP and validity matches the lowercase suffix
        """
        result = preprocess.parse_dose_segments(f"May 1, 2020 - DTaP - {suffix}", [])
        assert result[0]["vaccine"] == "DTaP"
        assert result[0]["validity"] == expected_status

    @pytest.mark.parametrize("suffix", ["VALID", "INVALID", "vAlid", "iNvalid"])
    def test_unsupported_validity_casing_remains_in_vaccine_name(
        self, suffix: str
    ) -> None:
        """Verify unsupported casing remains vaccine text with unknown validity.

        Real-world significance:
        - Unapproved casing must remain untrusted so a dose is not incorrectly
          shown as counting or not counting toward immunity

        Assertion: Suffix remains vaccine text and validity is unknown
        """
        result = preprocess.parse_dose_segments(f"May 1, 2020 - DTaP - {suffix}", [])
        assert result[0]["vaccine"] == f"DTaP - {suffix}"
        assert result[0]["validity"] == "unknown"

    def test_dose_without_suffix_yields_unknown_not_dropped(self) -> None:
        """Verify a dose lacking a suffix is captured as "unknown", not dropped.

        Real-world significance:
        - Legacy datasets or incomplete exports omit validity suffixes;
          they must appear on the notice with unknown status.
        """
        result = preprocess.parse_dose_segments("May 1, 2020 - DTaP", [])
        assert len(result) == 1
        assert result[0]["validity"] == "unknown"

    def test_same_date_doses_remain_separate_flat_entries(self) -> None:
        """Verify two doses on the same date produce two flat entries (no grouping here)."""
        result = preprocess.parse_dose_segments(
            "May 1, 2020 - DTaP; May 1, 2020 - MMR", []
        )
        assert len(result) == 2
        vaccines = {r["vaccine"] for r in result}
        assert vaccines == {"DTaP", "MMR"}

    def test_different_dates_produce_separate_entries(self) -> None:
        """Assertion: two segments with different dates → two entries."""
        result = preprocess.parse_dose_segments(
            "May 1, 2020 - DTaP; Jun 15, 2021 - MMR", []
        )
        assert len(result) == 2

    def test_entries_sorted_ascending_by_date(self) -> None:
        """Verify records are sorted by date regardless of input order.

        Real-world significance:
        - Immunization history is displayed chronologically on notices.
        """
        result = preprocess.parse_dose_segments(
            "Jun 15, 2021 - MMR; May 1, 2020 - DTaP", []
        )
        assert result[0]["date_given"] == "2020-05-01"
        assert result[1]["date_given"] == "2021-06-15"

    def test_replace_unspecified_filters_named_vaccines(self) -> None:
        """Verify vaccines in replace_unspecified are excluded from output."""
        result = preprocess.parse_dose_segments(
            "May 1, 2020 - Not Specified; Jun 15, 2021 - MMR",
            ["Not Specified"],
        )
        assert len(result) == 1
        assert result[0]["vaccine"] == "MMR"


@pytest.mark.unit
class TestBuildReceivedRows:
    """Unit tests for build_received_rows() end-to-end row construction.

    Covers:
    - Basic single-date, single-vaccine case
    - Same-vaccine deduplication: unknown > valid > invalid
    - Column status computation (valid, invalid, unknown, mixed)
    - Row splitting when a column is mixed
    - date_rowspan values: N on first row, 0 on continuations
    - Recursive splitting terminates cleanly
    - "Other" column produced for unmapped diseases

    Real-world significance:
    - build_received_rows is the sole source of the ``received`` field
      on ClientRecord; every immunization row and validity marker on a
      printed notice derives from this output.
    """

    @pytest.fixture
    def vaccine_ref(self) -> dict:
        return {
            "DTaP": ["Diphtheria", "Tetanus", "Pertussis"],
            "MMR": ["Measles", "Mumps", "Rubella"],
            "IPV": ["Polio"],
            "HBV": ["Hepatitis B"],
            "HPV": ["Human Papillomavirus"],
        }

    @pytest.fixture
    def header(self) -> list:
        return ["Diphtheria", "Tetanus", "Pertussis", "Polio", "Measles", "Other"]

    def test_single_vaccine_single_date(self, vaccine_ref, header) -> None:
        """One vaccine, one date → one row with correct column status."""
        rows = preprocess.build_received_rows(
            "May 1, 2020 - DTaP - Valid", [], vaccine_ref, header
        )
        assert len(rows) == 1
        assert rows[0]["date_given"] == "2020-05-01"
        assert rows[0]["date_rowspan"] == 1
        assert rows[0]["columns"]["Diphtheria"] == "valid"
        assert rows[0]["columns"]["Tetanus"] == "valid"
        assert rows[0]["columns"]["Pertussis"] == "valid"
        assert "vaccines" in rows[0]
        assert "DTaP" in rows[0]["vaccines"]

    def test_two_dates_two_rows_no_split(self, vaccine_ref, header) -> None:
        """Two distinct dates each produce one row; date_rowspan == 1 on both."""
        rows = preprocess.build_received_rows(
            "May 1, 2020 - DTaP - Valid; Jun 15, 2021 - IPV - Invalid",
            [], vaccine_ref, header,
        )
        assert len(rows) == 2
        assert all(r["date_rowspan"] == 1 for r in rows)
        assert rows[0]["columns"]["Diphtheria"] == "valid"
        assert rows[1]["columns"]["Polio"] == "invalid"

    def test_same_vaccine_deduplication_unknown_wins(self, vaccine_ref, header) -> None:
        """Two doses of same vaccine: unknown + valid → unknown (data quality signal)."""
        rows = preprocess.build_received_rows(
            "May 1, 2020 - DTaP; May 1, 2020 - DTaP - Valid",
            [], vaccine_ref, header,
        )
        assert len(rows) == 1
        assert rows[0]["columns"]["Diphtheria"] == "unknown"

    def test_same_vaccine_deduplication_valid_over_invalid(self, vaccine_ref, header) -> None:
        """Two doses of same vaccine: valid + invalid → valid."""
        rows = preprocess.build_received_rows(
            "May 1, 2020 - DTaP - Valid; May 1, 2020 - DTaP - Invalid",
            [], vaccine_ref, header,
        )
        assert len(rows) == 1
        assert rows[0]["columns"]["Diphtheria"] == "valid"

    def test_same_vaccine_deduplication_all_invalid(self, vaccine_ref, header) -> None:
        """Two doses of same vaccine: invalid + invalid → invalid."""
        rows = preprocess.build_received_rows(
            "May 1, 2020 - DTaP - Invalid; May 1, 2020 - DTaP - Invalid",
            [], vaccine_ref, header,
        )
        assert len(rows) == 1
        assert rows[0]["columns"]["Diphtheria"] == "invalid"

    def test_two_vaccines_same_date_no_mixed_column(self, vaccine_ref, header) -> None:
        """Two vaccines, same date, same validity → single row, no split."""
        rows = preprocess.build_received_rows(
            "May 1, 2020 - DTaP - Valid; May 1, 2020 - IPV - Valid",
            [], vaccine_ref, header,
        )
        assert len(rows) == 1
        assert rows[0]["date_rowspan"] == 1
        assert rows[0]["columns"]["Diphtheria"] == "valid"
        assert rows[0]["columns"]["Polio"] == "valid"

    def test_mixed_column_triggers_split_into_two_rows(self, vaccine_ref, header) -> None:
        """DTaP(valid) + IPV(invalid) on same date → Diphtheria=valid, Polio=invalid,
        no mixed → single row (different columns, not same column)."""
        rows = preprocess.build_received_rows(
            "May 1, 2020 - DTaP - Valid; May 1, 2020 - IPV - Invalid",
            [], vaccine_ref, header,
        )
        # DTaP and IPV map to different columns — no mixed, one row
        assert len(rows) == 1
        assert rows[0]["columns"]["Diphtheria"] == "valid"
        assert rows[0]["columns"]["Polio"] == "invalid"

    def test_two_vaccines_sharing_disease_column_produces_mixed(self) -> None:
        """Two different vaccines both mapping to same disease with conflicting validity
        → that column is mixed → split into two rows."""
        ref = {
            "VaxA": ["Diphtheria"],
            "VaxB": ["Diphtheria"],
        }
        header = ["Diphtheria", "Other"]
        rows = preprocess.build_received_rows(
            "May 1, 2020 - VaxA - Valid; May 1, 2020 - VaxB - Invalid",
            [], ref, header, show_validity_markers=True,
        )
        assert len(rows) == 2
        assert rows[0]["date_rowspan"] == 2
        assert rows[1]["date_rowspan"] == 0
        # Row 1: valid vaccine only
        assert rows[0]["columns"]["Diphtheria"] == "valid"
        # Row 2: invalid vaccine only
        assert rows[1]["columns"]["Diphtheria"] == "invalid"

    def test_date_rowspan_on_continuation_rows_is_zero(self) -> None:
        """Continuation rows for a split date must have date_rowspan == 0."""
        ref = {"VaxA": ["Diphtheria"], "VaxB": ["Diphtheria"]}
        header = ["Diphtheria", "Other"]
        rows = preprocess.build_received_rows(
            "May 1, 2020 - VaxA - Valid; May 1, 2020 - VaxB - Invalid",
            [], ref, header, show_validity_markers=True,
        )
        assert rows[1]["date_rowspan"] == 0

    def test_other_column_mixed_triggers_split(self, vaccine_ref, header) -> None:
        """HBV(valid) + HPV(invalid) both map to Other → Other is mixed → split."""
        rows = preprocess.build_received_rows(
            "May 1, 2020 - HBV - Valid; May 1, 2020 - HPV - Invalid",
            [], vaccine_ref, header, show_validity_markers=True,
        )
        assert len(rows) == 2
        assert rows[0]["columns"].get("Other") == "valid"
        assert rows[1]["columns"].get("Other") == "invalid"

    def test_other_column_all_valid(self, vaccine_ref, header) -> None:
        """HBV(valid) + HPV(valid) → Other == valid, single row."""
        rows = preprocess.build_received_rows(
            "May 1, 2020 - HBV - Valid; May 1, 2020 - HPV - Valid",
            [], vaccine_ref, header,
        )
        assert len(rows) == 1
        assert rows[0]["columns"].get("Other") == "valid"

    def test_unknown_and_valid_in_same_column_is_unknown(self) -> None:
        """VaxA(valid) + VaxB(unknown) for same disease → unknown (not mixed)."""
        ref = {"VaxA": ["Diphtheria"], "VaxB": ["Diphtheria"]}
        header = ["Diphtheria", "Other"]
        rows = preprocess.build_received_rows(
            "May 1, 2020 - VaxA - Valid; May 1, 2020 - VaxB",
            [], ref, header,
        )
        assert len(rows) == 1
        assert rows[0]["columns"]["Diphtheria"] == "unknown"

    def test_empty_input_returns_empty_list(self, vaccine_ref, header) -> None:
        """Assertion: empty string → []"""
        assert preprocess.build_received_rows("", [], vaccine_ref, header) == []

    def test_replace_unspecified_filters_vaccine(self, vaccine_ref, header) -> None:
        """Filtered vaccine absent from output; remaining vaccine present."""
        rows = preprocess.build_received_rows(
            "May 1, 2020 - Not Specified; May 1, 2020 - DTaP - Valid",
            ["Not Specified"], vaccine_ref, header,
        )
        assert len(rows) == 1
        assert "DTaP" in rows[0]["vaccines"]
        assert "Not Specified" not in rows[0]["vaccines"]

    def test_build_result_maps_vaccines_correctly(self, default_vaccine_reference) -> None:
        """Verify vaccine codes expand to component diseases in columns dict.

        Real-world significance:
        - DTaP → Diphtheria, Tetanus, Pertussis columns populated.
        """
        df = preprocess.map_columns(sample_input.create_test_input_dataframe(num_clients=1))
        df["IMMS_GIVEN"] = ["May 1, 2020 - DTaP"]

        result = preprocess.build_preprocess_result(
            df,
            language="en",
            vaccine_reference=default_vaccine_reference,
            replace_unspecified=[],
        )

        client = result.clients[0]
        assert client.received is not None
        assert len(client.received) > 0
        columns = client.received[0].get("columns")
        assert isinstance(columns, dict) and "Diphtheria" in columns
        
        
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
