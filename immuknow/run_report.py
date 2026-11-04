"""Persist one run record and generate its escaped, readable HTML view."""

from __future__ import annotations

import json
import logging
import os
import re
import platform
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
from itertools import chain, islice
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path
from time import perf_counter
from typing import Any, TextIO

from .data_models import CheckResult, CheckStatus

RUN_FORMAT_VERSION = 2


def engine_identity() -> dict[str, Any]:
    """Identify the installed native code and contracts used for this attempt."""
    package = Path(str(files("immuknow")))
    return {
        "application_version": version("ImmuKnow"),
        "python_version": platform.python_version(),
        "pdf_library_version": version("pypdf"),
        "run_format_version": RUN_FORMAT_VERSION,
        "code": [
            artifact_record(path, package) for path in sorted(package.glob("*.py"))
        ],
        "schemas": resource_manifest(package / "schemas", package),
    }


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
    checks = chain(
        record["checks"],
        (check for entry in record["entries"] for check in entry["checks"]),
        (
            check
            for attempt in record["delivery_attempts"]
            for check in attempt.get("checks", [])
        ),
        (
            result
            for attempt in record["delivery_attempts"]
            for evaluation in attempt.get("evaluations", {}).values()
            for result in evaluation["results"]
        ),
    )
    statuses = {check["status"] for check in checks}
    if failed_setup:
        record["status"] = "failed_setup"
    elif record["input"].get("accepted") is False:
        record["status"] = "rejected_input"
    elif "fail" in statuses:
        record["status"] = "completed_with_failures"
    elif "warn" in statuses:
        record["status"] = "completed_with_warnings"
    else:
        record["status"] = "completed"
    record["finished_at"] = timestamp()


class _OutcomeCheckpoint:
    """Periodically persist incorporated outcomes without rebuilding HTML."""

    def __init__(self, run_dir: Path, record: dict[str, Any]) -> None:
        self.run_dir = run_dir
        self.record = record
        self.pending = 0
        self.last_saved = perf_counter()
        self.interval = 30.0

    def advance(self) -> None:
        self.pending += 1
        if self.pending >= 1000 or perf_counter() - self.last_saved >= self.interval:
            started = perf_counter()
            write_json(self.run_dir, self.record)
            finished = perf_counter()
            self.interval = max(30.0, 10 * (finished - started))
            self.pending = 0
            self.last_saved = finished


def _write_record_chunks(stream: TextIO, record: dict[str, Any]) -> None:
    """Encode large run collections one entry or row value at a time."""
    encoder = json.JSONEncoder(ensure_ascii=False, separators=(",", ":"))
    attempt = ("delivery_attempts", "*")
    policies = (
        ("validation_policy",),
        ("configuration", "effective", "validation"),
        attempt + ("rule_settings",),
    )
    dict_paths = {
        (),
        ("configuration",),
        ("configuration", "effective"),
        *policies,
        attempt,
        attempt + ("review",),
        *(
            attempt + (key,)
            for key in (
                "evaluations",
                "resolved_rules",
                "memberships",
            )
        ),
    }
    list_paths = {
        ("entries",),
        ("delivery_attempts",),
        ("warning_acceptances",),
        ("withheld_rows",),
        attempt + ("bundles",),
        attempt + ("review", "accepted_tokens"),
        attempt + ("review", "withheld_rows"),
        *(p + ("clients",) for p in policies),
    }

    def write(value: Any, path: tuple[str, ...]) -> None:
        if path in dict_paths and isinstance(value, dict):
            stream.write("{")
            for index, (key, item) in enumerate(value.items()):
                if not isinstance(key, str):
                    raise TypeError("Run record field names must be strings")
                if index:
                    stream.write(",")
                stream.write(encoder.encode(key) + ":")
                write(item, path + (key,))
            stream.write("}")
        elif path in list_paths and isinstance(value, list):
            stream.write("[")
            for index, item in enumerate(value):
                if index:
                    stream.write(",")
                write(item, path + ("*",))
            stream.write("]")
        else:
            stream.write(encoder.encode(value))

    write(record, ())


