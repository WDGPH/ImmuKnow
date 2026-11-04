"""Evaluate saved originals and assemble bundles, then replace safely."""

from __future__ import annotations

import csv
import json
import re
import shutil
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any

from pypdf import PageObject, PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from jsonschema import ValidationError

from . import run_report, validation_policy
from .run_lock import run_lock
from .structured_input import parse_json, read_json
from .component_resources import verify_components
from .render_payload import validate_render_payload
from .render_contract import validate_render_report
from .compile_notices import TYPST_VERSION


def bundle_grouping(value: object) -> tuple[str, ...]:
    """Read the delivery grouping fields, including older single-field settings."""
    if value is None or (isinstance(value, str) and value.lower() == "size"):
        return ()
    fields = [value] if isinstance(value, str) else value
    if not isinstance(fields, list) or any(
        not isinstance(field, str) for field in fields
    ):
        raise ValueError(
            "Choose grouping fields from school, board, language, and page_count"
        )
    fields = [field.lower() for field in fields]
    if any(
        field not in {"school", "board", "language", "page_count"} for field in fields
    ):
        raise ValueError(
            "Choose grouping fields from school, board, language, and page_count"
        )
    if len(set(fields)) != len(fields):
        raise ValueError("Each grouping field can be selected only once")
    return tuple(fields)


def _group_values(entry: dict, fields: tuple[str, ...]) -> tuple[str, ...]:
    values = []
    for field in fields:
        if field in ("school", "board"):
            values.append(entry["facts"]["prepared"][field].get("id", "") or "")
        elif field == "language":
            values.append(entry["assignment"]["language"])
        else:
            values.append(str(entry["original"]["pages"]))
    return tuple(values)


def _original_reader(entry: dict, run_dir: Path) -> tuple[PdfReader, dict]:
    """Verify the retained payload binding and PDF bytes before any delivery use."""
    facts = entry["facts"]
    payload_path = (run_dir / facts["path"]).resolve()
    if not payload_path.is_relative_to((run_dir / "facts").resolve()):
        raise ValueError(f"Payload path is outside facts/: {entry['row_key']}")
    payload_bytes = payload_path.read_bytes()
    if sha256(payload_bytes).hexdigest() != facts["sha256"]:
        raise ValueError(f"Saved notice payload changed: {entry['row_key']}")
    payload = parse_json(payload_bytes, label="Saved notice payload")
    try:
        validate_render_payload(payload)
    except ValidationError as exc:
        raise ValueError(
            f"Saved notice payload does not match the supported format: {entry['row_key']}"
        ) from exc
    if (
        payload.get("row_key") != entry["row_key"]
        or payload.get("client_id") != entry["client_id"]
        or any(
            payload[key] != entry["assignment"][key]
            for key in ("template", "version_id", "language")
        )
    ):
        raise ValueError(
            f"Saved payload does not belong to this source row: {entry['row_key']}"
        )
    original = entry["original"]
    path = (run_dir / original["path"]).resolve()
    if not path.is_relative_to((run_dir / "originals").resolve()):
        raise ValueError(f"Original path is outside originals/: {entry['row_key']}")
    content = path.read_bytes()
    if sha256(content).hexdigest() != original["sha256"]:
        raise ValueError(f"Original PDF hash changed: {entry['row_key']}")
    reader = PdfReader(BytesIO(content))
    if reader.is_encrypted or not reader.pages:
        raise ValueError(
            f"Original PDF must be readable and unencrypted: {entry['row_key']}"
        )
    if len(reader.pages) != original["pages"]:
        raise ValueError(f"Original PDF page count changed: {entry['row_key']}")
    return reader, payload


