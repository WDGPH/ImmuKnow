"""Unit tests for pipeline/assignment_manifest.py."""

from __future__ import annotations

import io
import json
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from immuknow.assignment_manifest import (
    AssignmentFinding,
    ManifestRow,
    ReconciliationResult,
    has_errors,
    load_manifest,
    print_preflight_summary,
    reconcile,
)
from immuknow.data_models import ClientRecord
from immuknow.notice_versioning import NoticeKind, NoticeVersion, NoticeVersionCatalog
from tests.fixtures.sample_input import create_test_client_record


@pytest.mark.unit
@pytest.mark.parametrize("input_version", [None, "overdue_standard_v1"])
def test_input_version_agrees_with_manifest(input_version: str | None) -> None:
    """An input version can agree with the manifest without losing provenance."""
    client = _client("C001", ["Measles"])
    client = replace(client, version_id=input_version)
    row = ManifestRow("C001", "overdue_standard_v1", None, "study", "A")
    result = reconcile([client], {"C001": row}, _catalog(), False, "error")
    resolved = result.resolved_notices["C001"]
    assert resolved.version_id == "overdue_standard_v1"
    assert resolved.language == "en"
    assert resolved.experiment_id == "study"
    assert resolved.assignment_source == "manifest"


@pytest.mark.unit
def test_input_version_conflict_is_rejected() -> None:
    """An explicit input version cannot be silently overwritten by the manifest."""
    client = _client("C001", ["Measles"])
    client = replace(client, version_id="affirmative_schedule_v1")
    row = ManifestRow("C001", "overdue_standard_v1", "en", None, None)
    result = reconcile([client], {"C001": row}, _catalog(), False, "error")
    assert has_errors(result, "error")
    assert result.resolved_notices == {}
    finding = result.findings[0]
    assert finding.kind == "version_conflict"
    assert finding.client_id == "C001"
    assert "affirmative_schedule_v1" in finding.reason
    assert "overdue_standard_v1" in finding.reason


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_manifest(tmp_path: Path, rows: list) -> Path:
    p = tmp_path / "assignments.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    return p


def _catalog(default_version: str = "overdue_standard_v1") -> NoticeVersionCatalog:
    return NoticeVersionCatalog(
        schema_version=1,
        default_version=default_version,
        default_language="en",
        versions={
            "overdue_standard_v1": NoticeVersion(
                version_id="overdue_standard_v1",
                kind=NoticeKind.OVERDUE,
                requires="has_overdue",
            ),
            "affirmative_schedule_v1": NoticeVersion(
                version_id="affirmative_schedule_v1",
                kind=NoticeKind.AFFIRMATIVE,
                requires="no_overdue",
            ),
        },
    )


def _client(client_id: str, vaccines_due=None) -> ClientRecord:
    return replace(
        create_test_client_record(client_id=client_id),
        overdue_diseases=[
            {"disease": disease, "dose": None} for disease in (vaccines_due or [])
        ],
        version_id=None,
    )


def _row(
    client_id: str, version: str = "overdue_standard_v1", language: str | None = "en"
) -> dict:
    return {
        "client_id": client_id,
        "version_id": version,
        "language": language,
    }


def _empty_result(**overrides) -> ReconciliationResult:
    defaults: dict[str, Any] = {
        "counts_by_version": {},
        "counts_by_language": {},
        "findings": [],
        "default_language": "en",
    }
    defaults.update(overrides)
    return ReconciliationResult(**defaults)


def findings_for(result: ReconciliationResult, kind: str) -> list[AssignmentFinding]:
    return [finding for finding in result.findings if finding.kind == kind]


