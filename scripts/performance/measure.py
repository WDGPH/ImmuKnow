"""Complete-command measurement and post-timing verification for fictional runs."""

from __future__ import annotations

import argparse
import collections
import csv
import gzip
import hashlib
import json
import os
import shutil
import time
from pathlib import Path


def digest(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def effective(entry, version):
    if version == 1:
        return entry["effective_checks"]
    observations = entry["checks"]
    observed = {c["finding_key"]: c for c in observations}
    assert len(observed) == len(observations)
    results = entry["effective_checks"]
    assert len({c["finding_key"] for c in results}) == len(results)
    assert set(observed) == {c["finding_key"] for c in results}
    return [{**observed[c["finding_key"]], **c} for c in results]


def check_semantics(checks):
    keys = ("code", "status", "component", "page", "subjects", "message")
    output = []
    for check in checks:
        value = {key: check[key] for key in keys if key in check}
        if "measurements" in check and not (
            check["code"].startswith("layout.") and check["status"] == "pass"
        ):
            value["measurements"] = check["measurements"]
        output.append(value)
    return output


def semantic_evidence(entry, version):
    evidence = json.loads(
        json.dumps(entry["render_report" if version == 1 else "saved_evidence"])
    )
    for key in (
        "notice",
        "checks",
        "schema_version",
        "saved_evidence_version",
        "facts_sha256",
        "blocked_checks",
    ):
        evidence.pop(key, None)
    measurements = evidence.get("measurements", {})
    measurements.pop("header", None)
    geometry = {
        "x_pt",
        "y_pt",
        "width_pt",
        "height_pt",
        "end_y_pt",
        "window_x_pt",
        "window_y_pt",
        "window_width_pt",
        "window_height_pt",
        "window_padding_pt",
    }
    for name in ("address", "client", "signature"):
        for item in measurements.get(name, []):
            for key in geometry:
                item.pop(key, None)
    if version == 2:
        assert entry["saved_evidence"]["facts_sha256"] == digest(entry["notice"])
    return evidence


def verify(record_path, fixture, expected=None):
    record = json.loads(record_path.read_text())
    root = record_path.parent
    version = record["run_schema_version"]
    assert version in (1, 2), version
    with (fixture / "clients.csv").open(newline="") as f:
        source = list(csv.DictReader(f))
    entries = record["entries"]
    assert len(entries) == len(source)
    assert len({e["row_key"] for e in entries}) == len(entries)
    assert [e["client_id"] for e in entries] == [r["client_id"] for r in source]
    rows = {}
    codes = collections.Counter()
    for entry in entries:
        original = entry["original"]
        assert original["status"] == "completed", entry
        pdf_hash = file_hash(root / original["path"])
        assert pdf_hash == original["sha256"]
        observed = check_semantics(entry["checks"])
        resolved = check_semantics(effective(entry, version))
        codes.update((c["code"], c["status"]) for c in resolved)
        value = {
            "client_id": entry["client_id"],
            "assignment": entry["assignment"],
            "notice_sha256": digest(entry["notice"]),
            "observed_sha256": digest(observed),
            "effective_sha256": digest(resolved),
            "semantic_evidence_sha256": digest(semantic_evidence(entry, version)),
            "pdf_sha256": pdf_hash,
            "pages": original["pages"],
            "route": entry["routing"],
        }
        if expected is not None:
            assert value == expected["rows"][entry["row_key"]], (
                entry["row_key"],
                value,
                expected["rows"][entry["row_key"]],
            )
        rows[entry["row_key"]] = value
    members = []
    bundles = []
    for bundle in record["bundles"]:
        assert file_hash(root / bundle["path"]) == bundle["sha256"]
        pages = 0
        for key in bundle["members"]:
            entry = entries[int(key.removeprefix("row-")) - 1]
            assert entry["row_key"] == key
            member = entry["bundle"]
            assert member["path"] == bundle["path"]
            assert member["notice_start_page"] == pages + 1
            pages += entry["original"]["pages"]
            assert member["notice_end_page"] == pages
            members.append(key)
        assert pages == bundle["pages"]
        bundles.append(
            {
                "route": bundle["route"],
                "group": bundle["group"],
                "pages": pages,
                "members": bundle["members"],
            }
        )
    assert len(members) == len(entries) and set(members) == set(rows)
    csv_bytes = 0
    if version == 2:
        exports = record["exports"]
        assert exports["record_revision"] == record["record_revision"]
        for name in ("records", "findings"):
            path = root / exports[name]["path"]
            assert file_hash(path) == exports[name]["sha256"]
            csv_bytes += path.stat().st_size
            with path.open(newline="") as f:
                values = list(csv.DictReader(f))
            assert all(
                int(v["record_revision"]) == record["record_revision"] for v in values
            )
            if name == "records":
                assert [v["row_key"] for v in values] == list(rows)
        assert not (root / "report.html").exists()
        assert not list(root.glob("bundles-*/*.csv"))
        assert not (root / "facts").exists()
    result = {
        "status": record["status"],
        "schema_version": version,
        "row_count": len(entries),
        "pages": sum(v["pages"] for v in rows.values()),
        "rows": rows,
        "bundles": bundles,
        "original_pdf_bytes": sum(
            (root / e["original"]["path"]).stat().st_size for e in entries
        ),
        "bundle_pdf_bytes": sum(
            (root / b["path"]).stat().st_size for b in record["bundles"]
        ),
        "findings": {"|".join(k): v for k, v in sorted(codes.items())},
        "routing": dict(collections.Counter(v["route"] for v in rows.values())),
        "record_bytes": record_path.stat().st_size,
        "html_bytes": (root / "report.html").stat().st_size
        if (root / "report.html").exists()
        else 0,
        "bundle_csv_bytes": sum(p.stat().st_size for p in root.glob("bundles-*/*.csv")),
        "run_csv_bytes": csv_bytes,
        "timings": record["timings"],
    }
    if expected is not None:
        assert result["bundles"] == expected["bundles"]
        assert result["findings"] == expected["findings"]
        assert result["routing"] == expected["routing"]
    return result


def measure(binary, fixture, output):
    output.mkdir(parents=True, exist_ok=False)
    command = [
        str(binary),
        "--progress",
        "off",
        "run",
        str(fixture / "clients.csv"),
        "--notice-assignments",
        str(fixture / "assignments.json"),
        "--templates",
        str(fixture / "project/templates"),
        "--config",
        str(fixture / "project/config"),
        "--output",
        str(output / "runs"),
        "--timestamp",
        "1793534400",
        "--compile-workers",
        "2",
        "--encryption-workers",
        "2",
        "--bundle-workers",
        "4",
    ]
    start = time.perf_counter()
    pid = os.fork()
    if pid == 0:
        try:
            for target, name in ((1, "stdout.txt"), (2, "stderr.txt")):
                fd = os.open(
                    output / name, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600
                )
                os.dup2(fd, target)
                os.close(fd)
            os.execv(str(binary), command)
        except OSError:
            import traceback

            traceback.print_exc()
            os._exit(127)
    _, status, usage = os.wait4(pid, 0)
    measured = {
        "wall_seconds": time.perf_counter() - start,
        "exit_status": os.waitstatus_to_exitcode(status),
        "user_cpu_seconds": usage.ru_utime,
        "system_cpu_seconds": usage.ru_stime,
        "cpu_seconds": usage.ru_utime + usage.ru_stime,
        "peak_rss_bytes": usage.ru_maxrss * 1024,
        "major_page_faults": usage.ru_majflt,
        "block_input_operations": usage.ru_inblock,
        "block_output_operations": usage.ru_oublock,
        "command": command,
        "binary_sha256": file_hash(binary),
        "cache_conditions": "Fresh process; warm uncontrolled OS cache; verification outside timing.",
    }
    (output / "os-measurement.json").write_text(json.dumps(measured, indent=2) + "\n")
    return measured


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("measure")
    p.add_argument("binary", type=Path)
    p.add_argument("fixture", type=Path)
    p.add_argument("output", type=Path)
    p = sub.add_parser("verify")
    p.add_argument("record", type=Path)
    p.add_argument("fixture", type=Path)
    p.add_argument("manifest", type=Path)
    p.add_argument("--expected", type=Path)
    args = parser.parse_args()
    if args.action == "measure":
        print(json.dumps(measure(args.binary, args.fixture, args.output)), flush=True)
    else:
        expected = json.loads(args.expected.read_text()) if args.expected else None
        result = verify(args.record, args.fixture, expected)
        args.manifest.write_text(json.dumps(result, indent=2) + "\n")
        with (
            args.record.open("rb") as source,
            gzip.open(
                args.manifest.with_suffix(".run.json.gz"), "wb", compresslevel=1
            ) as target,
        ):
            shutil.copyfileobj(source, target)
        print(
            json.dumps(
                {k: v for k, v in result.items() if k not in ("rows", "bundles")}
            ),
            flush=True,
        )