def _routes(
    run_dir: Path,
    record: dict,
    entries: list[dict],
    group_by: tuple[str, ...],
    attempt: dict,
    accept: list[str],
    reason: str | None,
    withheld: list[str],
    resolved: dict,
) -> list[tuple[dict, dict]]:
    """Evaluate each original before deciding membership, retaining every result."""
    known_rows = {entry["row_key"] for entry in record["entries"]}
    if any(row not in known_rows for row in withheld) or len(set(withheld)) != len(
        withheld
    ):
        raise ValueError("Withheld rows must be distinct source row keys from this run")
    evaluations = {}
    for entry in entries:
        reader, payload = _original_reader(entry, run_dir)
        observations = deepcopy(entry["checks"])
        summary = entry.get("render_summary")
        try:
            if summary is None:
                raise ValueError("Required render evidence is missing")
            validate_render_report(summary, payload)
            if summary["page_count"] != len(reader.pages):
                raise ValueError(
                    "Render evidence page count differs from the original PDF"
                )
        except ValueError as exc:
            observations.append(
                {
                    "code": "render.evidence_failed",
                    "stage": "render",
                    "status": "fail",
                    "message": str(exc),
                }
            )
        else:
            for check in summary["checks"]:
                if check not in observations:
                    observations.append(deepcopy(check))
        facts = entry["facts"]["prepared"]
        for field in group_by:
            if field in ("school", "board") and not facts[field].get("id"):
                observations.append(
                    {
                        "code": "delivery.group_unknown",
                        "stage": "delivery",
                        "status": "warn",
                        "message": f"Missing {field} identifier; delivery grouping uses Unknown",
                        "measurements": {"group_by": field},
                    }
                )
        evaluation = validation_policy.evaluate_original(
            record, entry, observations, resolved[entry["row_key"]]
        )
        evaluations[entry["row_key"]] = evaluation
    attempt["evaluations"] = {
        key: value.to_dict() for key, value in evaluations.items()
    }
    validation_policy.accept_warnings(record, evaluations, accept, reason)
    record["withheld_rows"] = list(withheld)
    withheld_set = set(withheld)
    acceptances_by_row: dict[str, list[dict]] = {}
    for acceptance in record.get("warning_acceptances", []):
        acceptances_by_row.setdefault(acceptance["row_key"], []).append(acceptance)
    return [
        (
            entry,
            validation_policy.route_original(
                {
                    **record,
                    "warning_acceptances": acceptances_by_row.get(entry["row_key"], []),
                },
                evaluations[entry["row_key"]],
                withheld=entry["row_key"] in withheld_set,
            ),
        )
        for entry in entries
    ]


def _page_hash(page: PageObject) -> str:
    """Compare complete page copies after writing, independent of PDF object numbers."""
    writer = PdfWriter()
    writer.add_page(page)
    # Compare copies independently of the source or bundle header.
    writer.pdf_header = "%PDF-1.7"
    stream = BytesIO()
    writer.write(stream)
    return sha256(stream.getvalue()).hexdigest()


