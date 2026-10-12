"""Route saved originals into delivery or annotated review, then replace safely."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections import Counter
from copy import deepcopy
from enum import Enum
from hashlib import sha256
from importlib.resources import files
from io import BytesIO
from pathlib import Path
from typing import Any

from pypdf import PageObject, PdfReader, PdfWriter, Transformation
from pypdf.errors import PdfReadError

from . import run_report
from .compile_notices import check_compiler, compiler_warnings

# Known warning types remain usable as allowances even when absent in this run.
# Custom authored warning codes may also be allowed when recorded in this run.
WARNING_CODES = frozenset(
    {
        "data.school_unmatched",
        "source.client_id_missing",
        "source.first_name_missing",
        "source.last_name_missing",
        "source.school_name_missing",
        "source.board_name_missing",
        "source.client_id_format",
        "source.address_incomplete",
        "source.age_unknown",
        "source.overdue_unusable",
        "source.history_unparsed",
        "assignment.extra_manifest_row",
        "assignment.version_conflict",
        "assignment.check_unavailable",
        "assignment.eligibility_conflict",
        "compiler.warning",
        "compiler.font_substitution",
        "compiler.layout_nonconvergent",
        "content.translation_missing",
        "content.history_validity",
        "content.history_age_unknown",
        "content.history_unparsed",
        "content.address_age_unknown",
        "content.birth_date_unknown",
        "layout.history_width",
        "layout.header_title_lines",
        "layout.address_outside_window",
        "layout.signature_page",
        "layout.privacy_page",
        "layout.section_pages",
        "output.evidence_unavailable",
        "output.evidence_mismatch",
        "output.client_identity",
        "delivery.encryption_failed",
        "delivery.group_unknown",
    }
)
DEFAULT_OVERRIDES = {"allow_delivery_warnings": [], "clients": {}}
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


def validate_overrides(overrides: Any, record: dict[str, Any]) -> dict[str, Any]:
    """Reject typos and ambiguous public IDs before preparing replacement PDFs."""
    if not isinstance(overrides, dict) or set(overrides) - set(DEFAULT_OVERRIDES):
        raise ValueError(
            "Overrides must contain only allow_delivery_warnings and clients"
        )
    warnings = overrides.get("allow_delivery_warnings", [])
    clients = overrides.get("clients", {})
    if not isinstance(warnings, list) or any(
        not isinstance(code, str) for code in warnings
    ):
        raise ValueError("allow_delivery_warnings must be a list of warning codes")
    known = WARNING_CODES | {
        check["code"]
        for entry in record["entries"]
        for check in entry["checks"]
        if check["status"] == "warn"
    }
    unknown = sorted(set(warnings) - known)
    if unknown:
        raise ValueError("Unknown warning code(s): " + ", ".join(unknown))
    if not isinstance(clients, dict):
        raise ValueError("clients must map client IDs to delivery or review")
    counts = Counter(entry["client_id"] for entry in record["entries"])
    for client_id, destination in clients.items():
        if (
            not isinstance(client_id, str)
            or not re.fullmatch(r"\d{10}", client_id)
            or counts[client_id] != 1
        ):
            raise ValueError(
                f"Override client ID must be a unique ten-digit source ID: {client_id!r}"
            )
        if destination not in ("delivery", "review"):
            raise ValueError(f"Override for {client_id} must be delivery or review")
    return {
        "allow_delivery_warnings": sorted(set(warnings)),
        "clients": dict(sorted(clients.items())),
    }


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate override key: {key}")
        result[key] = value
    return result


def _read_overrides(overrides: dict | Path | None, run_dir: Path, record: dict) -> dict:
    if overrides is None:
        overrides = run_dir / "overrides.json"
        if not overrides.exists():
            with overrides.open("x", encoding="utf-8") as stream:
                json.dump(DEFAULT_OVERRIDES, stream, indent=2)
            overrides.chmod(0o600)
    if isinstance(overrides, Path):
        overrides = json.loads(
            overrides.read_text(encoding="utf-8"), object_pairs_hook=_unique_object
        )
    return validate_overrides(overrides, record)


def _original_reader(entry: dict, run_dir: Path) -> PdfReader:
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
    return reader


def _routes(
    entries: list[dict], group_by: BundleGrouping, overrides: dict
) -> list[tuple[dict, dict]]:
    routed = []
    allowed = set(overrides["allow_delivery_warnings"])
    for entry in entries:
        facts = entry["facts"]["prepared"]
        if group_by != BundleGrouping.SIZE and not facts[group_by.value].get("id"):
            if not any(
                check["code"] == "delivery.group_unknown" for check in entry["checks"]
            ):
                run_report.add_check(
                    entry,
                    "delivery.group_unknown",
                    "delivery",
                    "warn",
                    f"Missing {group_by.value} identifier; delivery grouping uses Unknown",
                    measurements={"group_by": group_by.value},
                )
        unresolved = sorted(
            {
                check["code"]
                for check in entry["checks"]
                if check["status"] == "warn" and check["code"] not in allowed
            }
        )
        explicit = overrides["clients"].get(entry["client_id"])
        destination = explicit or ("review" if unresolved else "delivery")
        reason = (
            "Explicit client override"
            if explicit
            else ("Unresolved warnings" if unresolved else "No unresolved warnings")
        )
        routed.append(
            (
                entry,
                {
                    "destination": destination,
                    "reason": reason,
                    "override": explicit,
                    "unresolved_warnings": unresolved,
                    "allowed_warnings": sorted(
                        {
                            check["code"]
                            for check in entry["checks"]
                            if check["status"] == "warn"
                        }
                        & allowed
                    ),
                },
            )
        )
    return routed


def _compile_review(
    template: Path,
    destination: Path,
    inputs: dict[str, str],
    work: Path,
    record: dict,
    attempt: dict,
) -> None:
    settings = record["configuration"]["effective"]
    typst_bin = os.environ.get(
        "TYPST_BIN", settings.get("typst", {}).get("bin", "typst")
    )
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
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    for warning in compiler_warnings(result.stderr):
        check = warning.to_dict()
        if check not in attempt["checks"]:
            attempt["checks"].append(check)


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
    for check in entry["checks"]:
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
        "override_example": json.dumps(
            {"clients": {entry["client_id"]: "delivery"}}, ensure_ascii=False, indent=2
        )
        if re.fullmatch(r"\d{10}", entry["client_id"])
        else "This source row has no valid public override ID. Correct source identity before generating a new notice.",
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
        settings = record["configuration"]["effective"]
        executable = os.environ.get(
            "TYPST_BIN", settings.get("typst", {}).get("bin", "typst")
        )
        try:
            check_compiler(executable)
        except RuntimeError as exc:
            raise ValueError(str(exc)) from exc
        for name in ("review_sheet.typ", "review_stamp.typ"):
            shutil.copyfile(
                Path(
                    str(files("immuknow").joinpath("review_templates").joinpath(name))
                ),
                work / name,
            )
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
            memberships = []
            cursor = 1
            for entry, routing in chunk:
                first_page = cursor
                sheet_first, sheet_last = None, None
                if destination == "review":
                    sheet = _review_sheet(entry, work, record, attempt)
                    sheet_first = cursor
                    for page in sheet.pages:
                        writer.add_page(page)
                        cursor += 1
                    sheet_last = cursor - 1
                notice_first = cursor
                original = _original_reader(entry, next_dir.parent)
                for page in original.pages:
                    writer.add_page(
                        _review_page(page, work, record, attempt, stamps)
                        if destination == "review"
                        else page
                    )
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
            if len(PdfReader(output).pages) != cursor - 1:
                raise ValueError(
                    "Assembled bundle page count does not match memberships"
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


def recover_delivery(run_dir: Path, record: dict[str, Any]) -> None:
    """Use only saved attempt state and the two fixed replacement directories."""
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
    run_dir: Path, record: dict[str, Any], overrides: dict | Path | None = None
) -> dict[str, Any]:
    """Validate, assemble, then commit one complete delivery result.

    Expected operation failures return a failed attempt while preserving the
    previous set. Unexpected errors save the same evidence and propagate.
    """
    if record.get("format_version") != run_report.RUN_FORMAT_VERSION:
        raise ValueError("Unsupported run format; rebundling requires format version 1")
    run_dir = run_dir.resolve()
    recover_delivery(run_dir, record)
    attempt: dict[str, Any] = {
        "number": len(record["delivery_attempts"]) + 1,
        "started_at": run_report.timestamp(),
        "finished_at": None,
        "status": "running",
        "configuration": {},
        "overrides": {},
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
        attempt["overrides"] = _read_overrides(overrides, run_dir, record)
        settings = record["configuration"]["effective"].get("bundling", {})
        attempt["configuration"] = deepcopy(settings)
        size = settings.get("bundle_size", 0)
        if type(size) is not int or size < 0:
            raise ValueError("bundle_size must be a nonnegative integer")
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
            routed = _routes(entries, group_by, attempt["overrides"])
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
                        "override": attempt["overrides"]["clients"].get(
                            entry["client_id"]
                        ),
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
        saved = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
        saved_attempt = saved["delivery_attempts"][-1]
        if (
            saved_attempt["number"] == attempt["number"]
            and saved_attempt["status"] == "completed"
        ):
            record.clear()
            record.update(saved)
            recover_delivery(run_dir, record)
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
