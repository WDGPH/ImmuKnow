"""Notice versioning models and catalog loader for the immunization pipeline.

Supports the optional assignment manifest feature. When notice_versions.yaml is
absent from the config directory the feature is off and all callers receive None
from load_catalog(), leaving fixed-mode behaviour unchanged.
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, Optional

import yaml

if TYPE_CHECKING:
    from .data_models import ClientRecord


class NoticeKind(str, Enum):
    OVERDUE = "overdue"
    AFFIRMATIVE = "affirmative"
    INFORMATIONAL = "informational"


EligibilityRule = Callable[["ClientRecord"], bool]

ELIGIBILITY_RULES: Dict[str, EligibilityRule] = {
    "has_overdue": lambda c: bool(c.vaccines_due_list),
    "no_overdue":  lambda c: not c.vaccines_due_list,
    "any":         lambda _: True,
}

# Fallback rule used when a version entry omits the `requires` field.
_KIND_DEFAULT_RULE: Dict[NoticeKind, str] = {
    NoticeKind.OVERDUE:       "has_overdue",
    NoticeKind.AFFIRMATIVE:   "no_overdue",
    NoticeKind.INFORMATIONAL: "any",
}


@dataclasses.dataclass(frozen=True)
class NoticeVersion:
    version_id: str
    kind: NoticeKind
    requires: str  # key into ELIGIBILITY_RULES


@dataclasses.dataclass(frozen=True)
class NoticeVersionCatalog:
    schema_version: int
    default_version: str
    default_language: str
    versions: Dict[str, NoticeVersion]


@dataclasses.dataclass(frozen=True)
class ResolvedNotice:
    notice_version: str
    notice_kind: str  # NoticeKind.value
    language: str
    experiment_id: Optional[str]
    experiment_arm: Optional[str]
    assignment_source: str  # "manifest" | "default"


def load_catalog(config_dir: Path) -> Optional[NoticeVersionCatalog]:
    """Load notice version catalog from config_dir/notice_versions.yaml.

    Returns None when the file is absent (feature stays off).
    Raises ValueError with an actionable message if the file exists but is invalid.
    """
    catalog_path = config_dir / "notice_versions.yaml"
    if not catalog_path.exists():
        return None

    try:
        raw = yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"notice_versions.yaml is invalid YAML: {exc}") from exc

    if "schema_version" not in raw:
        raise ValueError(
            "notice_versions.yaml is missing required field: schema_version"
        )

    if "default_version" not in raw:
        raise ValueError(
            "notice_versions.yaml is missing required field: default_version"
        )

    default_language = raw.get("default_language")
    if not default_language or not isinstance(default_language, str):
        raise ValueError(
            "notice_versions.yaml: default_language must be a non-empty string"
        )

    raw_versions = raw.get("versions", {})
    if not isinstance(raw_versions, dict):
        raise ValueError("notice_versions.yaml: versions must be a mapping")

    versions: Dict[str, NoticeVersion] = {}
    for version_id, version_data in raw_versions.items():
        if not isinstance(version_id, str) or not version_id.strip():
            raise ValueError(
                f"notice_versions.yaml: version ID must be a non-empty string, "
                f"got {version_id!r}"
            )
        kind_raw = (
            version_data.get("kind") if isinstance(version_data, dict) else None
        )
        try:
            kind = NoticeKind(kind_raw)
        except (ValueError, KeyError):
            valid = ", ".join(k.value for k in NoticeKind)
            raise ValueError(
                f"notice_versions.yaml: version {version_id!r} has invalid kind "
                f"{kind_raw!r}. Valid kinds: {valid}"
            )

        requires_raw = (
            version_data.get("requires") if isinstance(version_data, dict) else None
        )
        if requires_raw is None:
            requires = _KIND_DEFAULT_RULE[kind]
        elif requires_raw not in ELIGIBILITY_RULES:
            valid_rules = ", ".join(sorted(ELIGIBILITY_RULES))
            raise ValueError(
                f"notice_versions.yaml: version {version_id!r} has unknown requires "
                f"{requires_raw!r}. Valid rules: {valid_rules}"
            )
        else:
            requires = requires_raw

        versions[version_id] = NoticeVersion(
            version_id=version_id, kind=kind, requires=requires
        )

    default_version = raw["default_version"]
    if default_version not in versions:
        raise ValueError(
            f"notice_versions.yaml: default_version {default_version!r} is not in "
            f"versions. Available versions: {', '.join(sorted(versions.keys()))}"
        )

    return NoticeVersionCatalog(
        schema_version=raw["schema_version"],
        default_version=default_version,
        default_language=default_language,
        versions=versions,
    )


def validate_eligibility(
    client_record: "ClientRecord",
    resolved: ResolvedNotice,
    catalog: NoticeVersionCatalog,
) -> None:
    """Validate that the client satisfies the eligibility rule for the assigned version.

    Raises ValueError containing client_id (no name or DOB) if the rule is not met.
    """
    version = catalog.versions[resolved.notice_version]
    rule = ELIGIBILITY_RULES[version.requires]
    if not rule(client_record):
        raise ValueError(
            f"Eligibility conflict for client {client_record.client_id}: "
            f"assigned notice version '{resolved.notice_version}' "
            f"(rule: '{version.requires}') but client does not satisfy it. "
            "Check the manifest assignment or the client's overdue disease data."
        )
