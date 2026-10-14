"""Saved native runs exercise review, rule changes and replacement recovery."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

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


def test_saved_run_review_and_rebundle_journey(tmp_path: Path) -> None:
    config = tmp_path / "config"
    templates = tmp_path / "templates"
    shutil.copytree(ROOT / "immuknow/config", config)
    shutil.copytree(ROOT / "immuknow/templates", templates)
    parameters = yaml.safe_load((config / "parameters.yaml").read_text())
    # Generate the native originals first; this scenario then exercises the
    # separate delivery API, while orchestration integration is checked centrally.
    parameters["bundling"]["bundle_size"] = 0
    parameters["encryption"]["enabled"] = False
    (config / "parameters.yaml").write_text(yaml.safe_dump(parameters))
    frame = create_test_input_dataframe(num_clients=3)
    frame["overdue_disease"] = "Measles - 2"
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
                "message": "Required summary unavailable",
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
    attempt = bundle_pdfs.bundle_run(run_dir)
    record = json.loads((run_dir / "run.json").read_text())
    first, unknown, evidence = record["entries"]
    assert attempt["status"] == "completed", attempt["checks"]
    assert [entry["routing"]["destination"] for entry in record["entries"]] == [
        "delivery",
        "review",
        "review",
    ]
    assert len(attempt["bundles"]) == 2
    review_bundle = next(
        bundle for bundle in attempt["bundles"] if bundle["destination"] == "review"
    )
    assert review_bundle["row_keys"] == [unknown["row_key"], evidence["row_key"]]
    assert not (run_dir / "overrides.json").exists()
    review = PdfReader(run_dir / review_bundle["path"])
    for entry in (unknown, evidence):
        membership = entry["bundle"]
        sheet_text = " ".join(
            review.pages[index - 1].extract_text()
            for index in range(
                membership["sheet_start_page"], membership["sheet_end_page"] + 1
            )
        )
        for check in entry["checks"]:
            if check["status"] in ("warn", "fail"):
                assert check["code"] in sheet_text
        assert "immuknow-rebundle" in sheet_text
        for index in range(
            membership["notice_start_page"], membership["notice_end_page"] + 1
        ):
            assert "REVIEW" in review.pages[index - 1].extract_text()
            assert (
                float(review.pages[index - 1].mediabox.height)
                == 792 + bundle_pdfs.REVIEW_BAND_PT
            )
    assert "REVIEW" not in " ".join(
        page.extract_text()
        for page in PdfReader(run_dir / first["bundle"]["path"]).pages
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
        if bundle["destination"] == "delivery"
    )
    before = {
        entry["row_key"]: deepcopy(entry["bundle"]) for entry in record["entries"]
    }
    identical = bundle_pdfs.bundle_run(run_dir)
    assert identical["status"] == "completed"
    record = json.loads((run_dir / "run.json").read_text())
    assert {entry["row_key"]: entry["bundle"] for entry in record["entries"]} == before

    # Invalid choices and changed originals cannot replace the current committed set.
    active = {
        path.relative_to(run_dir): path.read_bytes()
        for path in (run_dir / "bundles").rglob("*.pdf")
    }
    memberships = deepcopy(
        [(entry["routing"], entry["bundle"]) for entry in record["entries"]]
    )
    invalid = bundle_pdfs.bundle_run(
        run_dir, accept=["unknown-warning-token"], reason="Reviewed"
    )
    assert invalid["status"] == "failed"
    assert "Unknown or stale warning token" in invalid["checks"][0]["message"]
    damaged = run_dir / first["original"]["path"]
    original = damaged.read_bytes()
    damaged.write_bytes(original + b"tampered")
    assert bundle_pdfs.bundle_run(run_dir)["status"] == "failed"
    damaged.write_bytes(original)
    resource = run_dir / "resources/templates/settings.typ"
    original_resource = resource.read_bytes()
    resource.write_bytes(original_resource + b"\n// changed after review\n")
    changed = bundle_pdfs.bundle_run(run_dir)
    assert changed["status"] == "failed"
    assert "Saved resources changed" in changed["checks"][-1]["message"]
    resource.write_bytes(original_resource)
    payload = run_dir / first["facts"]["path"]
    original_payload = payload.read_bytes()
    payload.write_bytes(original_payload + b" ")
    changed = bundle_pdfs.bundle_run(run_dir)
    assert changed["status"] == "failed"
    assert "Saved notice payload changed" in changed["checks"][-1]["message"]
    payload.write_bytes(original_payload)
    record = json.loads((run_dir / "run.json").read_text())
    assert [
        (entry["routing"], entry["bundle"]) for entry in record["entries"]
    ] == memberships
    assert {
        path.relative_to(run_dir): path.read_bytes()
        for path in (run_dir / "bundles").rglob("*.pdf")
    } == active

    # One interrupted swap leaves backup/state for the next operation to recover.
    replace = Path.replace

    def interrupt_swap(path: Path, destination: Path) -> Path:
        if path.name == "bundles.next":
            raise KeyboardInterrupt(
                "deliberate interruption after backing up active bundles"
            )
        return replace(path, destination)

    with (
        patch.object(Path, "replace", interrupt_swap),
        pytest.raises(KeyboardInterrupt),
    ):
        bundle_pdfs.bundle_run(run_dir, withhold=[])
    assert (run_dir / "bundles.previous").is_dir()
    record = json.loads((run_dir / "run.json").read_text())
    assert record["delivery_attempts"][-1]["status"] == "replacing"
    # A fresh attempt recovers before evaluating the requested warning choices.
    attempt = bundle_pdfs.bundle_run(
        run_dir, accept=["unknown-warning-token"], reason="Reviewed"
    )
    assert attempt["status"] == "failed"
    record = json.loads((run_dir / "run.json").read_text())
    assert record["delivery_attempts"][-2]["status"] == "failed"
    assert (
        record["delivery_attempts"][-2]["checks"][-1]["code"] == "delivery.interrupted"
    )
    assert [
        (entry["routing"], entry["bundle"]) for entry in record["entries"]
    ] == memberships
    assert {
        path.relative_to(run_dir): path.read_bytes()
        for path in (run_dir / "bundles").rglob("*.pdf")
    } == active
    assert not (run_dir / "bundles.previous").exists()
    assert not (run_dir / "bundles.next").exists()
    assert bundle_pdfs.bundle_run(run_dir)["status"] == "completed"
    record = json.loads((run_dir / "run.json").read_text())
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
    shutil.copytree(ROOT / "immuknow/templates", templates)
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
