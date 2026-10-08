"""Catalog and eligibility checks for the complete notice workflow."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from immuknow.notice_versioning import (
    NoticeKind,
    NoticeVersion,
    NoticeVersionCatalog,
    ResolvedNotice,
    attach_notice,
    load_catalog,
    validate_eligibility,
)
from tests.fixtures.sample_input import create_test_client_record


def catalog() -> NoticeVersionCatalog:
    return NoticeVersionCatalog(
        schema_version=1,
        versions={
            "overdue_diseases_v1": NoticeVersion(
                "overdue_diseases_v1", NoticeKind.OVERDUE, "has_overdue"
            ),
            "overdue_agents_v1": NoticeVersion(
                "overdue_agents_v1", NoticeKind.OVERDUE, "has_overdue"
            ),
            "affirmative_schedule_v1": NoticeVersion(
                "affirmative_schedule_v1", NoticeKind.AFFIRMATIVE, "no_overdue"
            ),
            "info_v1": NoticeVersion("info_v1", NoticeKind.INFORMATIONAL, "any"),
        },
    )


def write_catalog(tmp_path: Path, content: object) -> None:
    (tmp_path / "notice_versions.yaml").write_text(
        yaml.safe_dump(content), encoding="utf-8"
    )


def client(diseases: list[str] | None):
    return replace(
        create_test_client_record(client_id="C001"),
        overdue_diseases=[
            {"disease": disease, "dose": None} for disease in (diseases or [])
        ],
    )


def assigned(version_id: str, kind: NoticeKind, language: str = "en") -> ResolvedNotice:
    return ResolvedNotice(version_id, kind.value, language, None, None, "manifest")


@pytest.mark.unit
def test_catalog_loads_registered_kinds_and_explicit_rule(tmp_path: Path) -> None:
    write_catalog(
        tmp_path,
        {
            "schema_version": 1,
            "versions": {
                "overdue_diseases_v1": {"kind": "overdue"},
                "affirmative_schedule_v1": {"kind": "affirmative"},
                "info_v1": {"kind": "informational", "requires": "any"},
            },
        },
    )
    loaded = load_catalog(tmp_path)
    assert loaded.schema_version == 1
    assert loaded.versions["overdue_diseases_v1"].requires == "has_overdue"
    assert loaded.versions["affirmative_schedule_v1"].requires == "no_overdue"
    assert loaded.versions["info_v1"].requires == "any"


@pytest.mark.unit
def test_catalog_missing_file_fails_instead_of_using_hidden_defaults(
    tmp_path: Path,
) -> None:
    with pytest.raises(FileNotFoundError, match="notice_versions.yaml"):
        load_catalog(tmp_path)


@pytest.mark.unit
@pytest.mark.parametrize("raw", ["[]", "null", "hello", "- version: bad"])
def test_catalog_requires_mapping(tmp_path: Path, raw: str) -> None:
    (tmp_path / "notice_versions.yaml").write_text(raw, encoding="utf-8")
    with pytest.raises(ValueError, match="mapping"):
        load_catalog(tmp_path)


@pytest.mark.unit
@pytest.mark.parametrize("schema", [None, True, False, "1", 1.0, 2])
def test_catalog_rejects_missing_or_invalid_schema(
    tmp_path: Path, schema: object
) -> None:
    entry: dict[str, object] = {"versions": {"v1": {"kind": "overdue"}}}
    if schema is not None:
        entry["schema_version"] = schema
    write_catalog(tmp_path, entry)
    with pytest.raises(ValueError, match="schema_version"):
        load_catalog(tmp_path)


@pytest.mark.unit
@pytest.mark.parametrize("retired", ["default_language", "default_version"])
def test_catalog_rejects_retired_default_keys(tmp_path: Path, retired: str) -> None:
    write_catalog(
        tmp_path,
        {
            "schema_version": 1,
            "versions": {"v1": {"kind": "overdue"}},
            retired: "en" if retired == "default_language" else "v1",
        },
    )
    with pytest.raises(ValueError, match=retired):
        load_catalog(tmp_path)


@pytest.mark.unit
@pytest.mark.parametrize(
    "versions",
    [None, [], {}, {"v1": []}, {"v1": None}, {"": {"kind": "overdue"}}],
)
def test_catalog_rejects_malformed_versions(tmp_path: Path, versions: object) -> None:
    write_catalog(tmp_path, {"schema_version": 1, "versions": versions})
    with pytest.raises(ValueError, match="versions|version|identifier"):
        load_catalog(tmp_path)


@pytest.mark.unit
@pytest.mark.parametrize(
    "entry,reason",
    [
        ({"kind": "unknown"}, "kind"),
        ({"kind": "overdue", "requires": "unknown"}, "requires"),
        ({"kind": "overdue", "requires": ["any"]}, "requires"),
    ],
)
def test_catalog_rejects_invalid_rule_with_version_context(
    tmp_path: Path, entry: dict, reason: str
) -> None:
    write_catalog(tmp_path, {"schema_version": 1, "versions": {"v1": entry}})
    with pytest.raises(ValueError, match=f"v1.*{reason}"):
        load_catalog(tmp_path)


@pytest.mark.unit
def test_catalog_rejects_invalid_yaml(tmp_path: Path) -> None:
    (tmp_path / "notice_versions.yaml").write_text(
        "versions: [unclosed", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="invalid YAML"):
        load_catalog(tmp_path)


@pytest.mark.unit
@pytest.mark.parametrize(
    "version,kind,diseases,allowed",
    [
        ("overdue_diseases_v1", NoticeKind.OVERDUE, ["Measles"], True),
        ("overdue_diseases_v1", NoticeKind.OVERDUE, [], False),
        ("affirmative_schedule_v1", NoticeKind.AFFIRMATIVE, [], True),
        ("affirmative_schedule_v1", NoticeKind.AFFIRMATIVE, ["Measles"], False),
        ("info_v1", NoticeKind.INFORMATIONAL, [], True),
        ("info_v1", NoticeKind.INFORMATIONAL, ["Measles"], True),
    ],
)
def test_eligibility_uses_canonical_overdue_diseases(
    version: str, kind: NoticeKind, diseases: list[str], allowed: bool
) -> None:
    record = client(diseases)
    resolved = assigned(version, kind)
    if allowed:
        validate_eligibility(record, resolved, catalog())
    else:
        with pytest.raises(ValueError) as error:
            validate_eligibility(record, resolved, catalog())
        assert record.client_id in str(error.value)
        assert catalog().versions[version].requires in str(error.value)


@pytest.mark.unit
def test_explicit_any_rule_overrides_kind_default() -> None:
    selected = NoticeVersionCatalog(
        schema_version=1,
        versions={"open": NoticeVersion("open", NoticeKind.OVERDUE, "any")},
    )
    validate_eligibility(client([]), assigned("open", NoticeKind.OVERDUE), selected)


@pytest.mark.unit
def test_attaching_assignment_retains_client_metadata_and_provenance() -> None:
    record = replace(
        client(["Measles"]),
        metadata={"source_batch": "synthetic", "custom": {"flag": True}},
    )
    resolved = ResolvedNotice(
        "overdue_agents_v1", NoticeKind.OVERDUE.value, "fr", "study", "B", "manifest"
    )
    attached = attach_notice(record, resolved)
    assert attached.version_id == "overdue_agents_v1"
    assert attached.language == "fr"
    assert attached.metadata == {
        "source_batch": "synthetic",
        "custom": {"flag": True},
        "notice_kind": "overdue",
        "experiment_id": "study",
        "experiment_arm": "B",
        "assignment_source": "manifest",
    }


@pytest.mark.unit
def test_eligibility_error_identifies_client_without_person_name() -> None:
    record = replace(
        client([]),
        person={**client([]).person, "first_name": "Sensitive", "last_name": "Name"},
    )
    with pytest.raises(ValueError) as error:
        validate_eligibility(
            record, assigned("overdue_diseases_v1", NoticeKind.OVERDUE), catalog()
        )
    assert "C001" in str(error.value)
    assert "Sensitive" not in str(error.value)
    assert "Name" not in str(error.value)