# ---------------------------------------------------------------------------
# load_manifest
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLoadManifest:
    def test_loads_valid_manifest(self, tmp_path: Path) -> None:
        p = _write_manifest(tmp_path, [_row("C001"), _row("C002")])
        result = load_manifest(p)
        assert "C001" in result
        assert "C002" in result
        assert result["C001"].version_id == "overdue_standard_v1"

    def test_raises_on_non_list_json(self, tmp_path: Path) -> None:
        p = tmp_path / "assignments.json"
        p.write_text('{"client_id": "C001", "version_id": "v1"}', encoding="utf-8")
        with pytest.raises(ValueError, match="must be a JSON array"):
            load_manifest(p)

    def test_raises_missing_client_id(self, tmp_path: Path) -> None:
        p = _write_manifest(tmp_path, [{"version_id": "overdue_standard_v1"}])
        with pytest.raises(ValueError, match="client_id"):
            load_manifest(p)

    def test_raises_missing_version_id(self, tmp_path: Path) -> None:
        p = _write_manifest(tmp_path, [{"client_id": "C001"}])
        with pytest.raises(ValueError, match="required field 'version_id'"):
            load_manifest(p)

    def test_old_field_without_version_id_fails_clearly(self, tmp_path: Path) -> None:
        p = _write_manifest(
            tmp_path,
            [{"client_id": "C001", "notice_version": "overdue_standard_v1"}],
        )
        with pytest.raises(ValueError, match="required field 'version_id'"):
            load_manifest(p)

    @pytest.mark.parametrize("invalid", ["", 123, [], {}])
    def test_rejects_invalid_version_id(self, tmp_path: Path, invalid: object) -> None:
        p = _write_manifest(tmp_path, [{"client_id": "C001", "version_id": invalid}])
        with pytest.raises(ValueError, match="invalid version_id"):
            load_manifest(p)

    def test_raises_on_duplicate_client_ids(self, tmp_path: Path) -> None:
        p = _write_manifest(tmp_path, [_row("C001"), _row("C001")])
        with pytest.raises(ValueError, match="duplicate client_id"):
            load_manifest(p)

    def test_optional_fields_default_to_none(self, tmp_path: Path) -> None:
        p = _write_manifest(tmp_path, [{"client_id": "C001", "version_id": "v1"}])
        result = load_manifest(p)
        assert result["C001"].language is None
        assert result["C001"].experiment_id is None
        assert result["C001"].experiment_arm is None

    def test_preserves_experiment_fields(self, tmp_path: Path) -> None:
        rows = [
            {
                "client_id": "C001",
                "version_id": "v1",
                "experiment_id": "exp_a",
                "experiment_arm": "treatment",
            }
        ]
        p = _write_manifest(tmp_path, rows)
        result = load_manifest(p)
        assert result["C001"].experiment_id == "exp_a"
        assert result["C001"].experiment_arm == "treatment"

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.json"
        p.write_text("{not valid json", encoding="utf-8")
        with pytest.raises(ValueError, match="not valid JSON"):
            load_manifest(p)


# ---------------------------------------------------------------------------
# reconcile
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestReconcile:
    def test_happy_path_all_matched(self, tmp_path: Path) -> None:
        clients = [_client("C001", ["Measles"]), _client("C002", ["Polio"])]
        manifest = {
            "C001": ManifestRow("C001", "overdue_standard_v1", "en", None, None),
            "C002": ManifestRow("C002", "overdue_standard_v1", "fr", None, None),
        }
        result = reconcile(clients, manifest, _catalog(), False, "error")
        assert result.findings == []
        assert result.counts_by_language.get("en", 0) == 1
        assert result.counts_by_language.get("fr", 0) == 1

    def test_detects_missing_clients(self) -> None:
        clients = [_client("C001", ["Measles"]), _client("C002", ["Polio"])]
        manifest = {
            "C001": ManifestRow("C001", "overdue_standard_v1", "en", None, None),
        }
        result = reconcile(
            clients,
            manifest,
            _catalog(),
            allow_unassigned=False,
            extra_manifest_rows="error",
        )
        (finding,) = findings_for(result, "missing_assignment")
        assert finding.client_id == "C002"
        assert "no manifest assignment" in finding.reason

    def test_allow_unassigned_uses_defaults(self) -> None:
        clients = [_client("C001", ["Measles"]), _client("C002", ["Polio"])]
        manifest = {
            "C001": ManifestRow("C001", "overdue_standard_v1", "en", None, None),
        }
        result = reconcile(
            clients,
            manifest,
            _catalog(),
            allow_unassigned=True,
            extra_manifest_rows="error",
        )
        assert not findings_for(result, "missing_assignment")
        # C002 resolved with catalog defaults (overdue_standard_v1, en)
        assert result.counts_by_version.get("overdue_standard_v1 (en)", 0) >= 1

    def test_detects_extra_rows(self) -> None:
        clients = [_client("C001", ["Measles"])]
        manifest = {
            "C001": ManifestRow("C001", "overdue_standard_v1", "en", None, None),
            "EXTRA": ManifestRow("EXTRA", "overdue_standard_v1", "en", None, None),
        }
        result = reconcile(clients, manifest, _catalog(), False, "warn")
        (finding,) = findings_for(result, "extra_manifest_row")
        assert finding.client_id == "EXTRA"
        assert finding.version_id == "overdue_standard_v1"

    def test_detects_unknown_versions(self) -> None:
        clients = [_client("C001", ["Measles"])]
        manifest = {
            "C001": ManifestRow("C001", "no_such_version", "en", None, None),
        }
        result = reconcile(clients, manifest, _catalog(), False, "error")
        (finding,) = findings_for(result, "unknown_version")
        assert (finding.client_id, finding.version_id) == ("C001", "no_such_version")
        assert "notice_versions.yaml" in finding.reason

    def test_detects_missing_language_clients(self) -> None:
        clients = [_client("C001", ["Measles"])]
        manifest = {
            "C001": ManifestRow("C001", "overdue_standard_v1", None, None, None),
        }
        result = reconcile(clients, manifest, _catalog(), False, "error")
        (finding,) = findings_for(result, "missing_language")
        assert finding.client_id == "C001"
        assert "default 'en'" in finding.reason
        # Should still be counted with default language
        assert result.counts_by_language.get("en", 0) == 1

    def test_detects_eligibility_conflicts(self) -> None:
        # Affirmative assigned but client has vaccines due
        clients = [_client("C001", ["Measles"])]
        manifest = {
            "C001": ManifestRow("C001", "affirmative_schedule_v1", "en", None, None),
        }
        result = reconcile(clients, manifest, _catalog(), False, "error")
        (finding,) = findings_for(result, "eligibility_conflict")
        assert (finding.client_id, finding.version_id) == (
            "C001",
            "affirmative_schedule_v1",
        )
        assert "no_overdue" in finding.reason

    def test_counts_by_version_uses_composite_keys(self) -> None:
        clients = [_client("C001", ["Measles"]), _client("C002", ["Polio"])]
        manifest = {
            "C001": ManifestRow("C001", "overdue_standard_v1", "en", None, None),
            "C002": ManifestRow("C002", "overdue_standard_v1", "fr", None, None),
        }
        result = reconcile(clients, manifest, _catalog(), False, "error")
        assert "overdue_standard_v1 (en)" in result.counts_by_version
        assert "overdue_standard_v1 (fr)" in result.counts_by_version


