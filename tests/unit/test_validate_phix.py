"""Unit tests for validate_phix module - PHIX school name validation.

Tests cover:
- School name normalisation (uppercase, whitespace)
- Input entry parsing (name / ID splitting)
- Match classification (exact, inexact variants, no_match)
- Mapping file loading (valid, missing file, missing PHU)
- CSV audit file writing
- Full validate_schools pipeline (column enrichment, warn/error/skip behaviours)
- run_phix_validation integration with preprocess config

Real-world significance:
- Validates school names in Step 2 against the PHIX reference before notices are generated
- Unmatched schools surface data-quality issues before notices reach families
- Classification drives audit CSVs used by public-health staff for follow-up
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from immuknow import preprocess
from immuknow import validate_phix


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

MINIMAL_MAPPING = {
    "phus": {
        "Test PHU": {
            "SPRINGFIELD ELEMENTARY": "001",
            "SHELBYVILLE MIDDLE": "002",
        },
        "Other PHU": {
            "OTHER SCHOOL": "099",
        },
    }
}


@pytest.fixture
def mapping_file(tmp_path: Path) -> Path:
    """Write a minimal phix_mapping.json and return its path.

    Keeps tests isolated from the real config/phix_mapping.json.
    """
    p = tmp_path / "phix_mapping.json"
    p.write_text(json.dumps(MINIMAL_MAPPING), encoding="utf-8")
    return p


@pytest.fixture
def phix_config_yaml(tmp_path: Path, mapping_file: Path) -> Path:
    """Write a parameters.yaml with phix_validation enabled and return its path.

    Used by run_phix_validation tests that monkeypatch PARAMETERS_PATH.
    """
    config = {
        "phix_validation": {
            "enabled": True,
            "mapping_file": str(mapping_file),
            "target_phu": "Test PHU",
            "unmatched_behavior": "warn",
            "column_prefix": "phix_",
        }
    }
    p = tmp_path / "parameters.yaml"
    p.write_text(yaml.dump(config), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# normalize_school_name
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestNormalizeSchoolName:
    """Unit tests for normalize_school_name."""

    def test_uppercases_input(self):
        """Lowercase input is uppercased.

        Real-world significance:
        - Mapping keys are stored uppercase; input may arrive in any case.
        - Normalisation must match build_phix_mapping.py output exactly.

        Assertion: result is fully uppercased.
        """
        assert (
            validate_phix.normalize_school_name("Springfield Elementary")
            == "SPRINGFIELD ELEMENTARY"
        )

    def test_collapses_internal_whitespace(self):
        """Multiple spaces between words are collapsed to one.

        Real-world significance:
        - Input spreadsheets frequently contain extra spaces from copy-paste.
        - Whitespace inconsistency would cause false no_match results.

        Assertion: interior whitespace reduced to single space.
        """
        assert (
            validate_phix.normalize_school_name("SPRING  FIELD   SCHOOL")
            == "SPRING FIELD SCHOOL"
        )

    def test_strips_leading_trailing_whitespace(self):
        """Leading/trailing whitespace is removed.

        Assertion: result has no leading or trailing spaces.
        """
        assert validate_phix.normalize_school_name("  SCHOOL NAME  ") == "SCHOOL NAME"

    def test_empty_string_returns_empty(self):
        """Empty string input returns empty string without error.

        Assertion: empty string in → empty string out.
        """
        assert validate_phix.normalize_school_name("") == ""


# ---------------------------------------------------------------------------
# parse_input_entry
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestParseInputEntry:
    """Unit tests for parse_input_entry."""

    def test_no_separator_returns_full_string_and_empty_id(self):
        """Input without ' - ' separator is returned as-is with empty ID.

        Real-world significance:
        - Most entries are plain school names with no facility ID appended.

        Assertion: (original_string, "") returned.
        """
        name, fid = validate_phix.parse_input_entry("Springfield Elementary")
        assert name == "Springfield Elementary"
        assert fid == ""

    def test_splits_on_rightmost_separator(self):
        """Name and facility ID are split on the rightmost ' - '.

        Real-world significance:
        - School names may contain dashes (e.g. 'St. Jean-Baptiste'); only the
          trailing ' - <ID>' suffix should be stripped.

        Assertion: ID is the portion after the last ' - '; name retains interior dashes.
        """
        name, fid = validate_phix.parse_input_entry(
            "St. Jean-Baptiste Elementary - 019186"
        )
        assert name == "St. Jean-Baptiste Elementary"
        assert fid == "019186"

    def test_simple_name_id_split(self):
        """Standard 'NAME - ID' format is split correctly.

        Assertion: name and ID extracted without extra whitespace.
        """
        name, fid = validate_phix.parse_input_entry("Springfield Elementary - 001")
        assert name == "Springfield Elementary"
        assert fid == "001"

    def test_strips_whitespace_from_parts(self):
        """Whitespace around the separator is trimmed from both parts.

        Assertion: name and ID have no leading/trailing spaces.
        """
        name, fid = validate_phix.parse_input_entry("  Some School  -  042  ")
        assert name == "Some School"
        assert fid == "042"


# ---------------------------------------------------------------------------
# classify_match
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestClassifyMatch:
    """Unit tests for classify_match - all five result branches."""

    @pytest.fixture
    def mapping(self):
        name_to_id = {"SPRINGFIELD ELEMENTARY": "001", "SHELBYVILLE MIDDLE": "002"}
        id_to_name = {v: k for k, v in name_to_id.items()}
        return name_to_id, id_to_name

    def test_exact_match_when_name_and_id_both_match(self, mapping):
        """Name found in mapping and provided ID matches stored ID → exact.

        Real-world significance:
        - Exact matches require no manual review; highest-confidence classification.

        Assertion: match_type='exact', no mismatch_reason.
        """
        name_to_id, id_to_name = mapping
        result = validate_phix.classify_match(
            "Springfield Elementary", "001", name_to_id, id_to_name
        )
        assert result.match_type == "exact"
        assert result.mismatch_reason is None
        assert result.matched_id == "001"

    def test_inexact_name_only_when_no_id_provided(self, mapping):
        """Name found in mapping but no facility ID in input → inexact/name_only.

        Real-world significance:
        - Common when source data lacks the PHIX ID column; staff can still
          confirm by name.

        Assertion: match_type='inexact', mismatch_reason='name_only'.
        """
        name_to_id, id_to_name = mapping
        result = validate_phix.classify_match(
            "Springfield Elementary", "", name_to_id, id_to_name
        )
        assert result.match_type == "inexact"
        assert result.mismatch_reason == "name_only"

    def test_inexact_id_mismatch_when_ids_differ(self, mapping):
        """Name found but input ID differs from mapping ID → inexact/id_mismatch.

        Real-world significance:
        - Indicates a data-entry error or a school that was reassigned a new ID;
          requires manual review.

        Assertion: match_type='inexact', mismatch_reason='id_mismatch'.
        """
        name_to_id, id_to_name = mapping
        result = validate_phix.classify_match(
            "Springfield Elementary", "999", name_to_id, id_to_name
        )
        assert result.match_type == "inexact"
        assert result.mismatch_reason == "id_mismatch"

    def test_inexact_id_only_when_id_found_under_different_name(self, mapping):
        """Name not found, but provided ID exists under a different name in the school mapping → inexact/id_only.

        Real-world significance:
        - The school may have been renamed; the ID is trustworthy but the name
          needs updating in the source system.

        Assertion: match_type='inexact', mismatch_reason='id_only', matched_name comes from the school mapping.
        """
        name_to_id, id_to_name = mapping
        result = validate_phix.classify_match(
            "Springfeld Elemntary", "001", name_to_id, id_to_name
        )
        assert result.match_type == "inexact"
        assert result.mismatch_reason == "id_only"
        assert result.matched_name == "SPRINGFIELD ELEMENTARY"

    def test_no_match_when_neither_name_nor_id_found(self, mapping):
        """Neither name nor ID found in mapping → no_match.

        Real-world significance:
        - Indicates a school that is not in the PHIX reference; requires
          investigation before notices can be confirmed.

        Assertion: match_type='no_match'.
        """
        name_to_id, id_to_name = mapping
        result = validate_phix.classify_match(
            "Unknown School", "999", name_to_id, id_to_name
        )
        assert result.match_type == "no_match"


# ---------------------------------------------------------------------------
# load_mapping
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadMapping:
    """Unit tests for load_mapping."""

    def test_returns_name_to_id_and_id_to_name_for_known_phu(self, mapping_file):
        """Valid mapping file and known PHU returns correct lookup dicts.

        Assertion: name_to_id and id_to_name populated from the target PHU only.
        """
        name_to_id, id_to_name = validate_phix.load_mapping(mapping_file, "Test PHU")
        assert name_to_id["SPRINGFIELD ELEMENTARY"] == "001"
        assert id_to_name["001"] == "SPRINGFIELD ELEMENTARY"
        assert "OTHER SCHOOL" not in name_to_id  # Other PHU not included

    def test_raises_file_not_found_when_mapping_missing(self, tmp_path):
        """FileNotFoundError raised when mapping file does not exist.

        Real-world significance:
        - Prevents silent failures if the mapping file was not generated or
          is mis-configured; pipeline should halt with a clear message.

        Assertion: FileNotFoundError raised.
        """
        with pytest.raises(FileNotFoundError, match="PHIX mapping file not found"):
            validate_phix.load_mapping(tmp_path / "nonexistent.json", "Test PHU")

    def test_raises_key_error_when_phu_not_in_mapping(self, mapping_file):
        """KeyError raised when target_phu is absent, listing available PHUs.

        Real-world significance:
        - Mis-spelled or hyphenation-incorrect PHU names are a common config
          mistake; the error message lists available PHUs to help the user fix it.

        Assertion: KeyError raised; available PHU names appear in message.
        """
        with pytest.raises(KeyError, match="Other PHU"):
            validate_phix.load_mapping(mapping_file, "Nonexistent PHU")


# ---------------------------------------------------------------------------
# _write_csv
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWriteCsv:
    """Unit tests for _write_csv."""

    def test_no_op_when_results_empty(self, tmp_path):
        """Empty results list does not create a file.

        Real-world significance:
        - A run with no inexact matches should not produce an empty phix_inexact.csv
          that could confuse downstream consumers.

        Assertion: output file not created.
        """
        out = tmp_path / "phix_exact.csv"
        validate_phix._write_csv([], out)
        assert not out.exists()

    def test_writes_csv_with_expected_columns(self, tmp_path):
        """Non-empty results list produces a CSV with correct columns.

        Assertion: file exists; columns match the defined schema.
        """
        result = validate_phix.PHIXMatchResult(
            input_name="Springfield Elementary",
            input_id="001",
            match_type="exact",
            matched_name="SPRINGFIELD ELEMENTARY",
            matched_id="001",
        )
        out = tmp_path / "phix_exact.csv"
        validate_phix._write_csv([result], out)

        assert out.exists()
        df = pd.read_csv(out)
        assert list(df.columns) == [
            "input_name",
            "input_id",
            "matched_name",
            "matched_id",
            "mismatch_reason",
        ]
        assert df.iloc[0]["input_name"] == "Springfield Elementary"


# ---------------------------------------------------------------------------
# validate_schools
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestValidateSchools:
    """Unit tests for validate_schools - the public entry point."""

    @pytest.fixture
    def base_df(self) -> pd.DataFrame:
        """Minimal DataFrame with a school_name column for validation tests."""
        return pd.DataFrame(
            {
                "school_name": [
                    "Springfield Elementary - 001",  # exact
                    "Shelbyville Middle",  # inexact/name_only (no ID)
                    "Unknown Academy",  # no_match
                ],
                "client_id": ["C1", "C2", "C3"],
            }
        )

    def test_adds_phix_columns_to_dataframe(self, base_df, mapping_file, tmp_path):
        """validate_schools adds four phix_ columns to the returned DataFrame.

        Real-world significance:
        - Downstream audit steps depend on phix_match_type, phix_facility_id,
          phix_matched_name, and phix_matched_phu being present.

        Assertion: all four columns present in result DataFrame.
        """
        result_df, _ = validate_phix.validate_schools(
            base_df, mapping_file, "Test PHU", tmp_path
        )
        for col in [
            "phix_facility_id",
            "phix_match_type",
            "phix_matched_name",
            "phix_matched_phu",
        ]:
            assert col in result_df.columns

    def test_exact_match_row_has_correct_values(self, base_df, mapping_file, tmp_path):
        """Exact-match row has facility ID, match_type='exact', and PHU set.

        Assertion: PHIX columns correct for the exact-match row.
        """
        result_df, _ = validate_phix.validate_schools(
            base_df, mapping_file, "Test PHU", tmp_path
        )
        exact_row = result_df[result_df["client_id"] == "C1"].iloc[0]
        assert exact_row["phix_match_type"] == "exact"
        assert exact_row["phix_facility_id"] == "001"
        assert exact_row["phix_matched_phu"] == "Test PHU"

    def test_no_match_row_has_empty_phu(self, base_df, mapping_file, tmp_path):
        """No-match row has empty phix_matched_phu.

        Assertion: phix_matched_phu is empty string for no_match rows.
        """
        result_df, _ = validate_phix.validate_schools(
            base_df, mapping_file, "Test PHU", tmp_path
        )
        no_match_row = result_df[result_df["client_id"] == "C3"].iloc[0]
        assert no_match_row["phix_matched_phu"] == ""

    def test_warn_behavior_returns_all_rows_and_warning(
        self, base_df, mapping_file, tmp_path
    ):
        """unmatched_behavior='warn' keeps all rows and returns a warning string.

        Real-world significance:
        - Default behaviour; pipeline continues so the run is not blocked,
          but staff are alerted to review phix_no_match.csv.

        Assertion: returned DataFrame has same row count; warnings list non-empty.
        """
        result_df, warnings = validate_phix.validate_schools(
            base_df, mapping_file, "Test PHU", tmp_path, unmatched_behavior="warn"
        )
        assert len(result_df) == len(base_df)
        assert len(warnings) > 0
        assert "no PHIX match" in warnings[0]

    def test_error_behavior_raises_value_error(self, base_df, mapping_file, tmp_path):
        """unmatched_behavior='error' raises ValueError when no_match results exist.

        Real-world significance:
        - Strict mode for PHUs that require all schools to be validated before
          notices are generated.

        Assertion: ValueError raised when any school has no match.
        """
        with pytest.raises(ValueError, match="no PHIX match"):
            validate_phix.validate_schools(
                base_df, mapping_file, "Test PHU", tmp_path, unmatched_behavior="error"
            )

    def test_skip_behavior_filters_unmatched_rows(self, mapping_file, tmp_path):
        """unmatched_behavior='skip' removes rows whose school had no match.

        Real-world significance:
        - Ensures only validated schools proceed when the pipeline is configured
          to exclude unverifiable records.

        Assertion: rows for no_match schools removed; matched rows preserved.
        """
        # Use raw values with and without ID suffix to exercise both code paths
        df = pd.DataFrame(
            {
                "school_name": [
                    "Springfield Elementary - 001",  # exact  (raw value has ' - ID' suffix)
                    "Shelbyville Middle",  # inexact/name_only
                    "Unknown Academy",  # no_match
                ],
                "client_id": ["C1", "C2", "C3"],
            }
        )
        result_df, _ = validate_phix.validate_schools(
            df, mapping_file, "Test PHU", tmp_path, unmatched_behavior="skip"
        )
        assert set(result_df["client_id"]) == {"C1", "C2"}
        assert "C3" not in result_df["client_id"].values

    def test_missing_school_column_returns_df_unchanged(self, mapping_file, tmp_path):
        """DataFrame without school_name column passes through unchanged.

        Real-world significance:
        - Prevents hard crashes when the input is missing the expected column;
          pipeline continues with a logged warning.

        Assertion: original DataFrame returned as-is; warnings empty.
        """
        df = pd.DataFrame({"OTHER_COL": ["a", "b"]})
        result_df, warnings = validate_phix.validate_schools(
            df, mapping_file, "Test PHU", tmp_path
        )
        pd.testing.assert_frame_equal(result_df, df)
        assert warnings == []

    def test_nan_values_in_school_column_treated_as_no_match(
        self, mapping_file, tmp_path
    ):
        """NaN in school_name column does not crash; those rows get no_match columns.

        Real-world significance:
        - Sparse input files often have blank rows in the school column.

        Assertion: NaN rows have phix_match_type='no_match' and empty PHU.
        """
        df = pd.DataFrame(
            {
                "school_name": ["Springfield Elementary - 001", None],
                "client_id": ["C1", "C2"],
            }
        )
        result_df, _ = validate_phix.validate_schools(
            df, mapping_file, "Test PHU", tmp_path
        )
        nan_row = result_df[result_df["client_id"] == "C2"].iloc[0]
        assert nan_row["phix_match_type"] == "no_match"
        assert nan_row["phix_matched_phu"] == ""

    def test_custom_column_prefix_applied(self, base_df, mapping_file, tmp_path):
        """column_prefix parameter changes output column names.

        Assertion: columns use the supplied prefix instead of 'phix_'.
        """
        result_df, _ = validate_phix.validate_schools(
            base_df, mapping_file, "Test PHU", tmp_path, column_prefix="val_"
        )
        assert "val_match_type" in result_df.columns
        assert "phix_match_type" not in result_df.columns

    def test_writes_three_csv_audit_files(self, base_df, mapping_file, tmp_path):
        """CSV audit files are written to output_dir for non-empty categories.

        Real-world significance:
        - Public-health staff review phix_exact.csv, phix_inexact.csv, and
          phix_no_match.csv to follow up on data quality issues.

        Assertion: phix_inexact.csv and phix_no_match.csv present (base_df has both);
          phix_exact.csv present for the exact-match row.
        """
        validate_phix.validate_schools(base_df, mapping_file, "Test PHU", tmp_path)
        assert (tmp_path / "phix_exact.csv").exists()
        assert (tmp_path / "phix_inexact.csv").exists()
        assert (tmp_path / "phix_no_match.csv").exists()

    def test_does_not_mutate_input_dataframe(self, base_df, mapping_file, tmp_path):
        """The input DataFrame is not mutated; a copy is returned.

        Real-world significance:
        - Callers must be able to compare original and enriched DataFrames;
          in-place mutation would break that and could cause subtle bugs.

        Assertion: original DataFrame has no phix_ columns after the call.
        """
        original_cols = set(base_df.columns)
        validate_phix.validate_schools(base_df, mapping_file, "Test PHU", tmp_path)
        assert set(base_df.columns) == original_cols


# ---------------------------------------------------------------------------
# run_phix_validation (preprocess integration)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRunPhixValidation:
    """Preprocessing applies the selected PHIX settings directly."""

    @pytest.fixture
    def base_df(self) -> pd.DataFrame:
        """Minimal DataFrame for preprocess.run_phix_validation tests."""
        return pd.DataFrame(
            {
                "school_name": ["Springfield Elementary - 001", "Unknown Academy"],
                "client_id": ["C1", "C2"],
            }
        )

    def test_disabled_returns_df_unchanged_and_no_warnings(self, tmp_path, base_df):
        """When phix_validation.enabled is false, DataFrame passes through unchanged.

        Real-world significance:
        - Feature is opt-in; PHUs that do not use PHIX must not be affected.

        Assertion: same DataFrame returned; empty warnings list.
        """
        config = {"phix_validation": {"enabled": False}}
        result_df, warnings = preprocess.run_phix_validation(
            base_df, tmp_path, config=config, config_dir=tmp_path
        )

        pd.testing.assert_frame_equal(result_df, base_df)
        assert warnings == []

    def test_missing_mapping_file_key_returns_df_unchanged(self, tmp_path, base_df):
        """When mapping_file is not set, DataFrame passes through unchanged with a log warning.

        Real-world significance:
        - Prevents crashes during misconfigured deployments where the operator
          enabled the feature but forgot to specify the mapping path.

        Assertion: original DataFrame returned; warnings list empty.
        """
        config = {"phix_validation": {"enabled": True, "target_phu": "Test PHU"}}
        result_df, warnings = preprocess.run_phix_validation(
            base_df, tmp_path, config=config, config_dir=tmp_path
        )

        pd.testing.assert_frame_equal(result_df, base_df)
        assert warnings == []

    def test_missing_target_phu_returns_df_unchanged(
        self, tmp_path, base_df, mapping_file
    ):
        """When target_phu is not set, DataFrame passes through unchanged.

        Real-world significance:
        - Without a PHU, there is no mapping to load; pipeline should not crash.

        Assertion: original DataFrame returned; warnings list empty.
        """
        config = {
            "phix_validation": {
                "enabled": True,
                "mapping_file": str(mapping_file),
                "target_phu": "",
            }
        }
        result_df, warnings = preprocess.run_phix_validation(
            base_df, tmp_path, config=config, config_dir=tmp_path
        )

        pd.testing.assert_frame_equal(result_df, base_df)
        assert warnings == []

    def test_enabled_with_valid_config_enriches_df(
        self, tmp_path, base_df, phix_config_yaml
    ):
        """When fully configured and enabled, PHIX columns are added to the DataFrame.

        Real-world significance:
        - The happy path: Step 2 enriches client data with PHIX validation
          metadata used by public-health staff for audit.

        Assertion: phix_ columns present; warnings returned for unmatched school.
        """
        result_df, warnings = preprocess.run_phix_validation(
            base_df,
            tmp_path,
            config=yaml.safe_load(phix_config_yaml.read_text(encoding="utf-8")),
            config_dir=phix_config_yaml.parent,
        )

        assert "phix_match_type" in result_df.columns
        assert "phix_facility_id" in result_df.columns
        # "Unknown Academy" has no match → warning issued
        assert len(warnings) > 0

    def test_relative_mapping_uses_selected_config_directory(
        self, tmp_path, base_df, mapping_file
    ):
        config = {
            "phix_validation": {
                "enabled": True,
                "mapping_file": "phix_mapping.json",
                "target_phu": "Test PHU",
            }
        }
        result, _ = preprocess.run_phix_validation(
            base_df, tmp_path, config=config, config_dir=mapping_file.parent
        )
        assert result.loc[0, "phix_facility_id"] == "001"