def write_json(run_dir: Path, record: dict[str, Any]) -> Path:
    """Stream the authoritative record to a private atomic replacement."""
    started = perf_counter()
    try:
        path = run_dir / "run.json"
        temporary = path.with_suffix(path.suffix + ".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            os.chmod(temporary, 0o600)
            _write_record_chunks(stream, record)
        temporary.replace(path)
        return path
    finally:
        logging.getLogger(__name__).info(
            "JSON checkpoint took %.3fs", perf_counter() - started
        )


def write_report(run_dir: Path, record: dict[str, Any]) -> Path:
    """Replace JSON and its generated HTML view at a workflow boundary."""
    started = perf_counter()
    try:
        record_path = write_json(run_dir, record)
        if len(record["entries"]) >= 1000:
            _write_large_report(run_dir, record)
        else:
            _replace_text(run_dir / "report.html", render_html(record))
        return record_path
    finally:
        logging.getLogger(__name__).info(
            "Report checkpoint took %.3fs (JSON and HTML inclusive)",
            perf_counter() - started,
        )


def _replace_text(path: Path, content: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        os.chmod(temporary, 0o600)
        stream.write(content)
    temporary.replace(path)


def _preview(value: Any) -> Any:
    """Bound individual large measurement values in the HTML index."""
    if isinstance(value, list):
        result = [_preview(item) for item in value[:20]]
        if len(value) > 20:
            result.append(f"… {len(value) - 20} more; see run.json")
        return result
    if isinstance(value, dict):
        return {key: _preview(item) for key, item in islice(value.items(), 20)}
    if isinstance(value, str) and len(value) > 1000:
        return value[:1000] + "… see run.json"
    return value


def _active_bundle_attempt(record: dict[str, Any]) -> dict[str, Any] | None:
    """Keep the last published set available after failed or disabled attempts."""
    return next(
        (
            attempt
            for attempt in reversed(record["delivery_attempts"])
            if attempt["status"] == "completed"
            and attempt.get("configuration", {}).get("bundle_size", 1) != 0
        ),
        None,
    )


def _findings_links(record: dict[str, Any]) -> str:
    """Link the CSV sidecars in the active completed bundle set."""
    active = _active_bundle_attempt(record)
    if active is None:
        return ""
    links = []
    for bundle in active.get("bundles", []):
        artifact = bundle.get("findings_csv")
        if artifact:
            path = artifact["path"]
            links.append(
                f'<li><a href="{escape(path, quote=True)}">{escape(Path(path).name)}</a></li>'
            )
    return (
        "<h2>Bundle findings CSVs</h2><ul>" + "".join(links) + "</ul>" if links else ""
    )


def _write_large_report(run_dir: Path, record: dict[str, Any]) -> None:
    entries = record["entries"]
    counts = Counter(entry["original"]["status"] for entry in entries)
    accepted = {item["token"] for item in record.get("warning_acceptances", [])}
    header = '<!doctype html><html lang="en"><meta charset="utf-8"><title>ImmuKnow run report</title>'
    index = [
        header,
        f"<h1>ImmuKnow run {escape(record['run_id'])}</h1>",
        f"<p>{escape(record['status'])} · {len(entries)} source rows · {counts['completed']} original PDFs · {counts['failed']} failed notices</p>",
        '<p>Client information in this report and its linked files is sensitive. <a href="run.json">Complete run record</a></p>',
        '<p>After inspecting a PDF, accept a warning with <code>immuknow-rebundle RUN --accept-warning TOKEN --reason "Your review reason"</code>.</p>',
        _findings_links(record),
        "<h2>Run checks</h2>",
        _checks_html([_preview(check) for check in record["checks"]]),
        "<h2>Notice pages</h2><ul>",
    ]
    names = set()
    for offset in range(0, len(entries), 100):
        name = f"report-{offset // 100 + 1:05d}.html"
        names.add(name)
        page = [
            header,
            '<p><a href="report.html">Run report</a> · <a href="run.json">Complete run record</a></p>',
            f"<h1>Notices {offset + 1}–{min(offset + 100, len(entries))}</h1>",
        ]
        for entry in entries[offset : offset + 100]:
            title = f"{entry['row_key']} · {entry['client_id'] or 'Missing client ID'} · {entry['original']['status']}"
            page.append(f"<details><summary>{escape(title)}</summary>")
            for label, artifact in (
                ("Original PDF", entry["original"]),
                ("Encrypted PDF", entry["encryption"]),
                ("Bundle", entry["bundle"] or {}),
            ):
                if artifact.get("path"):
                    page.append(
                        f'<p><a href="{escape(artifact["path"], quote=True)}">{label}</a> · SHA-256 {escape(artifact.get("sha256", "")[:12])}</p>'
                    )
            latest = next(
                (
                    attempt
                    for attempt in reversed(record["delivery_attempts"])
                    if entry["row_key"] in attempt.get("evaluations", {})
                ),
                None,
            )
            if latest is None:
                page.append(_checks_html(entry["checks"]))
            else:
                evaluation = latest["evaluations"][entry["row_key"]]
                page.append(f"<h3>Latest evaluation · attempt {latest['number']}</h3>")
                page.append(_checks_html(evaluation["results"]))
                for warning_id, token in evaluation["warning_tokens"].items():
                    state = "Accepted" if token in accepted else "Awaiting review"
                    page.append(
                        f"<p>{escape(warning_id)} · {state}<br><code>{escape(token)}</code></p>"
                    )
            page.append("</details>")
        page.append("</html>")
        _replace_text(run_dir / name, "\n".join(page))
        index.append(
            f'<li><a href="{name}">Notices {offset + 1}–{min(offset + 100, len(entries))}</a></li>'
        )
    index.append("</ul><h2>Delivery attempts</h2>")
    active = _active_bundle_attempt(record)
    for attempt in record["delivery_attempts"]:
        index.append(
            f"<h3>Attempt {attempt['number']} · {escape(attempt['status'])}</h3>"
        )
        index.append(
            _checks_html([_preview(check) for check in attempt.get("checks", [])])
        )
        if attempt is active:
            for bundle in attempt.get("bundles", []):
                index.append(
                    f'<p><a href="{escape(bundle["path"], quote=True)}">{escape(bundle["path"])}</a></p>'
                )
    index.append("</html>")
    _replace_text(run_dir / "report.html", "\n".join(index))
    for path in run_dir.glob("report-*.html"):
        if re.fullmatch(r"report-\d{5}\.html", path.name) and path.name not in names:
            path.unlink()


def render_html(record: dict[str, Any]) -> str:
    """Keep every finding accessible without embedding untrusted HTML or scripts."""
    counts = Counter(entry["original"]["status"] for entry in record["entries"])
    parts = [
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>ImmuKnow run report</title>',
        "<style>body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem}details{border-top:1px solid #ccc;padding:1rem 0}summary{cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere}li{margin:.5rem 0}.fail{color:#a00}.warn{color:#805000}</style>",
        f"<h1>ImmuKnow run {escape(record['run_id'])}</h1>",
        f"<p>{escape(record['status'])} · {len(record['entries'])} source rows · {counts['completed']} original PDFs · {counts['failed']} failed notices</p>",
        "<p>Client information in this report and its linked files is sensitive.</p>",
        '<p>After inspecting a PDF, accept a warning with <code>immuknow-rebundle RUN --accept-warning TOKEN --reason "Your review reason"</code>.</p>',
        _findings_links(record),
        "<h2>Run checks</h2>",
        _checks_html(record["checks"]),
    ]
    accepted = {item["token"] for item in record.get("warning_acceptances", [])}
    for entry in record["entries"]:
        title = f"{entry['row_key']} · {entry['client_id'] or 'Missing client ID'} · {entry['original']['status']}"
        parts.extend(
            [
                f"<details><summary>{escape(title)}</summary>",
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
        latest = next(
            (
                attempt
                for attempt in reversed(record["delivery_attempts"])
                if entry["row_key"] in attempt.get("evaluations", {})
            ),
            None,
        )
        if latest is not None:
            evaluation = latest["evaluations"][entry["row_key"]]
            parts.append(f"<h3>Latest evaluation · attempt {latest['number']}</h3>")
            parts.append(_checks_html(evaluation["results"]))
            if evaluation["warning_tokens"]:
                parts.append("<ul>")
                for warning_id, token in evaluation["warning_tokens"].items():
                    state = "Accepted" if token in accepted else "Awaiting review"
                    parts.append(
                        f"<li>{escape(warning_id)} · {state}<br><code>{escape(token)}</code></li>"
                    )
                parts.append("</ul>")
        else:
            parts.append(_checks_html(entry["checks"]))
        parts.append(
            "<pre>"
            + escape(json.dumps(entry, ensure_ascii=False, indent=2))
            + "</pre></details>"
        )
    parts.append("<h2>Delivery attempts</h2>")
    active = _active_bundle_attempt(record)
    for attempt in record["delivery_attempts"]:
        parts.append(
            f"<details><summary>Attempt {attempt['number']} · {escape(attempt['status'])}</summary>"
        )
        parts.append(_checks_html(attempt.get("checks", [])))
        if attempt is active:
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
