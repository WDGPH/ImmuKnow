"""Explicit assignments fail only ambiguous rows and preserve warning selections."""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from immuknow.assignment_manifest import load_manifest, reconcile
from immuknow.preprocess import CONFIG_DIR
from immuknow.version_notices import load_catalog
from tests.unit.test_preprocess import prepare, source_rows


def load_rows(tmp_path: Path, rows):
    path = tmp_path / "assignments.json"
    path.write_text(json.dumps(rows))
    return load_manifest(path, tmp_path)


@pytest.mark.unit
def test_missing_and_ambiguous_files_preserve_independent_assignments(tmp_path: Path):
    (tmp_path / "overdue_diseases_v1.fr.typ").write_text("letter")
    rows = [
        {"client_id": "0000000001", "template": "overdue_diseases_v1.fr.typ"},
        {"client_id": "0000000002", "template": "missing.en.typ"},
        {"client_id": "extra", "template": "overdue_diseases_v1.fr.typ"},
    ]
    manifest = load_rows(tmp_path, rows)
    assert manifest["0000000002"].template == "missing.en.typ"
    clients, _ = prepare(source_rows())
    result = reconcile(clients.clients, manifest, load_catalog(CONFIG_DIR))
    assert list(result.resolved_notices) == ["row-000001"]
    assert result.resolved_notices["row-000001"].language == "fr"
    assert {(f.kind, f.status) for f in result.findings} == {
        ("missing_template", "fail"),
        ("extra_manifest_row", "warn"),
    }
    manifest = load_rows(tmp_path, [rows[0], rows[0]])
    result = reconcile(clients.clients, manifest, load_catalog(CONFIG_DIR))
    assert not result.resolved_notices
    assert result.findings[0].kind == "ambiguous_assignment"


@pytest.mark.unit
def test_unknown_catalog_and_applicability_conflicts_warn_and_keep_selection(
    tmp_path: Path,
):
    for name in ("custom.en.typ", "affirmative_schedule_v1.fr.typ"):
        (tmp_path / name).write_text("letter")
    manifest = load_rows(
        tmp_path,
        [
            {
                "client_id": "0000000001",
                "template": "affirmative_schedule_v1.fr.typ",
                "experiment_id": "wording",
                "experiment_arm": "B",
            },
            {"client_id": "0000000002", "template": "custom.en.typ"},
        ],
    )
    prepared, _ = prepare(source_rows())
    clients = [replace(c, version_id=None) for c in prepared.clients]
    result = reconcile(clients, manifest, load_catalog(CONFIG_DIR))
    assert len(result.resolved_notices) == 2
    assert {f.kind for f in result.findings} == {
        "eligibility_conflict",
        "check_unavailable",
    }
    assert all(f.status == "warn" for f in result.findings)
    assert result.resolved_notices["row-000001"].experiment_arm == "B"


@pytest.mark.unit
def test_duplicate_source_ids_never_choose_a_row(tmp_path: Path):
    (tmp_path / "overdue_diseases_v1.en.typ").write_text("letter")
    frame = source_rows()
    frame.loc[1, "client_id"] = frame.loc[0, "client_id"]
    prepared, _ = prepare(frame)
    manifest = load_rows(
        tmp_path,
        [{"client_id": "0000000001", "template": "overdue_diseases_v1.en.typ"}],
    )
    result = reconcile(prepared.clients, manifest, load_catalog(CONFIG_DIR))
    assert not result.resolved_notices
    assert [f.row_key for f in result.findings] == ["row-000001", "row-000002"]
    assert all(
        f.kind == "duplicate_client_id" and f.status == "fail" for f in result.findings
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "rows",
    [
        {},
        [1],
        [{"client_id": "x"}],
        [{"client_id": "x", "template": "custom.en.typ", "experiment_arm": 1}],
    ],
)
def test_malformed_shared_manifest_stops_setup(tmp_path: Path, rows):
    with pytest.raises(ValueError):
        load_rows(tmp_path, rows)


def test_assignment_whitespace_matches_source_trimming_and_exposes_collisions(tmp_path):
    (tmp_path / "custom.en.typ").write_text("letter")
    manifest = load_rows(
        tmp_path, [{"client_id": " 0000000001 ", "template": " custom.en.typ "}]
    )
    assert list(manifest) == ["0000000001"]
    assert manifest["0000000001"].template == "custom.en.typ"
    assert manifest["0000000001"].error is None
    manifest = load_rows(
        tmp_path,
        [
            {"client_id": " 0000000001 ", "template": "custom.en.typ"},
            {"client_id": "0000000001", "template": "custom.en.typ"},
        ],
    )
    assert manifest["0000000001"].error_kind == "ambiguous_assignment"


def test_assignment_unknown_fields_cannot_hide_a_typo(tmp_path):
    with pytest.raises(ValueError, match="unknown fields"):
        load_rows(
            tmp_path,
            [
                {
                    "client_id": "0000000001",
                    "template": "custom.en.typ",
                    "experiment_arn": "B",
                }
            ],
        )
