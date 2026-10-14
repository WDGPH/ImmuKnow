"""Route saved originals into delivery or annotated review, then replace safely."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from copy import deepcopy
from enum import Enum
from hashlib import sha256
from importlib.resources import files
from io import BytesIO
from pathlib import Path
from typing import Any

from pypdf import PageObject, PdfReader, PdfWriter, Transformation
from pypdf.errors import PdfReadError
from jsonschema import ValidationError

from . import run_report, validation_policy
from .run_lock import run_lock
from .structured_input import parse_json, read_json
from .component_resources import verify_components
from .render_payload import validate_render_payload
from .render_contract import validate_render_report
from .compile_notices import (
    CompilerTimeouts,
    TYPST_VERSION,
    check_compiler,
    compiler_warnings,
    run_typst,
)

REVIEW_BAND_PT = 18


class BundleGrouping(Enum):
    """Keep the existing size/school/board configuration contract."""

    SIZE = "size"
    SCHOOL = "school"
    BOARD = "board"

    @classmethod
    def from_string(cls, value: str | None) -> BundleGrouping:
        if value is None:
            return cls.SIZE
        if isinstance(value, str):
            try:
                return cls(value.lower())
            except ValueError:
                pass
        raise ValueError(
            f"Unknown bundle grouping: {value!r}. Valid options: size, school, board"
        )


def _original_reader(entry: dict, run_dir: Path) -> PdfReader:
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
    summary = entry.get("render_summary")
    if summary is not None:
        validate_render_report(
            summary,
            {
                key: payload[key]
                for key in (
                    "row_key",
                    "template",
                    "client_id",
                    "version_id",
                    "language",
                )
            },
        )
        if summary["page_count"] != len(reader.pages):
            raise ValueError(
                f"Render evidence page count differs from the original: {entry['row_key']}"
            )
    return reader


def _routes(
    record: dict,
    entries: list[dict],
    group_by: BundleGrouping,
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
        observations = deepcopy(entry["checks"])
        summary = entry.get("render_summary")
        if summary is None:
            observations.append(
                {
                    "code": "render.evidence_failed",
                    "stage": "render",
                    "status": "fail",
                    "message": "Required render evidence is missing; generate and check a new notice.",
                }
            )
        else:
            for check in summary["checks"]:
                if check not in observations:
                    observations.append(deepcopy(check))
        facts = entry["facts"]["prepared"]
        if group_by != BundleGrouping.SIZE and not facts[group_by.value].get("id"):
            observations.append(
                {
                    "code": "delivery.group_unknown",
                    "stage": "delivery",
                    "status": "warn",
                    "message": f"Missing {group_by.value} identifier; delivery grouping uses Unknown",
                    "measurements": {"group_by": group_by.value},
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
    return [
        (
            entry,
            validation_policy.route_original(
                record,
                evaluations[entry["row_key"]],
                withheld=entry["row_key"] in withheld,
            ),
        )
        for entry in entries
    ]


def _compile_review(
    template: Path,
    destination: Path,
    inputs: dict[str, str],
    work: Path,
    record: dict,
    attempt: dict,
) -> None:
    settings = record["configuration"]["effective"]
    review_tools = attempt["review_tools"]
    typst_bin = review_tools["compiler"]["path"]
    timestamp = settings.get("creation_timestamp")
    if type(timestamp) is not int:
        raise ValueError("Saved run is missing its frozen creation timestamp")
    command = [
        typst_bin,
        "compile",
        "--root",
        str(work),
        "--creation-timestamp",
        str(timestamp),
    ]
    for key, value in inputs.items():
        command.extend(["--input", f"{key}={value}"])
    command.extend([str(template), str(destination)])
    timeouts = CompilerTimeouts.from_config(
        settings.get("typst", {}).get("timeouts_seconds", {})
    )
    result = run_typst(command, timeout=timeouts.review, operation="review compilation")
    for warning in compiler_warnings(result.stderr):
        check = warning.to_dict()
        if check not in attempt["checks"]:
            attempt["checks"].append(check)


def _prepare_review(work: Path, record: dict, attempt: dict) -> None:
    """Copy and identify the review templates and executable actually used."""
    settings = record["configuration"]["effective"]
    requested = os.environ.get(
        "TYPST_BIN", settings.get("typst", {}).get("bin", "typst")
    )
    tools = {"compiler": {"requested": requested}, "templates": []}
    attempt["review_tools"] = tools
    for name in ("review_sheet.typ", "review_stamp.typ"):
        shutil.copyfile(
            Path(str(files("immuknow").joinpath("review_templates").joinpath(name))),
            work / name,
        )
        tools["templates"].append(run_report.artifact_record(work / name, work))
    executable = shutil.which(requested)
    if executable is None:
        raise ValueError(f"Typst executable not found: {requested}")
    executable_path = Path(executable).resolve()
    tools["compiler"].update(
        path=str(executable_path),
        sha256=sha256(executable_path.read_bytes()).hexdigest(),
    )
    run_report.write_report(work.parent.parent, record)
    timeouts = CompilerTimeouts.from_config(
        settings.get("typst", {}).get("timeouts_seconds", {})
    )
    try:
        tools["compiler"]["version_output"] = check_compiler(
            str(executable_path), timeout=timeouts.version
        )
    except RuntimeError as exc:
        raise ValueError(str(exc)) from exc
    run_report.write_report(work.parent.parent, record)


def _measurement_text(measurements: dict) -> str:
    """Show actual warning measurements in millimetres; retain precision in JSON."""
    lines = []
    for key, value in measurements.items():
        if type(value) in (int, float) and key.endswith("_pt"):
            key = key[:-3] + " (mm)"
            value = f"{value * 25.4 / 72:.1f}"
        elif type(value) in (int, float) and key.endswith("_mm"):
            key = key[:-3] + " (mm)"
            value = f"{value:.1f}"
        elif type(value) is float:
            value = f"{value:.1f}"
        elif isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        lines.append(f"{key.replace('_', ' ')}: {value}")
    return "\n".join(lines)


def _review_sheet(entry: dict, work: Path, record: dict, attempt: dict) -> PdfReader:
    facts = entry["facts"]["prepared"]
    findings = []
    for check in attempt["evaluations"][entry["row_key"]]["results"]:
        if check["status"] not in ("warn", "fail", "not_run"):
            continue
        findings.append(
            {
                "code": check["code"],
                "status": check["status"],
                "message": check["message"],
                "location": " · ".join(
                    filter(
                        None,
                        [
                            check["stage"],
                            check.get("component", ""),
                            f"original page {check['page']}"
                            if check.get("page")
                            else "",
                        ],
                    )
                ),
                "measurements": _measurement_text(check["measurements"])
                if check.get("measurements")
                else "",
            }
        )
    payload = {
        "client_id": entry["client_id"] or "Missing",
        "row_key": entry["row_key"],
        "template": entry["assignment"].get("template", "Unknown"),
        "school": facts["school"].get("name", "") or "Unknown",
        "board": facts["board"].get("name", "") or "Unknown",
        "findings": findings,
        "measurements": f"Original PDF pages: {entry['original']['pages']}. Full checks and layout measurements remain in report.html.",
        "warning_tokens": attempt["evaluations"][entry["row_key"]]["warning_tokens"],
    }
    data = work / f"{entry['row_key']}.json"
    data.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    output = work / f"{entry['row_key']}-sheet.pdf"
    _compile_review(
        work / "review_sheet.typ", output, {"data": data.name}, work, record, attempt
    )
    return PdfReader(output)


def _review_page(
    page: PageObject, work: Path, record: dict, attempt: dict, stamps: dict
) -> PageObject:
    # Normalize rotation only on a writer-owned copy; originals stay unchanged.
    if page.rotation:
        copied = PdfWriter()
        page = copied.add_page(page)
        page.transfer_rotation_to_content()
    crop = page.cropbox
    width, height = float(crop.width), float(crop.height)
    dimensions = (width, height)
    if dimensions not in stamps:
        output = work / f"stamp-{len(stamps) + 1:03d}.pdf"
        _compile_review(
            work / "review_stamp.typ",
            output,
            {"page-width": str(width), "page-height": str(height + REVIEW_BAND_PT)},
            work,
            record,
            attempt,
        )
        stamps[dimensions] = PdfReader(output).pages[0]
    reviewed = PageObject.create_blank_page(width=width, height=height + REVIEW_BAND_PT)
    reviewed.merge_transformed_page(
        page, Transformation().translate(-float(crop.left), -float(crop.bottom))
    )
    reviewed.merge_page(stamps[dimensions])
    return reviewed


def _page_hash(page: PageObject) -> str:
    """Compare complete page copies after writing, independent of PDF object numbers."""
    writer = PdfWriter()
    writer.add_page(page)
    # A new review page has no source header; a read-back page inherits the
    # bundle header. Keep this comparison copy's header independent of either.
    writer.pdf_header = "%PDF-1.7"
    stream = BytesIO()
    writer.write(stream)
    return sha256(stream.getvalue()).hexdigest()


def _assemble(
    routed: list[tuple[dict, dict]],
    next_dir: Path,
    work: Path,
    group_by: BundleGrouping,
    size: int,
    record: dict,
    attempt: dict,
) -> None:
    groups: dict[tuple[str, str], list[tuple[dict, dict]]] = {}
    for entry, routing in routed:
        group_id = ""
        if routing["destination"] == "delivery" and group_by != BundleGrouping.SIZE:
            group_id = entry["facts"]["prepared"][group_by.value].get("id", "") or ""
        groups.setdefault((routing["destination"], group_id), []).append(
            (entry, routing)
        )
    review_needed = any(destination == "review" for destination, _ in groups)
    if review_needed:
        _prepare_review(work, record, attempt)
    stamps: dict = {}
    for group_number, ((destination, group_id), members) in enumerate(
        sorted(groups.items()), 1
    ):
        directory = next_dir / destination
        directory.mkdir(exist_ok=True)
        label = re.sub(r"[^A-Za-z0-9]+", "_", group_id).strip("_")[:60] or "unknown"
        for offset in range(0, len(members), size):
            chunk = members[offset : offset + size]
            name = f"{group_by.value if destination == 'delivery' else 'review'}_{group_number:03d}_{label}_{offset // size + 1:03d}.pdf"
            output = directory / name
            path = "bundles/" + output.relative_to(next_dir).as_posix()
            writer = PdfWriter()
            expected_pages = []
            memberships: list[tuple[dict, dict, dict]] = []
            cursor = 1
            for entry, routing in chunk:
                first_page = cursor
                sheet_first, sheet_last = None, None
                if destination == "review":
                    sheet = _review_sheet(entry, work, record, attempt)
                    sheet_first = cursor
                    for page in sheet.pages:
                        expected_pages.append(_page_hash(page))
                        writer.add_page(page)
                        cursor += 1
                    sheet_last = cursor - 1
                notice_first = cursor
                original = _original_reader(entry, next_dir.parent)
                for page in original.pages:
                    selected_page = (
                        _review_page(page, work, record, attempt, stamps)
                        if destination == "review"
                        else page
                    )
                    expected_pages.append(_page_hash(selected_page))
                    writer.add_page(selected_page)
                    cursor += 1
                memberships.append(
                    (
                        entry,
                        routing,
                        {
                            "path": path,
                            "destination": destination,
                            "start_page": first_page,
                            "end_page": cursor - 1,
                            "sheet_start_page": sheet_first,
                            "sheet_end_page": sheet_last,
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
            if destination == "delivery" and length["enabled"]:
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
                    else "Delivery batch contains a notice with the wrong PDF page count",
                    measurements={
                        "bundle": path,
                        "expected_pages": length["count"],
                        "notices": counts,
                    },
                )
            checksum = sha256(output.read_bytes()).hexdigest()
            if destination == "review":
                group_name = "Review"
            elif group_by == BundleGrouping.SIZE:
                group_name = "All clients"
            elif group_id:
                group_name = (
                    chunk[0][0]["facts"]["prepared"][group_by.value].get("name", "")
                    or "Unknown"
                )
            else:
                group_name = "Unknown"
            artifact = {
                "path": path,
                "sha256": checksum,
                "pages": cursor - 1,
                "destination": destination,
                "group_by": group_by.value if destination == "delivery" else "review",
                "group_id": group_id or None,
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
            "No notices are eligible for a delivery batch",
        )
    if any(
        check["code"] == "delivery.notice_length" and check["status"] == "fail"
        for check in attempt["checks"]
    ):
        raise ValueError(
            "Fixed page count failed; the previous bundle set remains active"
        )


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
        attempt["review_tools"] = None
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
        group_by = BundleGrouping.from_string(settings.get("group_by"))
        entries = [
            entry
            for entry in record["entries"]
            if entry["original"]["status"] == "completed"
        ]
        if len({entry["row_key"] for entry in record["entries"]}) != len(
            record["entries"]
        ):
            raise ValueError("Run entries must have unique source row keys")
        for entry in entries:
            _original_reader(entry, run_dir)
        record["validation_policy"] = deepcopy(requested)
        routed = _routes(
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
            work = run_dir / "work" / "delivery"
            if work.exists():
                shutil.rmtree(work)
            work.mkdir(parents=True, mode=0o700)
            next_dir.mkdir(mode=0o700)
            _assemble(routed, next_dir, work, group_by, size, record, attempt)
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
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            detail += "\n" + exc.stderr
        run_report.add_check(attempt, "delivery.failed", "delivery", "fail", detail)
        run_report.finish_run(record)
        run_report.write_report(run_dir, record)
        if isinstance(
            exc, (OSError, ValueError, PdfReadError, subprocess.CalledProcessError)
        ):
            return attempt
        raise
