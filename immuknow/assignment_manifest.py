"""Assignment manifest loading, reconciliation, and preflight reporting.

A manifest is a JSON array that maps client IDs to notice versions, languages,
and optional experiment metadata. This module loads manifests, reconciles them
against the preprocessed cohort, and produces a ReconciliationResult that the
caller uses to decide whether to halt or continue.

Malformed manifests raise immediately; assignment conflicts become structured findings.
Reconciliation records missing assignments, unknown versions, and eligibility
conflicts for the caller to apply the selected policy.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

from .enums import Language
from .notice_versioning import (
    NoticeVersionCatalog,
    ResolvedNotice,
    validate_eligibility,
    validate_version_id,
)

if TYPE_CHECKING:
    from .data_models import ClientRecord


@dataclasses.dataclass(frozen=True)
class ManifestRow:
    client_id: str
    version_id: str
    language: Optional[str]
    experiment_id: Optional[str]
    experiment_arm: Optional[str]


@dataclasses.dataclass(frozen=True)
class AssignmentFinding:
    kind: str
    client_id: str
    version_id: Optional[str]
    reason: str


@dataclasses.dataclass(frozen=True)
class ReconciliationResult:
    counts_by_version: Dict[str, int]
    counts_by_language: Dict[str, int]
    findings: List[AssignmentFinding]
    default_language: str
    resolved_notices: Dict[str, ResolvedNotice] = dataclasses.field(
        default_factory=dict
    )


class ReconciliationError(ValueError):
    """Preflight failure with the full client-linked findings for run-local reporting."""

    def __init__(self, result: ReconciliationResult):
        self.result = result
        super().__init__("Manifest preflight failed; inspect assignment findings")


def load_manifest(path: Path) -> Dict[str, ManifestRow]:
    """Read a JSON assignment manifest and return a dict keyed by client_id.

    Raises ValueError for:

    - content that is not a JSON array
    - rows missing client_id or version_id
    - duplicate client_id entries
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Assignment manifest is not valid JSON: {path}") from exc

    if not isinstance(raw, list):
        raise ValueError(
            f"Assignment manifest must be a JSON array, got {type(raw).__name__}: {path}"
        )

    result: Dict[str, ManifestRow] = {}
    seen: Dict[str, int] = {}  # client_id -> first line index (1-based)

    for idx, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            raise ValueError(
                f"Assignment manifest row {idx} must be an object, "
                f"got {type(item).__name__}: {path}"
            )

        client_id = item.get("client_id")
        if not client_id or not isinstance(client_id, str):
            raise ValueError(
                f"Assignment manifest row {idx} is missing required field 'client_id': {path}"
            )

        version_id = item.get("version_id")
        if version_id is None:
            raise ValueError(
                f"Assignment manifest row {idx} (client_id={client_id!r}) is missing "
                f"required field 'version_id': {path}"
            )
        if not isinstance(version_id, str) or not version_id:
            raise ValueError(
                f"Assignment manifest row {idx} (client_id={client_id!r}) has invalid "
                f"version_id: {version_id!r}: {path}"
            )
        validate_version_id(version_id)

        if client_id in seen:
            raise ValueError(
                f"Assignment manifest has duplicate client_id {client_id!r} "
                f"(first at row {seen[client_id]}, again at row {idx}): {path}"
            )
        seen[client_id] = idx

        language = item.get("language") or None
        if language is not None:
            language = Language.from_string(language).value
        experiment_id = item.get("experiment_id") or None
        experiment_arm = item.get("experiment_arm") or None

        result[client_id] = ManifestRow(
            client_id=client_id,
            version_id=version_id,
            language=language,
            experiment_id=experiment_id,
            experiment_arm=experiment_arm,
        )

    return result