# ---------------------------------------------------------------------------
# has_errors
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHasErrors:
    def test_no_errors_returns_false(self) -> None:
        assert not has_errors(_empty_result(), "error")

    def test_missing_clients_is_always_error(self) -> None:
        result = _empty_result(
            findings=[AssignmentFinding("missing_assignment", "C001", None, "missing")]
        )
        assert has_errors(result, "error")
        assert has_errors(result, "warn")

    def test_unknown_versions_is_always_error(self) -> None:
        result = _empty_result(
            findings=[
                AssignmentFinding("unknown_version", "C001", "bad_version", "unknown")
            ]
        )
        assert has_errors(result, "error")
        assert has_errors(result, "warn")

    def test_eligibility_conflicts_is_always_error(self) -> None:
        result = _empty_result(
            findings=[
                AssignmentFinding("eligibility_conflict", "C001", "v1", "ineligible")
            ]
        )
        assert has_errors(result, "error")
        assert has_errors(result, "warn")

    def test_extra_rows_respects_error_policy(self) -> None:
        result = _empty_result(
            findings=[AssignmentFinding("extra_manifest_row", "EXTRA", "v1", "extra")]
        )
        assert has_errors(result, "error")
        assert not has_errors(result, "warn")

    def test_missing_language_clients_not_an_error(self) -> None:
        result = _empty_result(
            findings=[AssignmentFinding("missing_language", "C001", "v1", "default")]
        )
        assert not has_errors(result, "error")


# ---------------------------------------------------------------------------
# print_preflight_summary
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPrintPreflightSummary:
    def _capture(self, result: ReconciliationResult) -> str:
        buf = io.StringIO()
        with patch(
            "builtins.print",
            side_effect=lambda *args, **kw: buf.write(
                " ".join(str(a) for a in args) + "\n"
            ),
        ):
            print_preflight_summary(result)
        return buf.getvalue()

    def test_output_contains_no_pii(self) -> None:
        result = _empty_result(
            counts_by_version={"overdue_standard_v1 (en)": 100},
            counts_by_language={"en": 100},
        )
        output = self._capture(result)
        pii_candidates = ["John", "Jane", "Smith", "1990-01-01", "123 Main St"]
        for pii in pii_candidates:
            assert pii not in output

    def test_shows_assignment_mode(self) -> None:
        output = self._capture(_empty_result())
        assert "manifest" in output

    def test_shows_version_language_counts(self) -> None:
        result = _empty_result(
            counts_by_version={
                "overdue_standard_v1 (en)": 500,
                "overdue_standard_v1 (fr)": 125,
            },
            counts_by_language={"en": 500, "fr": 125},
        )
        output = self._capture(result)
        assert "overdue_standard_v1 (en)" in output
        assert "500" in output
        assert "overdue_standard_v1 (fr)" in output
        assert "125" in output

    def test_shows_missing_language_with_default(self) -> None:
        result = _empty_result(
            findings=[
                AssignmentFinding("missing_language", "C001", "v1", "default"),
                AssignmentFinding("missing_language", "C002", "v1", "default"),
            ],
            default_language="fr",
        )
        output = self._capture(result)
        assert "2" in output
        assert "fr" in output

    def test_shows_zero_counts_for_clean_run(self) -> None:
        output = self._capture(_empty_result())
        assert "Missing clients" in output
        assert "0" in output