def _assemble(
    routed: list[tuple[dict, dict]],
    next_dir: Path,
    group_by: tuple[str, ...],
    size: int,
    attempt: dict,
) -> None:
    groups: dict[tuple[str, ...], list[tuple[dict, dict]]] = {}
    for entry, routing in routed:
        groups.setdefault(_group_values(entry, group_by), []).append((entry, routing))
    for group_number, (values, members) in enumerate(sorted(groups.items()), 1):
        label = (
            re.sub(r"[^A-Za-z0-9]+", "_", "_".join(values)).strip("_")[:60] or "unknown"
        )
        prefix = "_".join(group_by) or "size"
        for offset in range(0, len(members), size):
            chunk = members[offset : offset + size]
            name = f"{prefix}_{group_number:03d}_{label}_{offset // size + 1:03d}.pdf"
            output = next_dir / name
            path = "bundles/" + output.relative_to(next_dir).as_posix()
            writer = PdfWriter()
            expected_pages = []
            memberships: list[tuple[dict, dict, dict]] = []
            cursor = 1
            for entry, routing in chunk:
                first_page = cursor
                notice_first = cursor
                original, _ = _original_reader(entry, next_dir.parent)
                for page in original.pages:
                    expected_pages.append(_page_hash(page))
                    writer.add_page(page)
                    cursor += 1
                memberships.append(
                    (
                        entry,
                        routing,
                        {
                            "path": path,
                            "destination": "bundle",
                            "start_page": first_page,
                            "end_page": cursor - 1,
                            "notice_start_page": notice_first,
                            "notice_end_page": cursor - 1,
                        },
                    )
                )
            with output.open("wb") as stream:
                writer.write(stream)
            written = PdfReader(output)
            if len(written.pages) != cursor - 1:
                raise ValueError(
                    "Assembled bundle page count does not match memberships"
                )
            if [_page_hash(page) for page in written.pages] != expected_pages:
                raise ValueError(
                    "Assembled bundle pages do not match the selected notices in order"
                )
            length = attempt["notice_length"]
            if length["enabled"]:
                counts = [
                    {
                        "row_key": entry["row_key"],
                        "pages": membership["notice_end_page"]
                        - membership["notice_start_page"]
                        + 1,
                    }
                    for entry, _, membership in memberships
                ]
                passed = all(item["pages"] == length["count"] for item in counts)
                run_report.add_check(
                    attempt,
                    "delivery.notice_length",
                    "delivery",
                    "pass" if passed else "fail",
                    "Every notice has the required PDF page count"
                    if passed
                    else "Bundle contains a notice with the wrong PDF page count",
                    measurements={
                        "bundle": path,
                        "expected_pages": length["count"],
                        "notices": counts,
                    },
                )
            checksum = sha256(output.read_bytes()).hexdigest()
            if not group_by:
                group_name = "All clients"
            else:
                names = []
                for field, value in zip(group_by, values):
                    if field in ("school", "board"):
                        name = (
                            chunk[0][0]["facts"]["prepared"][field].get("name", "")
                            if value
                            else ""
                        )
                        names.append(name or "Unknown")
                    elif field == "page_count":
                        names.append(f"{value} pages" if value != "1" else "1 page")
                    else:
                        names.append(value)
                group_name = " / ".join(names)
            artifact = {
                "path": path,
                "sha256": checksum,
                "pages": cursor - 1,
                "destination": "bundle",
                "group_by": (group_by[0] if len(group_by) == 1 else list(group_by))
                if group_by
                else "size",
                "group_id": (values[0] or None)
                if len(values) == 1
                else (list(values) if values else None),
                "group_name": group_name,
                "row_keys": [entry["row_key"] for entry, _ in chunk],
            }
            attempt["bundles"].append(artifact)
            for entry, routing, membership in memberships:
                membership["sha256"] = checksum
                attempt["memberships"][entry["row_key"]] = {
                    "routing": routing,
                    "bundle": membership,
                }
    if set(attempt["memberships"]) != {entry["row_key"] for entry, _ in routed}:
        raise ValueError("Every readable original must belong to exactly one bundle")
    if attempt["notice_length"]["enabled"] and not any(
        check["code"] == "delivery.notice_length" for check in attempt["checks"]
    ):
        run_report.add_check(
            attempt,
            "delivery.notice_length",
            "delivery",
            "not_applicable",
            "No notices are available for a bundle",
        )
    if any(
        check["code"] == "delivery.notice_length" and check["status"] == "fail"
        for check in attempt["checks"]
    ):
        raise ValueError(
            "Fixed page count failed; the previous bundle set remains active"
        )


FINDINGS_COLUMNS = (
    "run_id",
    "attempt",
    "row_key",
    "client_id",
    "template",
    "version_id",
    "language",
    "eligibility",
    "eligibility_reason",
    "withheld",
    "bundle_path",
    "notice_start_page",
    "notice_end_page",
    "original_page",
    "bundle_page",
    "stage",
    "component",
    "code",
    "effective_status",
    "message",
    "measurements_json",
    "warning_token",
    "warning_accepted",
    "acceptance_reason",
)


