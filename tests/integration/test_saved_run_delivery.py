"""Saved native runs exercise review, rule changes and replacement recovery."""

from __future__ import annotations

from tests.fixtures.project import copy_project

import csv
import json
import os
import shutil
import subprocess
import sys
from copy import deepcopy
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path

import pytest
import yaml
from pypdf import PdfReader

from immuknow import bundle_pdfs, run_report
from immuknow.data_models import ClientRecord
from immuknow.encrypt_notices import encrypt_notice
from immuknow.orchestrator import run_pipeline
from tests.fixtures.sample_input import create_test_input_dataframe

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


def test_saved_run_review_and_rebundle_journey(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "config"
    templates = tmp_path / "templates"
    shutil.copytree(ROOT / "immuknow/config", config)
    copy_project(templates)
    parameters = yaml.safe_load((config / "parameters.yaml").read_text())
    # Generate the native originals first; this scenario then exercises the
    # separate delivery API, while orchestration integration is checked centrally.
    parameters["bundling"]["bundle_size"] = 0
    parameters["encryption"]["enabled"] = False
    (config / "parameters.yaml").write_text(yaml.safe_dump(parameters))
    frame = create_test_input_dataframe(num_clients=3)
    frame["overdue_disease"] = "Measles - 2"
    frame["overdue_agent"] = "M"
    frame["school_id"] = ["school-a", "", "school-a"]
    frame.loc[1, "date_of_birth"] = ""
    source = tmp_path / "clients.csv"
    frame.to_csv(source, index=False)
    saved = run_pipeline(
        source,
        tmp_path / "runs",
        config_dir=config,
        notice_template=templates / "overdue_diseases_v1.en.typ",
    )
    run_dir = saved.parent
    record = json.loads(saved.read_text())
    record["configuration"]["effective"]["bundling"] = {
        "bundle_size": 2,
        "group_by": "school",
    }
    first, unknown, evidence = record["entries"]
    evidence["checks"].extend(
        [
            {
                "code": "render.evidence_failed",
                "stage": "render",
                "status": "fail",
                "message": '=Required, "summary"\nunavailable',
            },
        ]
    )
    original_hashes = {
        entry["row_key"]: entry["original"]["sha256"] for entry in record["entries"]
    }
    original_text = {
        entry["row_key"]: " ".join(
            page.extract_text()
            for page in PdfReader(run_dir / entry["original"]["path"]).pages
        )
        for entry in record["entries"]
    }

    # Successful encryption really decrypts; unknown DOB never becomes an empty password.
    for entry in (first, unknown):
        encrypted = run_dir / "encrypted" / f"{entry['row_key']}.pdf"
        entry["encryption"] = {"requested": True, "status": "not_run"}
        try:
            encrypt_notice(
                ClientRecord(**entry["facts"]["prepared"]),
                run_dir / entry["original"]["path"],
                encrypted,
                {},
            )
            entry["encryption"].update(
                status="completed", **run_report.artifact_record(encrypted, run_dir)
            )
        except ValueError as exc:
            entry["encryption"]["status"] = "failed"
            run_report.add_check(
                entry, "encryption.failed", "delivery", "fail", str(exc)
            )
    assert PdfReader(run_dir / first["encryption"]["path"]).decrypt("20150102")
    assert unknown["encryption"]["status"] == "failed"
    assert not (run_dir / "encrypted" / f"{unknown['row_key']}.pdf").exists()

    run_report.write_report(run_dir, record)
    link_tokens = [
        token
        for code, token in record["delivery_attempts"][-1]["evaluations"][
            first["row_key"]
        ]["warning_tokens"].items()
        if code.startswith("content.multiple_links:")
    ]
    monkeypatch.setenv("TYPST_BIN", str(tmp_path / "missing-typst"))
    attempt = bundle_pdfs.bundle_run(
        run_dir, accept=link_tokens, reason="Reviewed the first notice's contact links"
    )
    prior_attempt = deepcopy(record["delivery_attempts"][-1])
    record = json.loads((run_dir / "run.json").read_text())
    assert record["delivery_attempts"][-2] == prior_attempt
    assert attempt["engine"]["pdf_library_version"] == version("pypdf")
    assert attempt["engine"]["code"]
    first, unknown, evidence = record["entries"]
    assert attempt["status"] == "completed", attempt["checks"]
    assert [entry["routing"]["destination"] for entry in record["entries"]] == [
        "delivery",
        "review",
        "review",
    ]
    assert len(attempt["bundles"]) == 2
    assert all(bundle["destination"] == "bundle" for bundle in attempt["bundles"])
    assert first["bundle"]["path"] == evidence["bundle"]["path"]
    assert first["bundle"]["path"] != unknown["bundle"]["path"]
    assert all(
        Path(bundle["path"]).parent.parent == Path("bundles")
        for bundle in attempt["bundles"]
    )
    assert not (run_dir / "overrides.json").exists()
    for entry in (first, unknown, evidence):
        membership = entry["bundle"]
        bundled = PdfReader(run_dir / membership["path"])
        original = PdfReader(run_dir / entry["original"]["path"])
        pages = bundled.pages[
            membership["notice_start_page"] - 1 : membership["notice_end_page"]
        ]
        assert len(pages) == len(original.pages)
        for actual, source_page in zip(pages, original.pages, strict=True):
            assert actual.mediabox == source_page.mediabox
            assert actual.extract_text() == source_page.extract_text()

            def links(page):
                return [
                    str(ref.get_object().get("/A", {}).get("/URI", ""))
                    for ref in page.get("/Annots", [])
                ]

            assert links(actual) == links(source_page)
    artifact = next(
        bundle
        for bundle in attempt["bundles"]
        if evidence["row_key"] in bundle["row_keys"]
    )
    csv_path = run_dir / artifact["findings_csv"]["path"]
    assert csv_path == (run_dir / artifact["path"]).with_suffix(".csv")
    with csv_path.open(newline="") as stream:
        findings = list(csv.DictReader(stream))
    failure = next(
        row
        for row in findings
        if row["row_key"] == evidence["row_key"]
        and row["code"] == "render.evidence_failed"
    )
    assert failure["effective_status"] == "fail"
    assert failure["message"] == '\'=Required, "summary"\nunavailable'
    assert failure["bundle_path"] == evidence["bundle"]["path"]
    assert int(failure["notice_start_page"]) == evidence["bundle"]["notice_start_page"]
    assert (
        artifact["findings_csv"]["sha256"] == sha256(csv_path.read_bytes()).hexdigest()
    )
    assert artifact["findings_csv"]["rows"] == len(findings)
    assert {row["row_key"] for row in findings} <= set(artifact["row_keys"])
    assert any(
        row["row_key"] == first["row_key"]
        and row["code"] == "content.multiple_links"
        and row["warning_accepted"] == "true"
        for row in findings
    )
    findings_before = deepcopy([entry["checks"] for entry in record["entries"]])

    # Relocate the saved run and remove every original source/project location.
    moved = tmp_path / "relocated-run"
    shutil.move(run_dir, moved)
    run_dir = moved
    source.unlink()
    shutil.rmtree(templates)
    shutil.rmtree(config)
    tokens = list(
        record["delivery_attempts"][-1]["evaluations"][unknown["row_key"]][
            "warning_tokens"
        ].values()
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "immuknow.rebundle",
            str(run_dir),
            *[arg for token in tokens for arg in ("--accept-warning", token)],
            "--reason",
            "Reviewed source and original",
            "--withhold",
            first["row_key"],
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "TYPST_BIN": str(tmp_path / "missing-typst")},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    record = json.loads((run_dir / "run.json").read_text())
    first, unknown, evidence = record["entries"]
    assert [entry["routing"]["destination"] for entry in record["entries"]] == [
        "review",
        "delivery",
        "review",
    ]
    assert unknown["encryption"]["status"] == "failed"
    assert [entry["checks"] for entry in record["entries"]] == findings_before
    delivery = PdfReader(run_dir / unknown["bundle"]["path"])
    assert "REVIEW" not in " ".join(page.extract_text() for page in delivery.pages)
    assert "Unknown" in next(
        bundle["group_name"]
        for bundle in record["delivery_attempts"][-1]["bundles"]
        if unknown["row_key"] in bundle["row_keys"]
    )
    before = {
        entry["row_key"]: deepcopy(entry["bundle"]) for entry in record["entries"]
    }
    identical = bundle_pdfs.bundle_run(run_dir)
    assert identical["status"] == "completed"
    record = json.loads((run_dir / "run.json").read_text())
    for entry in record["entries"]:
        old = before[entry["row_key"]]
        current = entry["bundle"]
        assert current["path"] != old["path"]
        assert current["sha256"] == old["sha256"]
        assert (current["notice_start_page"], current["notice_end_page"]) == (
            old["notice_start_page"],
            old["notice_end_page"],
        )

    # Invalid choices and failed CSV writes preserve committed artifacts.
    active = {
        path.relative_to(run_dir): path.read_bytes()
        for path in (run_dir / "bundles").rglob("*")
        if path.is_file()
    }
    memberships = deepcopy(
        [(entry["routing"], entry["bundle"]) for entry in record["entries"]]
    )

    def fail_csv(*args, **kwargs):
        raise OSError("CSV write failed")

    with monkeypatch.context() as failure:
        failure.setattr(bundle_pdfs, "_write_findings", fail_csv)
        failed_csv = bundle_pdfs.bundle_run(run_dir)
    assert failed_csv["status"] == "failed"
    assert failed_csv["bundles"] == []
    assert "CSV write failed" in failed_csv["checks"][-1]["message"]
    assert {
        path.relative_to(run_dir): path.read_bytes()
        for path in (run_dir / "bundles").rglob("*")
        if path.is_file()
        and not any(part.endswith(".incomplete") for part in path.parts)
    } == active
    invalid = bundle_pdfs.bundle_run(
        run_dir, accept=["unknown-warning-token"], reason="Reviewed"
    )
    assert invalid["status"] == "failed"
    assert "Unknown or stale warning token" in invalid["checks"][0]["message"]
    record = json.loads((run_dir / "run.json").read_text())
    assert [
        (entry["routing"], entry["bundle"]) for entry in record["entries"]
    ] == memberships
    assert {
        path.relative_to(run_dir): path.read_bytes()
        for path in (run_dir / "bundles").rglob("*")
        if path.is_file()
        and not any(part.endswith(".incomplete") for part in path.parts)
    } == active

    for entry in record["entries"]:
        assert (
            sha256((run_dir / entry["original"]["path"]).read_bytes()).hexdigest()
            == original_hashes[entry["row_key"]]
        )
        assert (
            " ".join(
                page.extract_text()
                for page in PdfReader(run_dir / entry["original"]["path"]).pages
            )
            == original_text[entry["row_key"]]
        )


def test_saved_rule_changes_recheck_originals_and_preserve_earlier_results(tmp_path):
    config = tmp_path / "config"
    templates = tmp_path / "templates"
    shutil.copytree(ROOT / "immuknow/config", config)
    copy_project(templates)
    parameters = yaml.safe_load((config / "parameters.yaml").read_text())
    parameters["bundling"] = {"bundle_size": 10}
    parameters["encryption"]["enabled"] = False
    code = "layout.address_outside_window"
    parameters["validation"] = {
        "rules": {code: {"severity": "fail", "reason": "Use narrow window"}}
    }
    (config / "parameters.yaml").write_text(yaml.safe_dump(parameters))
    settings = templates / "settings.typ"
    settings.write_text(settings.read_text().replace("height: 81pt", "height: 30pt"))
    source = tmp_path / "clients.csv"
    frame = create_test_input_dataframe(num_clients=1)
    frame["overdue_disease"] = "Measles - 2"
    frame["overdue_agent"] = "M"
    frame.to_csv(source, index=False)
    saved = run_pipeline(
        source,
        tmp_path / "runs",
        config_dir=config,
        notice_template=templates / "overdue_diseases_v1.en.typ",
    )
    record = json.loads(saved.read_text())
    entry = record["entries"][0]
    row = entry["row_key"]
    previous = deepcopy(record["delivery_attempts"][0])
    assert code in previous["evaluations"][row]["failed_checks"]
    assert entry["routing"]["destination"] == "review"
    assert (
        next(check for check in entry["checks"] if check["code"] == code)["status"]
        == "warn"
    )
    original = (saved.parent / entry["original"]["path"]).read_bytes()
    policy_file = tmp_path / "rules.json"
    policy_file.write_text("{}")
    command = [sys.executable, "-m", "immuknow.rebundle", str(saved.parent)]
    result = subprocess.run(
        command + ["--policy", str(policy_file)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    record = json.loads(saved.read_text())
    current = record["delivery_attempts"][-1]["evaluations"][row]
    assert code not in current["failed_checks"]
    assert current["settings"][code]["severity"] == "warn"
    assert any(key.startswith(code + ":") for key in current["warning_tokens"])
    result = subprocess.run(
        command
        + [
            arg
            for token in current["warning_tokens"].values()
            for arg in ("--accept-warning", token)
        ]
        + ["--reason", "Inspected window placement"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    record = json.loads(saved.read_text())
    assert record["entries"][0]["routing"]["destination"] == "delivery"
    assert record["delivery_attempts"][0] == previous
    assert (saved.parent / entry["original"]["path"]).read_bytes() == original
    report = (saved.parent / "report.html").read_text()
    assert "Latest evaluation" in report
    assert "Accepted" in report
    assert all(token in report for token in current["warning_tokens"].values())
