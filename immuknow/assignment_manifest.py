"""Read explicit assignments and reconcile each source row without choosing notices.

Malformed shared JSON stops setup. Missing files and ambiguous assignments
produce row failures that reject the input file; unknown applicability and
conflicting facts warn.
"""

from __future__ import annotations

import dataclasses
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from .structured_input import read_json

from .version_notices import (
    NoticeVersionCatalog,
    ResolvedNotice,
    template_identity,
    validate_eligibility,
)

if TYPE_CHECKING:
    from .data_models import ClientRecord


@dataclasses.dataclass(frozen=True)
class ManifestRow:
    client_id: str
    version_id: str
    language: str
    experiment_id: str | None
    experiment_arm: str | None
    assignment_source: str = "manifest"
    error: str | None = None
    error_kind: str = "missing_template"
    template: str | None = None


@dataclasses.dataclass(frozen=True)
class AssignmentFinding:
    kind: str
    client_id: str
    version_id: str | None
    reason: str
    row_key: str | None = None
    status: Literal["warn", "fail"] = "fail"


@dataclasses.dataclass(frozen=True)
class ReconciliationResult:
    counts_by_version: dict[str, int]
    counts_by_language: dict[str, int]
    findings: list[AssignmentFinding]
    resolved_notices: dict[str, ResolvedNotice] = dataclasses.field(
        default_factory=dict
    )


def load_manifest(path: Path, template_dir: Path) -> dict[str, ManifestRow]:
    """Read UTF-8 JSON; preserve duplicate assignments as ambiguous, never select one."""
    raw = read_json(path)
    if not isinstance(raw, list):
        raise ValueError("Assignment manifest must be a JSON array")
    result: dict[str, ManifestRow] = {}
    for index, item in enumerate(raw, 1):
        if not isinstance(item, dict):
            raise ValueError(f"Assignment manifest row {index} must be an object")
        if set(item) - {
            "client_id",
            "template",
            "experiment_id",
            "experiment_arm",
            "version_id",
            "language",
        }:
            raise ValueError(f"Assignment manifest row {index} contains unknown fields")
        for field in ("client_id", "template"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise ValueError(
                    f"Assignment manifest row {index}: {field} must be a nonempty string"
                )
        for field in ("experiment_id", "experiment_arm"):
            if field in item and not isinstance(item[field], str):
                raise ValueError(
                    f"Assignment manifest row {index}: {field} must be a string"
                )
        if "version_id" in item or "language" in item:
            raise ValueError(
                "Version and language are derived from the template filename"
            )
        client_id, template = item["client_id"].strip(), item["template"].strip()
        error = None
        version, language = "", ""
        try:
            if Path(template).name != template or "\\" in template:
                raise ValueError(
                    "Template must be a basename inside the selected template tree"
                )
            version, language = template_identity(template_dir / template)
        except (ValueError, FileNotFoundError) as exc:
            error = str(exc)
        row = ManifestRow(
            client_id,
            version,
            language,
            item.get("experiment_id"),
            item.get("experiment_arm"),
            error=error,
            template=template,
        )
        if client_id in result:
            row = dataclasses.replace(
                row,
                error="Multiple manifest rows assign this client ID",
                error_kind="ambiguous_assignment",
            )
        result[client_id] = row
    return result


def reconcile(
    clients: list[ClientRecord],
    manifest: dict[str, ManifestRow],
    catalog: NoticeVersionCatalog,
) -> ReconciliationResult:
    """Return row-keyed selections and findings; preserve every explicit valid selection."""
    counts_by_version: dict[str, int] = {}
    counts_by_language: dict[str, int] = {}
    cohort_counts = Counter(c.client_id for c in clients if c.client_id)
    findings = [
        AssignmentFinding(
            "extra_manifest_row",
            cid,
            manifest[cid].version_id,
            "Manifest row has no matching source client",
            status="warn",
        )
        for cid in sorted(set(manifest) - {c.client_id for c in clients})
    ]
    resolved_notices: dict[str, ResolvedNotice] = {}
    for client in clients:
        cid, key = client.client_id, client.sequence
        row = manifest.get(cid)
        if cid and cohort_counts[cid] > 1:
            findings.append(
                AssignmentFinding(
                    "duplicate_client_id",
                    cid,
                    None,
                    "Duplicate source client ID prevents an unambiguous notice",
                    key,
                )
            )
            continue
        if row is None:
            findings.append(
                AssignmentFinding(
                    "missing_assignment",
                    cid,
                    None,
                    "Source row has no explicit notice assignment",
                    key,
                )
            )
            continue
        if row.error:
            findings.append(
                AssignmentFinding(row.error_kind, cid, row.version_id, row.error, key)
            )
            continue
        if client.version_id and client.version_id != row.version_id:
            findings.append(
                AssignmentFinding(
                    "version_conflict",
                    cid,
                    row.version_id,
                    "Input version conflicts with the explicit assignment; selected template retained",
                    key,
                    "warn",
                )
            )
        version = catalog.versions.get(row.version_id)
        resolved = ResolvedNotice(
            row.version_id,
            version.kind.value if version else "unknown",
            row.language,
            row.experiment_id,
            row.experiment_arm,
            row.assignment_source,
        )
        if version is None:
            findings.append(
                AssignmentFinding(
                    "check_unavailable",
                    cid,
                    row.version_id,
                    "No registered applicability check for the selected version",
                    key,
                    "warn",
                )
            )
        else:
            try:
                validate_eligibility(client, resolved, catalog)
            except ValueError as exc:
                findings.append(
                    AssignmentFinding(
                        "eligibility_conflict",
                        cid,
                        row.version_id,
                        str(exc),
                        key,
                        "warn",
                    )
                )
        resolved_notices[key] = resolved
        label = f"{row.version_id} ({row.language})"
        counts_by_version[label] = counts_by_version.get(label, 0) + 1
        counts_by_language[row.language] = counts_by_language.get(row.language, 0) + 1
    return ReconciliationResult(
        counts_by_version, counts_by_language, findings, resolved_notices
    )


def print_preflight_summary(result: ReconciliationResult) -> None:
    """Summarize counts without printing client identifiers to shared output."""
    print("Notice assignments")
    for identity, count in sorted(result.counts_by_version.items()):
        print(f"  {identity}: {count}")
    for status in ("warn", "fail"):
        print(f"  {status}: {sum(f.status == status for f in result.findings)}")
