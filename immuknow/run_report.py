"""Persist one run record and generate its escaped, readable HTML view."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
from pathlib import Path
from typing import Any

from .data_models import CheckResult, CheckStatus

RUN_FORMAT_VERSION = 1


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def artifact_record(path: Path, run_dir: Path) -> dict[str, Any]:
    """Record actual bytes, with paths relative to the portable run directory."""
    return {
        "path": path.relative_to(run_dir).as_posix(),
        "sha256": sha256(path.read_bytes()).hexdigest(),
    }


def resource_manifest(resource_dir: Path, run_dir: Path) -> dict[str, Any]:
    records = [
        artifact_record(path, run_dir)
        for path in sorted(resource_dir.rglob("*"))
        if path.is_file()
    ]
    fingerprint = sha256(
        json.dumps(records, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {"sha256": fingerprint, "files": records}


def add_check(
    target: dict[str, Any],
    code: str,
    stage: str,
    status: CheckStatus,
    message: str,
    **details: Any,
) -> None:
    target["checks"].append(
        CheckResult(code, stage, status, message, **details).to_dict()
    )


def finish_run(record: dict[str, Any], *, failed_setup: bool = False) -> None:
    checks = (
        record["checks"]
        + [check for entry in record["entries"] for check in entry["checks"]]
        + [
            check
            for attempt in record["delivery_attempts"]
            for check in attempt.get("checks", [])
        ]
    )
    if failed_setup:
        record["status"] = "failed_setup"
    elif record["input"].get("accepted") is False:
        record["status"] = "rejected_input"
    elif any(check["status"] == "fail" for check in checks):
        record["status"] = "completed_with_failures"
    elif any(check["status"] == "warn" for check in checks):
        record["status"] = "completed_with_warnings"
    else:
        record["status"] = "completed"
    record["finished_at"] = timestamp()


def write_report(run_dir: Path, record: dict[str, Any]) -> Path:
    """Replace JSON and its generated view after each completed responsibility."""
    record_path = run_dir / "run.json"
    _replace_text(record_path, json.dumps(record, ensure_ascii=False, indent=2))
    _replace_text(run_dir / "report.html", render_html(record))
    return record_path


def _replace_text(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.touch(mode=0o600, exist_ok=True)
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def render_html(record: dict[str, Any]) -> str:
    """Keep every finding accessible without embedding untrusted HTML or scripts."""
    counts = Counter(entry["original"]["status"] for entry in record["entries"])
    parts = [
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>ImmuKnow run report</title>',
        "<style>body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem}details{border-top:1px solid #ccc;padding:1rem 0}summary{cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere}li{margin:.5rem 0}.fail{color:#a00}.warn{color:#805000}</style>",
        f"<h1>ImmuKnow run {escape(record['run_id'])}</h1>",
        f"<p>{escape(record['status'])} · {len(record['entries'])} source rows · {counts['completed']} original PDFs · {counts['failed']} failed notices</p>",
        "<p>Client information in this report and its linked files is sensitive.</p>",
        "<h2>Run checks</h2>",
        _checks_html(record["checks"]),
    ]
    for entry in record["entries"]:
        title = f"{entry['row_key']} · {entry['client_id'] or 'Missing client ID'} · {entry['original']['status']}"
        parts.extend(
            [
                f"<details><summary>{escape(title)}</summary>",
                _checks_html(entry["checks"]),
            ]
        )
        for label, artifact in (
            ("Original PDF", entry["original"]),
            ("Encrypted PDF", entry["encryption"]),
            ("Bundle", entry["bundle"] or {}),
        ):
            if artifact.get("path"):
                parts.append(
                    f'<p><a href="{escape(artifact["path"], quote=True)}">{label}</a> · SHA-256 {escape(artifact.get("sha256", "")[:12])}</p>'
                )
        parts.append(
            "<pre>"
            + escape(json.dumps(entry, ensure_ascii=False, indent=2))
            + "</pre></details>"
        )
    parts.append("<h2>Delivery attempts</h2>")
    for attempt in record["delivery_attempts"]:
        parts.append(
            f"<details><summary>Attempt {attempt['number']} · {escape(attempt['status'])}</summary>"
        )
        parts.append(_checks_html(attempt.get("checks", [])))
        if (
            attempt["status"] == "completed"
            and attempt is record["delivery_attempts"][-1]
        ):
            for bundle in attempt["bundles"]:
                parts.append(
                    f'<p><a href="{escape(bundle["path"], quote=True)}">{escape(bundle["path"])}</a></p>'
                )
        parts.append(
            "<pre>"
            + escape(json.dumps(attempt, ensure_ascii=False, indent=2))
            + "</pre></details>"
        )
    parts.extend(
        [
            "<h2>Run resources and configuration</h2><pre>",
            escape(
                json.dumps(
                    {
                        key: value
                        for key, value in record.items()
                        if key not in {"entries", "delivery_attempts"}
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            ),
            "</pre></html>",
        ]
    )
    return "\n".join(parts)


def _checks_html(checks: list[dict[str, Any]]) -> str:
    return (
        "<ul>"
        + "".join(
            f'<li class="{escape(check["status"])}">{escape(check["status"])} · {escape(check["code"])}: {escape(check["message"])}'
            + (
                "<pre>"
                + escape(
                    json.dumps(check["measurements"], ensure_ascii=False, indent=2)
                )
                + "</pre>"
                if check.get("measurements")
                else ""
            )
            + "</li>"
            for check in checks
        )
        + "</ul>"
    )
