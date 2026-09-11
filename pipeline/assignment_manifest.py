"""Assignment manifest loading, reconciliation, and preflight reporting.

A manifest is a JSON array that maps client IDs to notice versions, languages,
and optional experiment metadata. This module loads manifests, reconciles them
against the preprocessed cohort, and produces a ReconciliationResult that the
caller uses to decide whether to halt or continue.

None of the functions here raise on policy violations - they populate the result
and the caller (build_preprocess_result / orchestrator) decides what to do.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

from .notice_versioning import NoticeVersionCatalog, ResolvedNotice, validate_eligibility

if TYPE_CHECKING:
    from .data_models import ClientRecord


@dataclasses.dataclass(frozen=True)
class ManifestRow:
    client_id: str
    notice_version: str
    language: Optional[str]
    experiment_id: Optional[str]
    experiment_arm: Optional[str]


@dataclasses.dataclass(frozen=True)
class ReconciliationResult:
    # counts_by_version keys are "version_id (lang)" composite strings — matches
    # the print_preflight_summary display format exactly.
    counts_by_version: Dict[str, int]
    counts_by_language: Dict[str, int]
    missing_clients: List[str]          # in cohort, not in manifest
    extra_rows: List[str]               # in manifest, not in cohort
    duplicate_manifest_ids: List[str]   # always empty; duplicates caught by load_manifest
    unknown_versions: List[str]         # version IDs not in catalog (deduplicated)
    missing_language_clients: List[str] # client_ids whose manifest row has no language
    eligibility_conflicts: List[str]    # client_ids failing eligibility
    default_language: str               # catalog.default_language, used by print summary


def load_manifest(path: Path) -> Dict[str, ManifestRow]:
    """Read a JSON assignment manifest and return a dict keyed by client_id.

    Raises ValueError for:

    - content that is not a JSON array
    - rows missing client_id or notice_version
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

        notice_version = item.get("notice_version")
        if not notice_version or not isinstance(notice_version, str):
            raise ValueError(
                f"Assignment manifest row {idx} (client_id={client_id!r}) is missing "
                f"required field 'notice_version': {path}"
            )

        if client_id in seen:
            raise ValueError(
                f"Assignment manifest has duplicate client_id {client_id!r} "
                f"(first at row {seen[client_id]}, again at row {idx}): {path}"
            )
        seen[client_id] = idx

        language = item.get("language") or None
        experiment_id = item.get("experiment_id") or None
        experiment_arm = item.get("experiment_arm") or None

        result[client_id] = ManifestRow(
            client_id=client_id,
            notice_version=notice_version,
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

    Does NOT raise - all policy decisions are left to the caller.
    """
    cohort_ids = {c.client_id for c in clients}
    manifest_ids = set(manifest.keys())

    counts_by_version: Dict[str, int] = {}
    counts_by_language: Dict[str, int] = {}
    missing_clients: List[str] = []
    extra_rows: List[str] = sorted(manifest_ids - cohort_ids)
    unknown_versions_set: set[str] = set()
    missing_language_clients: List[str] = []
    eligibility_conflicts: List[str] = []

    for client in clients:
        cid = client.client_id
        row = manifest.get(cid)

        if row is not None:
            version = row.notice_version

            if version not in catalog.versions:
                unknown_versions_set.add(version)
                continue

            lang = row.language
            if not lang:
                lang = catalog.default_language
                missing_language_clients.append(cid)

            catalog_version = catalog.versions[version]
            resolved = ResolvedNotice(
                notice_version=version,
                notice_kind=catalog_version.kind.value,
                language=lang,
                experiment_id=row.experiment_id,
                experiment_arm=row.experiment_arm,
                assignment_source="manifest",
            )
            try:
                validate_eligibility(client, resolved, catalog)
            except ValueError:
                eligibility_conflicts.append(cid)
                continue

            composite_key = f"{version} ({lang})"
            counts_by_version[composite_key] = counts_by_version.get(composite_key, 0) + 1
            counts_by_language[lang] = counts_by_language.get(lang, 0) + 1

        else:
            if allow_unassigned:
                version = catalog.default_version
                lang = catalog.default_language
                catalog_version = catalog.versions[version]
                resolved = ResolvedNotice(
                    notice_version=version,
                    notice_kind=catalog_version.kind.value,
                    language=lang,
                    experiment_id=None,
                    experiment_arm=None,
                    assignment_source="default",
                )
                try:
                    validate_eligibility(client, resolved, catalog)
                except ValueError:
                    eligibility_conflicts.append(cid)
                    continue

                composite_key = f"{version} ({lang})"
                counts_by_version[composite_key] = (
                    counts_by_version.get(composite_key, 0) + 1
                )
                counts_by_language[lang] = counts_by_language.get(lang, 0) + 1
            else:
                missing_clients.append(cid)

    return ReconciliationResult(
        counts_by_version=counts_by_version,
        counts_by_language=counts_by_language,
        missing_clients=missing_clients,
        extra_rows=extra_rows,
        duplicate_manifest_ids=[],
        unknown_versions=sorted(unknown_versions_set),
        missing_language_clients=missing_language_clients,
        eligibility_conflicts=eligibility_conflicts,
        default_language=catalog.default_language,
    )


def has_errors(result: ReconciliationResult, extra_manifest_rows: str) -> bool:
    """Return True if result contains anything that should halt the pipeline.

    The extra_manifest_rows policy ("error" | "warn") governs whether extra rows
    count as an error. All other error categories are always fatal.
    """
    if result.missing_clients:
        return True
    if result.unknown_versions:
        return True
    if result.eligibility_conflicts:
        return True
    if result.extra_rows and extra_manifest_rows == "error":
        return True
    return False


def print_preflight_summary(result: ReconciliationResult) -> None:
    """Print the assignment preflight summary to stdout.

    No PII is emitted - only client counts, version IDs, and language codes.
    """
    total = sum(result.counts_by_version.values()) + len(result.missing_clients)
    print("Assignment mode: manifest")
    print(f"Clients: {total}")
    for composite_key, count in sorted(result.counts_by_version.items()):
        print(f"  {composite_key}: {count}")
    print(f"Missing clients (no manifest row): {len(result.missing_clients)}")
    print(f"Extra manifest rows (not in cohort): {len(result.extra_rows)}")
    print(f"Unknown versions: {len(result.unknown_versions)}")
    print(
        f"Clients missing language (falling back to default "
        f"'{result.default_language}'): {len(result.missing_language_clients)}"
    )
    print(f"Eligibility conflicts: {len(result.eligibility_conflicts)}")
