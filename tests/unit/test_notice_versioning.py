"""Unit tests for pipeline/notice_versioning.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from pipeline.notice_versioning import (
    ELIGIBILITY_RULES,
    NoticeKind,
    NoticeVersion,
    NoticeVersionCatalog,
    ResolvedNotice,
    load_catalog,
    validate_eligibility,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_catalog(tmp_path: Path, content: dict) -> Path:
    p = tmp_path / "notice_versions.yaml"
    p.write_text(yaml.dump(content), encoding="utf-8")
    return tmp_path


def _make_catalog() -> NoticeVersionCatalog:
    return NoticeVersionCatalog(
        schema_version=1,
        default_version="overdue_standard_v1",
        default_language="en",
        versions={
            "overdue_standard_v1": NoticeVersion(
                version_id="overdue_standard_v1", kind=NoticeKind.OVERDUE, requires="has_overdue"
            ),
            "affirmative_schedule_v1": NoticeVersion(
                version_id="affirmative_schedule_v1", kind=NoticeKind.AFFIRMATIVE, requires="no_overdue"
            ),
            "info_v1": NoticeVersion(
                version_id="info_v1", kind=NoticeKind.INFORMATIONAL, requires="any"
            ),
        },
    )


def _resolved(kind: str, version: str = "overdue_standard_v1") -> ResolvedNotice:
    return ResolvedNotice(
        notice_version=version,
        notice_kind=kind,
        language="en",
        experiment_id=None,
        experiment_arm=None,
        assignment_source="manifest",
    )


def _client(vaccines_due_list):
    m = MagicMock()
    m.client_id = "C001"
    m.vaccines_due_list = vaccines_due_list
    return m


# ---------------------------------------------------------------------------
# load_catalog
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestLoadCatalog:
    def test_returns_none_when_file_absent(self, tmp_path: Path) -> None:
        result = load_catalog(tmp_path)
        assert result is None

    def test_loads_valid_catalog(self, tmp_path: Path) -> None:
        _write_catalog(tmp_path, {
            "schema_version": 1,
            "default_version": "overdue_standard_v1",
            "default_language": "en",
            "versions": {
                "overdue_standard_v1": {"kind": "overdue"},
                "affirmative_schedule_v1": {"kind": "affirmative"},
            },
        })
        catalog = load_catalog(tmp_path)
        assert catalog is not None
        assert catalog.schema_version == 1
        assert catalog.default_version == "overdue_standard_v1"
        assert catalog.default_language == "en"
        assert "overdue_standard_v1" in catalog.versions
        assert catalog.versions["overdue_standard_v1"].kind == NoticeKind.OVERDUE

    def test_raises_on_invalid_yaml(self, tmp_path: Path) -> None:
        (tmp_path / "notice_versions.yaml").write_text(
            "key: [unclosed", encoding="utf-8"
        )
        with pytest.raises(ValueError, match="invalid YAML"):
            load_catalog(tmp_path)

    def test_raises_missing_schema_version(self, tmp_path: Path) -> None:
        _write_catalog(tmp_path, {
            "default_version": "v1",
            "default_language": "en",
            "versions": {"v1": {"kind": "overdue"}},
        })
        with pytest.raises(ValueError, match="schema_version"):
            load_catalog(tmp_path)

    def test_raises_missing_default_version(self, tmp_path: Path) -> None:
        _write_catalog(tmp_path, {
            "schema_version": 1,
            "default_language": "en",
            "versions": {"v1": {"kind": "overdue"}},
        })
        with pytest.raises(ValueError, match="default_version"):
            load_catalog(tmp_path)

    def test_raises_empty_default_language(self, tmp_path: Path) -> None:
        _write_catalog(tmp_path, {
            "schema_version": 1,
            "default_version": "v1",
            "default_language": "",
            "versions": {"v1": {"kind": "overdue"}},
        })
        with pytest.raises(ValueError, match="default_language"):
            load_catalog(tmp_path)

    def test_raises_unknown_kind(self, tmp_path: Path) -> None:
        _write_catalog(tmp_path, {
            "schema_version": 1,
            "default_version": "v1",
            "default_language": "en",
            "versions": {"v1": {"kind": "unknown_kind"}},
        })
        with pytest.raises(ValueError, match="invalid kind"):
            load_catalog(tmp_path)

    def test_raises_default_version_not_in_versions(self, tmp_path: Path) -> None:
        _write_catalog(tmp_path, {
            "schema_version": 1,
            "default_version": "missing_version",
            "default_language": "en",
            "versions": {"v1": {"kind": "overdue"}},
        })
        with pytest.raises(ValueError, match="default_version.*not in versions"):
            load_catalog(tmp_path)

    def test_raises_empty_version_id(self, tmp_path: Path) -> None:
        p = tmp_path / "notice_versions.yaml"
        # Write raw YAML with an empty-string key manually
        p.write_text(
            "schema_version: 1\ndefault_version: ''\ndefault_language: en\n"
            "versions:\n  '': {kind: overdue}\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError):
            load_catalog(tmp_path)

    def test_all_notice_kinds_accepted(self, tmp_path: Path) -> None:
        _write_catalog(tmp_path, {
            "schema_version": 1,
            "default_version": "overdue_v1",
            "default_language": "fr",
            "versions": {
                "overdue_v1": {"kind": "overdue"},
                "affirmative_v1": {"kind": "affirmative"},
                "informational_v1": {"kind": "informational"},
            },
        })
        catalog = load_catalog(tmp_path)
        assert catalog is not None
        assert catalog.versions["overdue_v1"].kind == NoticeKind.OVERDUE
        assert catalog.versions["affirmative_v1"].kind == NoticeKind.AFFIRMATIVE
        assert catalog.versions["informational_v1"].kind == NoticeKind.INFORMATIONAL

    def test_explicit_requires_field_is_loaded(self, tmp_path: Path) -> None:
        _write_catalog(tmp_path, {
            "schema_version": 1,
            "default_version": "v1",
            "default_language": "en",
            "versions": {"v1": {"kind": "overdue", "requires": "any"}},
        })
        catalog = load_catalog(tmp_path)
        assert catalog is not None
        assert catalog.versions["v1"].requires == "any"

    def test_omitted_requires_falls_back_to_kind_default(self, tmp_path: Path) -> None:
        _write_catalog(tmp_path, {
            "schema_version": 1,
            "default_version": "overdue_v1",
            "default_language": "en",
            "versions": {
                "overdue_v1": {"kind": "overdue"},
                "affirmative_v1": {"kind": "affirmative"},
                "info_v1": {"kind": "informational"},
            },
        })
        catalog = load_catalog(tmp_path)
        assert catalog is not None
        assert catalog.versions["overdue_v1"].requires == "has_overdue"
        assert catalog.versions["affirmative_v1"].requires == "no_overdue"
        assert catalog.versions["info_v1"].requires == "any"

    def test_raises_on_unknown_requires_value(self, tmp_path: Path) -> None:
        _write_catalog(tmp_path, {
            "schema_version": 1,
            "default_version": "v1",
            "default_language": "en",
            "versions": {"v1": {"kind": "overdue", "requires": "no_such_rule"}},
        })
        with pytest.raises(ValueError, match="unknown requires"):
            load_catalog(tmp_path)


# ---------------------------------------------------------------------------
# validate_eligibility
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestValidateEligibility:
    def test_overdue_passes_with_vaccines_due(self) -> None:
        client = _client(["Measles", "Polio"])
        resolved = _resolved(NoticeKind.OVERDUE)
        validate_eligibility(client, resolved, _make_catalog())

    def test_overdue_raises_with_none_vaccines_due(self) -> None:
        client = _client(None)
        resolved = _resolved(NoticeKind.OVERDUE)
        with pytest.raises(ValueError, match="C001"):
            validate_eligibility(client, resolved, _make_catalog())

    def test_overdue_raises_with_empty_vaccines_due(self) -> None:
        client = _client([])
        resolved = _resolved(NoticeKind.OVERDUE)
        with pytest.raises(ValueError, match="C001"):
            validate_eligibility(client, resolved, _make_catalog())

    def test_affirmative_passes_with_no_vaccines_due(self) -> None:
        client = _client(None)
        resolved = _resolved(NoticeKind.AFFIRMATIVE, "affirmative_schedule_v1")
        validate_eligibility(client, resolved, _make_catalog())

    def test_affirmative_passes_with_empty_vaccines_due(self) -> None:
        client = _client([])
        resolved = _resolved(NoticeKind.AFFIRMATIVE, "affirmative_schedule_v1")
        validate_eligibility(client, resolved, _make_catalog())

    def test_affirmative_raises_with_non_empty_vaccines_due(self) -> None:
        client = _client(["Measles"])
        resolved = _resolved(NoticeKind.AFFIRMATIVE, "affirmative_schedule_v1")
        with pytest.raises(ValueError, match="C001"):
            validate_eligibility(client, resolved, _make_catalog())

    def test_informational_passes_regardless_of_vaccines_due(self) -> None:
        client_with = _client(["Measles"])
        client_without = _client(None)
        resolved = _resolved(NoticeKind.INFORMATIONAL, "info_v1")
        validate_eligibility(client_with, resolved, _make_catalog())
        validate_eligibility(client_without, resolved, _make_catalog())

    def test_error_message_contains_client_id_not_name(self) -> None:
        client = _client([])
        client.client_id = "SENSITIVE_CLIENT_001"
        client.full_name = "John Smith"
        resolved = _resolved(NoticeKind.OVERDUE)
        with pytest.raises(ValueError) as exc_info:
            validate_eligibility(client, resolved, _make_catalog())
        assert "SENSITIVE_CLIENT_001" in str(exc_info.value)
        assert "John Smith" not in str(exc_info.value)

    def test_error_message_includes_rule_name(self) -> None:
        client = _client([])
        resolved = _resolved(NoticeKind.OVERDUE)
        with pytest.raises(ValueError, match="has_overdue"):
            validate_eligibility(client, resolved, _make_catalog())

    def test_explicit_any_rule_overrides_kind_default(self) -> None:
        # An overdue-kind version with requires=any accepts clients with no vaccines due.
        catalog = NoticeVersionCatalog(
            schema_version=1,
            default_version="overdue_open_v1",
            default_language="en",
            versions={
                "overdue_open_v1": NoticeVersion(
                    version_id="overdue_open_v1", kind=NoticeKind.OVERDUE, requires="any"
                ),
            },
        )
        client = _client(None)
        resolved = _resolved(NoticeKind.OVERDUE, "overdue_open_v1")
        validate_eligibility(client, resolved, catalog)  # should not raise


# ---------------------------------------------------------------------------
# ELIGIBILITY_RULES registry
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestEligibilityRules:
    def test_has_overdue_true_when_list_non_empty(self) -> None:
        client = _client(["Measles"])
        assert ELIGIBILITY_RULES["has_overdue"](client) is True

    def test_has_overdue_false_when_list_empty(self) -> None:
        assert ELIGIBILITY_RULES["has_overdue"](_client([])) is False
        assert ELIGIBILITY_RULES["has_overdue"](_client(None)) is False

    def test_no_overdue_true_when_list_empty(self) -> None:
        assert ELIGIBILITY_RULES["no_overdue"](_client([])) is True
        assert ELIGIBILITY_RULES["no_overdue"](_client(None)) is True

    def test_no_overdue_false_when_list_non_empty(self) -> None:
        assert ELIGIBILITY_RULES["no_overdue"](_client(["Polio"])) is False

    def test_any_always_true(self) -> None:
        assert ELIGIBILITY_RULES["any"](_client(["Measles"])) is True
        assert ELIGIBILITY_RULES["any"](_client(None)) is True
        assert ELIGIBILITY_RULES["any"](_client([])) is True
