"""Notice versioning models and catalog loader for the immunization pipeline.

Supports the optional assignment manifest feature. When notice_versions.yaml is
absent from the config directory the feature is off and all callers receive None
from load_catalog(), leaving fixed-mode behaviour unchanged.
"""

from __future__ import annotations

import dataclasses
import re
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, Optional

import yaml

from .enums import Language

if TYPE_CHECKING:
    from .data_models import ClientRecord


class NoticeKind(str, Enum):
    OVERDUE = "overdue"
    AFFIRMATIVE = "affirmative"
    INFORMATIONAL = "informational"


EligibilityRule = Callable[["ClientRecord"], bool]

ELIGIBILITY_RULES: Dict[str, EligibilityRule] = {
    "has_overdue": lambda c: bool(c.overdue_diseases),
    "no_overdue": lambda c: not c.overdue_diseases,
    "any": lambda _: True,
}

# Fallback rule used when a version entry omits the `requires` field.
_KIND_DEFAULT_RULE: Dict[NoticeKind, str] = {
    NoticeKind.OVERDUE: "has_overdue",
    NoticeKind.AFFIRMATIVE: "no_overdue",
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
    version_id: str
    notice_kind: str  # NoticeKind.value
    language: str
    experiment_id: Optional[str]
    experiment_arm: Optional[str]
    assignment_source: str  # "manifest" | "default"


def validate_version_id(version_id: str) -> None:
    """Reject version identifiers that cannot safely name a template entry point."""
    if not isinstance(version_id, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_-]*", version_id
    ):
        raise ValueError(f"Unsafe notice version identifier: {version_id!r}")


def attach_notice(client: "ClientRecord", resolved: ResolvedNotice) -> "ClientRecord":
    """Attach one resolved notice while preserving unrelated client metadata."""
    Language.from_string(resolved.language)
    validate_version_id(resolved.version_id)
    return dataclasses.replace(
        client,
        language=resolved.language,
        version_id=resolved.version_id,
        metadata={
            **client.metadata,
            "notice_kind": resolved.notice_kind,
            "experiment_id": resolved.experiment_id,
            "experiment_arm": resolved.experiment_arm,
            "assignment_source": resolved.assignment_source,
        },
    )


def load_catalog(config_dir: Path) -> Optional[NoticeVersionCatalog]:
    """Load notice version catalog from config_dir/notice_versions.yaml.

    Returns None when the file is absent (feature stays off).
    Raises ValueError with an actionable message if the file exists but is invalid.
    """
    catalog_path = config_dir / "notice_versions.yaml"
    if not catalog_path.exists():
        return None

    try:
        raw = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"notice_versions.yaml is invalid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValueError("notice_versions.yaml must be a mapping")

    if "schema_version" not in raw:
        raise ValueError(
            "notice_versions.yaml is missing required field: schema_version"
        )
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise ValueError(
            "notice_versions.yaml: schema_version must be the supported integer 1"
        )

    if "default_version" not in raw:
        raise ValueError(
            "notice_versions.yaml is missing required field: default_version"
        )

    default_version = raw["default_version"]
    if not isinstance(default_version, str) or not default_version:
        raise ValueError(
            "notice_versions.yaml: default_version must be a non-empty string"
        )
    validate_version_id(default_version)

    default_language = raw.get("default_language")
    if not isinstance(default_language, str) or not default_language:
        raise ValueError(
            "notice_versions.yaml: default_language must be a non-empty string"
        )
    try:
        default_language = Language.from_string(default_language).value
    except ValueError as exc:
        raise ValueError(
            f"notice_versions.yaml: invalid default_language {default_language!r}: {exc}"
        ) from exc

    raw_versions = raw.get("versions")
    if not isinstance(raw_versions, dict) or not raw_versions:
        raise ValueError("notice_versions.yaml: versions must be a non-empty mapping")

    versions: Dict[str, NoticeVersion] = {}
    for version_id, version_data in raw_versions.items():
        if not isinstance(version_id, str) or not version_id.strip():
            raise ValueError(
                f"notice_versions.yaml: version ID must be a non-empty string, "
                f"got {version_id!r}"
            )
        validate_version_id(version_id)
        if not isinstance(version_data, dict):
            raise ValueError(
                f"notice_versions.yaml: version {version_id!r} must be a mapping"
            )
        kind_raw = version_data.get("kind")
        try:
            kind = NoticeKind(kind_raw)
        except (ValueError, KeyError):
            valid = ", ".join(k.value for k in NoticeKind)
            raise ValueError(
                f"notice_versions.yaml: version {version_id!r} has invalid kind "
                f"{kind_raw!r}. Valid kinds: {valid}"
            )

        requires_raw = version_data.get("requires")
        if requires_raw is None:
            requires = _KIND_DEFAULT_RULE[kind]
        elif not isinstance(requires_raw, str) or requires_raw not in ELIGIBILITY_RULES:
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
    version = catalog.versions[resolved.version_id]
    rule = ELIGIBILITY_RULES[version.requires]
    if not rule(client_record):
        raise ValueError(
            f"Eligibility conflict for client {client_record.client_id}: "
            f"assigned notice version '{resolved.version_id}' "
            f"(rule: '{version.requires}') but client does not satisfy it. "
            "Check the manifest assignment or the client's overdue disease data."
        )