def _spreadsheet_cell(value: Any) -> Any:
    """Keep text inert when a CSV is opened by spreadsheet software."""
    if not isinstance(value, str):
        return value
    stripped = value.lstrip()
    leading = value[: len(value) - len(stripped)]
    if any(char in leading for char in "\t\r\n") or stripped.startswith(
        ("=", "+", "-", "@")
    ):
        return "'" + value
    return value


def _write_findings(next_dir: Path, record: dict, attempt: dict) -> None:
    """Write a derived, filterable view beside the staged bundle PDFs."""
    accepted = {item["token"]: item for item in record.get("warning_acceptances", [])}
    entries = {entry["row_key"]: entry for entry in record["entries"]}
    for artifact in attempt["bundles"]:
        relative = Path(artifact["path"]).with_suffix(".csv")
        path = next_dir / relative.name
        count = 0
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FINDINGS_COLUMNS)
            writer.writeheader()
            for row_key in artifact["row_keys"]:
                entry = entries[row_key]
                member = attempt["memberships"][row_key]
                bundle = member["bundle"]
                route = member["routing"]
                evaluation = attempt["evaluations"][row_key]
                results = evaluation["results"]
                tokens = evaluation["warning_tokens"]
                findings = [
                    (index, check)
                    for index, check in enumerate(results)
                    if check.get("status") in ("warn", "fail", "not_run")
                ]
                if not findings and route.get("withheld"):
                    findings = [(None, {})]
                for index, check in findings:
                    warning_id = (
                        f"{check.get('code')}:{index + 1}" if index is not None else ""
                    )
                    token = tokens.get(warning_id, "")
                    acceptance = accepted.get(token) if token else None
                    original_page = check.get("page")
                    notice_start = bundle.get("notice_start_page")
                    bundle_page = (
                        notice_start + original_page - 1
                        if type(original_page) is int
                        and notice_start is not None
                        and 1 <= original_page <= entry["original"].get("pages", 0)
                        else ""
                    )
                    row = {
                        "run_id": record["run_id"],
                        "attempt": attempt["number"],
                        "row_key": row_key,
                        "client_id": entry.get("client_id", ""),
                        **{
                            key: entry["assignment"].get(key, "")
                            for key in ("template", "version_id", "language")
                        },
                        "eligibility": route["destination"],
                        "eligibility_reason": route["reason"],
                        "withheld": "true" if route.get("withheld") else "false",
                        "bundle_path": bundle.get("path", ""),
                        "notice_start_page": bundle.get("notice_start_page", ""),
                        "notice_end_page": bundle.get("notice_end_page", ""),
                        "original_page": original_page
                        if original_page is not None
                        else "",
                        "bundle_page": bundle_page,
                        "stage": check.get("stage", ""),
                        "component": check.get("component", ""),
                        "code": check.get("code", ""),
                        "effective_status": check.get("status", ""),
                        "message": check.get("message", ""),
                        "measurements_json": json.dumps(
                            check["measurements"], ensure_ascii=False
                        )
                        if "measurements" in check
                        else "",
                        "warning_token": token,
                        "warning_accepted": ("true" if acceptance else "false")
                        if token
                        else "",
                        "acceptance_reason": acceptance["reason"] if acceptance else "",
                    }
                    writer.writerow(
                        {key: _spreadsheet_cell(value) for key, value in row.items()}
                    )
                    count += 1

        artifact["findings_csv"] = {
            "path": relative.as_posix(),
            "sha256": sha256(path.read_bytes()).hexdigest(),
            "rows": count,
        }


