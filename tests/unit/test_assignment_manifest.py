"""Unit tests for pipeline/assignment_manifest.py."""

from __future__ import annotations

import json
import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.assignment_manifest import (
    ManifestRow,
    ReconciliationResult,
    has_errors,
    load_manifest,
    print_preflight_summary,
    reconcile,
)
from pipeline.notice_versioning import NoticeKind, NoticeVersion, NoticeVersionCatalog


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
                version_id="overdue_standard_v1", kind=NoticeKind.OVERDUE, requires="has_overdue"
            ),
            "affirmative_schedule_v1": NoticeVersion(
                version_id="affirmative_schedule_v1", kind=NoticeKind.AFFIRMATIVE, requires="no_overdue"
            ),
        },
    )


def _client(client_id: str, vaccines_due=None) -> MagicMock:
    m = MagicMock()
    m.client_id = client_id
    m.vaccines_due_list = vaccines_due
    return m


def _row(client_id: str, version: str = "overdue_standard_v1", language: str | None = "en") -> dict:
    return {
        "client_id": client_id,
        "notice_version": version,
        "language": language,
    }


def _empty_result(**overrides) -> ReconciliationResult:
    defaults = dict(
        counts_by_version={},
        counts_by_language={},
        missing_clients=[],
        extra_rows=[],
        duplicate_manifest_ids=[],
        unknown_versions=[],
        missing_language_clients=[],
        eligibility_conflicts=[],
        default_language="en",
    )
    defaults.update(overrides)
    return ReconciliationResult(**defaults)


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
        assert result["C001"].notice_version == "overdue_standard_v1"

    def test_raises_on_non_list_json(self, tmp_path: Path) -> None:
        p = tmp_path / "assignments.json"
        p.write_text('{"client_id": "C001", "notice_version": "v1"}', encoding="utf-8")
        with pytest.raises(ValueError, match="must be a JSON array"):
            load_manifest(p)

    def test_raises_missing_client_id(self, tmp_path: Path) -> None:
        p = _write_manifest(tmp_path, [{"notice_version": "overdue_standard_v1"}])
        with pytest.raises(ValueError, match="client_id"):
            load_manifest(p)

    def test_raises_missing_notice_version(self, tmp_path: Path) -> None:
        p = _write_manifest(tmp_path, [{"client_id": "C001"}])
        with pytest.raises(ValueError, match="notice_version"):
            load_manifest(p)

    def test_raises_on_duplicate_client_ids(self, tmp_path: Path) -> None:
        p = _write_manifest(tmp_path, [_row("C001"), _row("C001")])
        with pytest.raises(ValueError, match="duplicate client_id"):
            load_manifest(p)

    def test_optional_fields_default_to_none(self, tmp_path: Path) -> None:
        p = _write_manifest(tmp_path, [{"client_id": "C001", "notice_version": "v1"}])
        result = load_manifest(p)
        assert result["C001"].language is None
        assert result["C001"].experiment_id is None
        assert result["C001"].experiment_arm is None

    def test_preserves_experiment_fields(self, tmp_path: Path) -> None:
        rows = [{
            "client_id": "C001",
            "notice_version": "v1",
            "experiment_id": "exp_a",
            "experiment_arm": "treatment",
        }]
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
        assert result.missing_clients == []
        assert result.extra_rows == []
        assert result.unknown_versions == []
        assert result.eligibility_conflicts == []
        assert result.counts_by_language.get("en", 0) == 1
        assert result.counts_by_language.get("fr", 0) == 1

    def test_detects_missing_clients(self) -> None:
        clients = [_client("C001", ["Measles"]), _client("C002", ["Polio"])]
        manifest = {
            "C001": ManifestRow("C001", "overdue_standard_v1", "en", None, None),
        }
        result = reconcile(clients, manifest, _catalog(), allow_unassigned=False, extra_manifest_rows="error")
        assert "C002" in result.missing_clients

    def test_allow_unassigned_uses_defaults(self) -> None:
        clients = [_client("C001", ["Measles"]), _client("C002", ["Polio"])]
        manifest = {
            "C001": ManifestRow("C001", "overdue_standard_v1", "en", None, None),
        }
        result = reconcile(clients, manifest, _catalog(), allow_unassigned=True, extra_manifest_rows="error")
        assert result.missing_clients == []
        # C002 resolved with catalog defaults (overdue_standard_v1, en)
        assert result.counts_by_version.get("overdue_standard_v1 (en)", 0) >= 1

    def test_detects_extra_rows(self) -> None:
        clients = [_client("C001", ["Measles"])]
        manifest = {
            "C001": ManifestRow("C001", "overdue_standard_v1", "en", None, None),
            "EXTRA": ManifestRow("EXTRA", "overdue_standard_v1", "en", None, None),
        }
        result = reconcile(clients, manifest, _catalog(), False, "warn")
        assert "EXTRA" in result.extra_rows

    def test_detects_unknown_versions(self) -> None:
        clients = [_client("C001", ["Measles"])]
        manifest = {
            "C001": ManifestRow("C001", "no_such_version", "en", None, None),
        }
        result = reconcile(clients, manifest, _catalog(), False, "error")
        assert "no_such_version" in result.unknown_versions
        # Client should not appear in counts
        assert "C001" not in result.missing_clients

    def test_detects_missing_language_clients(self) -> None:
        clients = [_client("C001", ["Measles"])]
        manifest = {
            "C001": ManifestRow("C001", "overdue_standard_v1", None, None, None),
        }
        result = reconcile(clients, manifest, _catalog(), False, "error")
        assert "C001" in result.missing_language_clients
        # Should still be counted with default language
        assert result.counts_by_language.get("en", 0) == 1

    def test_detects_eligibility_conflicts(self) -> None:
        # Affirmative assigned but client has vaccines due
        clients = [_client("C001", ["Measles"])]
        manifest = {
            "C001": ManifestRow("C001", "affirmative_schedule_v1", "en", None, None),
        }
        result = reconcile(clients, manifest, _catalog(), False, "error")
        assert "C001" in result.eligibility_conflicts

    def test_duplicate_manifest_ids_always_empty(self) -> None:
        # load_manifest raises on duplicates; reconcile always produces empty list
        clients = [_client("C001", ["Measles"])]
        manifest = {
            "C001": ManifestRow("C001", "overdue_standard_v1", "en", None, None),
        }
        result = reconcile(clients, manifest, _catalog(), False, "error")
        assert result.duplicate_manifest_ids == []

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
        result = _empty_result(missing_clients=["C001"])
        assert has_errors(result, "error")
        assert has_errors(result, "warn")

    def test_unknown_versions_is_always_error(self) -> None:
        result = _empty_result(unknown_versions=["bad_version"])
        assert has_errors(result, "error")
        assert has_errors(result, "warn")

    def test_eligibility_conflicts_is_always_error(self) -> None:
        result = _empty_result(eligibility_conflicts=["C001"])
        assert has_errors(result, "error")
        assert has_errors(result, "warn")

    def test_extra_rows_respects_error_policy(self) -> None:
        result = _empty_result(extra_rows=["EXTRA"])
        assert has_errors(result, "error")
        assert not has_errors(result, "warn")

    def test_missing_language_clients_not_an_error(self) -> None:
        result = _empty_result(missing_language_clients=["C001"])
        assert not has_errors(result, "error")


# ---------------------------------------------------------------------------
# print_preflight_summary
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPrintPreflightSummary:
    def _capture(self, result: ReconciliationResult) -> str:
        import io
        buf = io.StringIO()
        with patch("builtins.print", side_effect=lambda *args, **kw: buf.write(" ".join(str(a) for a in args) + "\n")):
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
            missing_language_clients=["C001", "C002"],
            default_language="fr",
        )
        output = self._capture(result)
        assert "2" in output
        assert "fr" in output

    def test_shows_zero_counts_for_clean_run(self) -> None:
        output = self._capture(_empty_result())
        assert "Missing clients" in output
        assert "0" in output