def reconcile(
    clients: "List[ClientRecord]",
    manifest: Dict[str, ManifestRow],
    catalog: NoticeVersionCatalog,
    allow_unassigned: bool,
    extra_manifest_rows: str,  # "error" | "warn"
) -> ReconciliationResult:
    """Reconcile a cohort against a manifest and return a populated ReconciliationResult.

    Assignment and eligibility findings retain the client and reason for policy
    handling and sensitive run-local reporting.
    """
    cohort_ids = {c.client_id for c in clients}
    manifest_ids = set(manifest.keys())

    counts_by_version: Dict[str, int] = {}
    counts_by_language: Dict[str, int] = {}
    findings = [
        AssignmentFinding(
            "extra_manifest_row",
            cid,
            manifest[cid].version_id,
            "Manifest assignment has no matching client in the source cohort",
        )
        for cid in sorted(manifest_ids - cohort_ids)
    ]
    resolved_notices: Dict[str, ResolvedNotice] = {}

    for client in clients:
        cid = client.client_id
        row = manifest.get(cid)

        if row is None and not allow_unassigned:
            findings.append(
                AssignmentFinding(
                    "missing_assignment",
                    cid,
                    client.version_id,
                    "Source client has no manifest assignment; add a row or enable allow_unassigned",
                )
            )
            continue

        input_version = client.version_id
        if row is not None and input_version and input_version != row.version_id:
            findings.append(
                AssignmentFinding(
                    "version_conflict",
                    cid,
                    row.version_id,
                    f"Conflicting input version_id {input_version!r} and manifest version_id {row.version_id!r}",
                )
            )
            continue
        version = row.version_id if row else (input_version or catalog.default_version)
        validate_version_id(version)
        if version not in catalog.versions:
            findings.append(
                AssignmentFinding(
                    "unknown_version",
                    cid,
                    version,
                    f"Assigned version {version!r} is absent from notice_versions.yaml",
                )
            )
            continue
        lang = (row.language if row else None) or catalog.default_language
        lang = Language.from_string(lang).value
        if row and not row.language:
            findings.append(
                AssignmentFinding(
                    "missing_language",
                    cid,
                    version,
                    f"Manifest language is absent; using catalog default {catalog.default_language!r}",
                )
            )
        resolved = ResolvedNotice(
            version_id=version,
            notice_kind=catalog.versions[version].kind.value,
            language=lang,
            experiment_id=row.experiment_id if row else None,
            experiment_arm=row.experiment_arm if row else None,
            assignment_source="manifest"
            if row
            else ("input" if input_version else "default"),
        )
        try:
            validate_eligibility(client, resolved, catalog)
        except ValueError as exc:
            findings.append(
                AssignmentFinding(
                    "eligibility_conflict",
                    cid,
                    version,
                    str(exc),
                )
            )
            continue
        resolved_notices[cid] = resolved
        composite_key = f"{version} ({lang})"
        counts_by_version[composite_key] = counts_by_version.get(composite_key, 0) + 1
        counts_by_language[lang] = counts_by_language.get(lang, 0) + 1

    return ReconciliationResult(
        counts_by_version=counts_by_version,
        counts_by_language=counts_by_language,
        findings=findings,
        default_language=catalog.default_language,
        resolved_notices=resolved_notices,
    )


def has_errors(result: ReconciliationResult, extra_manifest_rows: str) -> bool:
    """Return True if result contains anything that should halt the pipeline.

    The extra_manifest_rows policy ("error" | "warn") governs whether extra rows
    count as an error. All other error categories are always fatal.
    """
    return any(
        finding.kind
        in {
            "missing_assignment",
            "unknown_version",
            "eligibility_conflict",
            "version_conflict",
        }
        or (finding.kind == "extra_manifest_row" and extra_manifest_rows == "error")
        for finding in result.findings
    )


def print_preflight_summary(result: ReconciliationResult) -> None:
    """Print the assignment preflight summary to stdout.

    Findings contain client IDs and must remain in run-local sensitive artifacts.
    """
    total = sum(result.counts_by_version.values()) + sum(
        finding.kind
        in {
            "missing_assignment",
            "unknown_version",
            "eligibility_conflict",
            "version_conflict",
        }
        for finding in result.findings
    )
    print("Assignment mode: manifest")
    print(f"Clients: {total}")
    for composite_key, count in sorted(result.counts_by_version.items()):
        print(f"  {composite_key}: {count}")
    counts = {
        kind: sum(finding.kind == kind for finding in result.findings)
        for kind in (
            "missing_assignment",
            "extra_manifest_row",
            "unknown_version",
            "missing_language",
            "eligibility_conflict",
            "version_conflict",
        )
    }
    print(f"Missing clients (no manifest row): {counts['missing_assignment']}")
    print(f"Extra manifest rows (not in cohort): {counts['extra_manifest_row']}")
    print(f"Unknown versions: {counts['unknown_version']}")
    print(
        f"Clients missing language (falling back to default "
        f"'{result.default_language}'): {counts['missing_language']}"
    )
    print(f"Eligibility conflicts: {counts['eligibility_conflict']}")
    print(f"Explicit version conflicts: {counts['version_conflict']}")