def _recover_delivery(run_dir: Path, record: dict[str, Any]) -> None:
    """Recover saved replacement state while the caller holds this run's lock."""
    next_dir, previous = run_dir / "bundles.next", run_dir / "bundles.previous"
    attempts = record["delivery_attempts"]
    latest = attempts[-1] if attempts else None
    if previous.exists():
        if latest is None:
            raise ValueError("Bundle backup exists without a recorded delivery attempt")
        if latest["status"] == "completed":
            shutil.rmtree(previous)
            if next_dir.exists():
                shutil.rmtree(next_dir)
            return
        active = run_dir / "bundles"
        if active.exists():
            shutil.rmtree(active)
        previous.replace(active)
        for entry in record["entries"]:
            prior = latest.get("previous_memberships", {}).get(entry["row_key"])
            if prior:
                entry.update(prior)
    if next_dir.exists():
        shutil.rmtree(next_dir)
    if latest and latest["status"] in ("running", "prepared", "replacing"):
        latest["status"] = "failed"
        latest["bundles"] = []
        latest["memberships"] = {}
        latest["finished_at"] = run_report.timestamp()
        run_report.add_check(
            latest,
            "delivery.interrupted",
            "delivery",
            "fail",
            "Interrupted bundle replacement was rolled back; previous memberships remain active",
        )
        run_report.finish_run(record)
        run_report.write_report(run_dir, record)


def bundle_run(
    run_dir: Path,
    *,
    accept: list[str] | None = None,
    reason: str | None = None,
    withhold: list[str] | None = None,
    policy: dict | None = None,
) -> dict[str, Any]:
    """Lock a saved run before loading, recovering or changing its delivery."""
    run_dir = run_dir.resolve()
    with run_lock(run_dir):
        record = read_json(run_dir / "run.json")
        if not isinstance(record, dict):
            raise ValueError(
                "Unsupported run format; rebundling requires format version 2"
            )
        return _bundle_run(
            run_dir,
            record,
            accept=accept,
            reason=reason,
            withhold=withhold,
            policy=policy,
        )


