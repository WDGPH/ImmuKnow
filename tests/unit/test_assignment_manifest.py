"""Manifest parsing and cohort reconciliation behavior."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

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
from immuknow.notice_versioning import NoticeKind, NoticeVersion, NoticeVersionCatalog
from tests.fixtures.sample_input import create_test_client_record


def write_manifest(tmp_path: Path, rows: object) -> Path:
    path = tmp_path / "assignments.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    return path


def row(
    client_id: str, version: str = "overdue_standard_v1", language: str = "en"
) -> dict:
    return {"client_id": client_id, "version_id": version, "language": language}


def catalog() -> NoticeVersionCatalog:
    return NoticeVersionCatalog(
        schema_version=1,
        versions={
            "overdue_standard_v1": NoticeVersion(
                "overdue_standard_v1", NoticeKind.OVERDUE, "has_overdue"
            ),
            "affirmative_schedule_v1": NoticeVersion(
                "affirmative_schedule_v1", NoticeKind.AFFIRMATIVE, "no_overdue"
            ),
        },
    )


def client(client_id: str, diseases: list[str], version_id: str | None = None):
    return replace(
        create_test_client_record(client_id=client_id),
        overdue_diseases=[{"disease": name, "dose": None} for name in diseases],
        version_id=version_id,
    )


def assignment(
    client_id: str, version: str = "overdue_standard_v1", language: str = "en"
):
    return ManifestRow(client_id, version, language, None, None)


def findings(result: ReconciliationResult, kind: str) -> list[AssignmentFinding]:
    return [item for item in result.findings if item.kind == kind]


@pytest.mark.unit
def test_manifest_loads_explicit_language_and_experiment_metadata(
    tmp_path: Path,
) -> None:
    path = write_manifest(
        tmp_path,
        [
            {
                **row("C001", language="fr"),
                "experiment_id": "study",
                "experiment_arm": "B",
            }
        ],
    )
    loaded = load_manifest(path)
    assert loaded == {
        "C001": ManifestRow("C001", "overdue_standard_v1", "fr", "study", "B")
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    "rows,message",
    [
        ({"client_id": "C001"}, "JSON array"),
        ([123], "row 1"),
        ([{"version_id": "v1", "language": "en"}], "client_id"),
        ([{"client_id": "C001", "language": "en"}], "version_id"),
        (
            [{"client_id": "C001", "notice_version": "v1", "language": "en"}],
            "version_id",
        ),
        ([row("C001"), row("C001")], "duplicate client_id"),
    ],
)
def test_manifest_rejects_malformed_or_duplicate_rows(
    tmp_path: Path, rows: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        load_manifest(write_manifest(tmp_path, rows))


@pytest.mark.unit
@pytest.mark.parametrize("invalid", ["", 123, [], {}])
def test_manifest_rejects_invalid_version_id(tmp_path: Path, invalid: object) -> None:
    with pytest.raises(ValueError, match="version_id"):
        load_manifest(
            write_manifest(tmp_path, [{**row("C001"), "version_id": invalid}])
        )


@pytest.mark.unit
@pytest.mark.parametrize("language", [None, "", "es", 123, []])
def test_manifest_rejects_missing_or_unsupported_language(
    tmp_path: Path, language: object
) -> None:
    with pytest.raises(ValueError, match="language"):
        load_manifest(write_manifest(tmp_path, [{**row("C001"), "language": language}]))


@pytest.mark.unit
def test_manifest_rejects_absent_language_field(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="language"):
        load_manifest(
            write_manifest(tmp_path, [{"client_id": "C001", "version_id": "v1"}])
        )


@pytest.mark.unit
def test_manifest_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "assignments.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError, match="valid JSON"):
        load_manifest(path)


@pytest.mark.unit
def test_reconcile_preserves_explicit_identity_and_provenance() -> None:
    records = [
        client("C001", ["Measles"], version_id="overdue_standard_v1"),
        client("C002", ["Polio"]),
    ]
    selected = {
        "C001": ManifestRow("C001", "overdue_standard_v1", "en", "study", "A"),
        "C002": ManifestRow("C002", "overdue_standard_v1", "fr", None, None),
    }
    result = reconcile(records, selected, catalog(), "error")
    assert result.findings == []
    assert result.counts_by_language == {"en": 1, "fr": 1}
    assert result.counts_by_version == {
        "overdue_standard_v1 (en)": 1,
        "overdue_standard_v1 (fr)": 1,
    }
    assert result.resolved_notices["C001"].experiment_id == "study"
    assert result.resolved_notices["C001"].experiment_arm == "A"
    assert result.resolved_notices["C001"].assignment_source == "manifest"
    assert result.resolved_notices["C002"].language == "fr"


@pytest.mark.unit
def test_missing_client_assignment_is_always_fatal() -> None:
    result = reconcile(
        [client("C001", ["Measles"]), client("C002", ["Polio"])],
        {"C001": assignment("C001")},
        catalog(),
        "warn",
    )
    missing = findings(result, "missing_assignment")
    assert len(missing) == 1
    assert missing[0].client_id == "C002"
    assert "manifest" in missing[0].reason
    assert "C002" not in result.resolved_notices
    assert has_errors(result, "warn")


@pytest.mark.unit
def test_source_version_conflict_identifies_both_versions() -> None:
    result = reconcile(
        [client("C001", ["Measles"], version_id="affirmative_schedule_v1")],
        {"C001": assignment("C001")},
        catalog(),
        "error",
    )
    conflict = findings(result, "version_conflict")
    assert len(conflict) == 1
    assert conflict[0].client_id == "C001"
    assert "affirmative_schedule_v1" in conflict[0].reason
    assert "overdue_standard_v1" in conflict[0].reason
    assert has_errors(result, "error")


@pytest.mark.unit
def test_unknown_version_and_eligibility_conflict_are_client_linked() -> None:
    result = reconcile(
        [client("C001", ["Measles"]), client("C002", ["Polio"])],
        {
            "C001": assignment("C001", "unregistered_v1"),
            "C002": assignment("C002", "affirmative_schedule_v1"),
        },
        catalog(),
        "error",
    )
    unknown = findings(result, "unknown_version")
    ineligible = findings(result, "eligibility_conflict")
    assert [(item.client_id, item.version_id) for item in unknown] == [
        ("C001", "unregistered_v1")
    ]
    assert [(item.client_id, item.version_id) for item in ineligible] == [
        ("C002", "affirmative_schedule_v1")
    ]
    assert "no_overdue" in ineligible[0].reason
    assert has_errors(result, "error")


@pytest.mark.unit
@pytest.mark.parametrize("policy,should_fail", [("warn", False), ("error", True)])
def test_extra_manifest_rows_follow_configured_policy(
    policy: str, should_fail: bool
) -> None:
    result = reconcile(
        [client("C001", ["Measles"])],
        {"C001": assignment("C001"), "EXTRA": assignment("EXTRA")},
        catalog(),
        policy,
    )
    extra = findings(result, "extra_manifest_row")
    assert len(extra) == 1
    assert extra[0].client_id == "EXTRA"
    assert extra[0].version_id == "overdue_standard_v1"
    assert has_errors(result, policy) is should_fail


@pytest.mark.unit
def test_preflight_console_shows_counts_without_client_details(capsys) -> None:
    result = reconcile(
        [client("C001", ["Measles"])],
        {"C001": assignment("C001", language="fr")},
        catalog(),
        "error",
    )
    print_preflight_summary(result)
    output = capsys.readouterr().out
    assert "overdue_standard_v1" in output
    assert "fr" in output
    assert "1" in output
    assert "C001" not in output
    assert "Measles" not in output


@pytest.mark.unit
def test_manifest_omitted_experiment_fields_remain_absent(tmp_path: Path) -> None:
    loaded = load_manifest(write_manifest(tmp_path, [row("C001")]))
    assert loaded["C001"].experiment_id is None
    assert loaded["C001"].experiment_arm is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "kind",
    [
        "missing_assignment",
        "unknown_version",
        "eligibility_conflict",
        "version_conflict",
    ],
)
def test_each_client_assignment_failure_is_fatal(kind: str) -> None:
    result = ReconciliationResult(
        counts_by_version={},
        counts_by_language={},
        findings=[AssignmentFinding(kind, "C001", "v1", "synthetic failure")],
    )
    assert has_errors(result, "warn")