def _bundle_run(
    run_dir: Path,
    record: dict[str, Any],
    *,
    accept: list[str] | None = None,
    reason: str | None = None,
    withhold: list[str] | None = None,
    policy: dict | None = None,
) -> dict[str, Any]:
    """Validate, assemble, then commit while the caller holds this run's lock.

    Expected operation failures return a failed attempt while preserving the
    previous set. Unexpected errors save the same evidence and propagate.
    """
    if record.get("format_version") != run_report.RUN_FORMAT_VERSION:
        raise ValueError("Unsupported run format; rebundling requires format version 2")
    if record["input"].get("accepted") is not True:
        raise ValueError(
            "Input checks did not accept this run; correct the source and generate a new run"
        )
    run_dir = run_dir.resolve()
    _recover_delivery(run_dir, record)
    attempt: dict[str, Any] = {
        "number": len(record["delivery_attempts"]) + 1,
        "started_at": run_report.timestamp(),
        "finished_at": None,
        "status": "running",
        "configuration": {},
        "review": {"accepted_tokens": accept or [], "reason": reason},
        "evaluations": {},
        "checks": [],
        "bundles": [],
        "memberships": {},
        "previous_memberships": {
            entry["row_key"]: {
                "routing": deepcopy(entry["routing"]),
                "bundle": deepcopy(entry["bundle"]),
            }
            for entry in record["entries"]
        },
    }
    previous_memberships = attempt["previous_memberships"]
    record["delivery_attempts"].append(attempt)
    run_report.write_report(run_dir, record)
    next_dir, previous, active = (
        run_dir / "bundles.next",
        run_dir / "bundles.previous",
        run_dir / "bundles",
    )
    try:
        attempt["engine"] = run_report.engine_identity()
        if record.get("version", {}).get("compiler") != TYPST_VERSION:
            raise ValueError(
                "Saved run uses an unsupported notice compiler; generate and check a new run"
            )
        requested = (
            record.get(
                "validation_policy",
                record["configuration"]["effective"].get("validation", {}),
            )
            if policy is None
            else policy
        )
        attempt["rule_definitions"] = validation_policy.policy_snapshot()
        attempt["rule_settings"] = deepcopy(requested)
        resolved = validation_policy.resolve_policy(requested, record)
        attempt["resolved_rules"] = deepcopy(resolved)
        attempt["notice_length"] = validation_policy.notice_length_settings(requested)
        retained = run_report.resource_manifest(run_dir / "resources", run_dir)
        if retained["sha256"] != record["resources"].get("sha256"):
            raise ValueError(
                "Saved resources changed; generate and check a new run before delivery"
            )
        attempt["resources_sha256"] = retained["sha256"]
        verify_components(run_dir / "resources/templates")
        settings = record["configuration"]["effective"].get("bundling", {})
        attempt["configuration"] = deepcopy(settings)
        size = settings.get("bundle_size", 0)
        if type(size) is not int or size < 0:
            raise ValueError("bundle_size must be a nonnegative integer")
        if size == 0 and attempt["notice_length"]["enabled"]:
            raise ValueError(
                "Fixed notice length requires bundling.bundle_size above zero"
            )
        group_by = bundle_grouping(settings.get("group_by"))
        entries = [
            entry
            for entry in record["entries"]
            if entry["original"]["status"] == "completed"
        ]
        if len({entry["row_key"] for entry in record["entries"]}) != len(
            record["entries"]
        ):
            raise ValueError("Run entries must have unique source row keys")
        record["validation_policy"] = deepcopy(requested)
        routed = _routes(
            run_dir,
            record,
            entries,
            group_by,
            attempt,
            accept or [],
            reason,
            record.get("withheld_rows", []) if withhold is None else withhold,
            resolved,
        )
        if not attempt["notice_length"]["enabled"]:
            run_report.add_check(
                attempt,
                "delivery.notice_length",
                "delivery",
                "not_run",
                "Fixed notice length is disabled",
            )
        attempt["review"]["withheld_rows"] = record["withheld_rows"]
        run_report.write_report(run_dir, record)
        if size == 0:
            attempt["status"] = "completed"
            run_report.add_check(
                attempt,
                "delivery.disabled",
                "delivery",
                "not_applicable",
                "Bundling is disabled; originals remain available",
            )
        else:
            next_dir.mkdir(mode=0o700)
            _assemble(routed, next_dir, group_by, size, attempt)
            _write_findings(next_dir, record, attempt)
            attempt["status"] = "prepared"
            run_report.write_report(run_dir, record)
            attempt["status"] = "replacing"
            run_report.write_report(run_dir, record)
            active.mkdir(exist_ok=True)
            active.replace(previous)
            next_dir.replace(active)
            for entry in record["entries"]:
                membership = attempt["memberships"].get(entry["row_key"])
                if membership:
                    entry.update(membership)
                else:
                    entry["bundle"] = None
                    entry["routing"] = {
                        "destination": None,
                        "reason": "No readable original PDF",
                    }
            attempt["status"] = "completed"
        attempt["finished_at"] = run_report.timestamp()
        attempt.pop("previous_memberships", None)
        run_report.finish_run(record)
        run_report.write_report(run_dir, record)
        if previous.exists():
            shutil.rmtree(previous)
        return attempt
    except Exception as exc:
        # JSON is authoritative if its HTML view fails after the commit write.
        saved = read_json(run_dir / "run.json")
        saved_attempt = saved["delivery_attempts"][-1]
        if (
            saved_attempt["number"] == attempt["number"]
            and saved_attempt["status"] == "completed"
        ):
            record.clear()
            record.update(saved)
            _recover_delivery(run_dir, record)
            raise
        if previous.exists():
            if active.exists():
                shutil.rmtree(active)
            previous.replace(active)
        if next_dir.exists():
            shutil.rmtree(next_dir)
        for entry in record["entries"]:
            entry.update(previous_memberships[entry["row_key"]])
        attempt["status"] = "failed"
        attempt.pop("previous_memberships", None)
        attempt["bundles"] = []
        attempt["memberships"] = {}
        attempt["finished_at"] = run_report.timestamp()
        detail = str(exc)
        run_report.add_check(attempt, "delivery.failed", "delivery", "fail", detail)
        run_report.finish_run(record)
        run_report.write_report(run_dir, record)
        if isinstance(exc, (OSError, ValueError, PdfReadError)):
            return attempt
        raise
