"""One saved native run exercises review, overrides, relocation and replacement recovery."""

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
                "message": "Synthetic unavailable summary",
            },
            {
                "code": "output.evidence_unavailable",
                "stage": "output",
                "status": "warn",
                "message": "Saved original is readable but checking did not complete",
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
            run_report.add_check(
                entry,
                "delivery.encryption_failed",
                "delivery",
                "warn",
                "Requested encryption failed",
            )
    assert PdfReader(run_dir / first["encryption"]["path"]).decrypt("20150102")
    assert unknown["encryption"]["status"] == "failed"
    assert not (run_dir / "encrypted" / f"{unknown['row_key']}.pdf").exists()

    attempt = bundle_pdfs.bundle_run(run_dir, record)
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
    assert (run_dir / "overrides.json").is_file()
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
    overrides = {
        "allow_delivery_warnings": [],
        "clients": {unknown["client_id"]: "delivery", first["client_id"]: "review"},
    }
    (run_dir / "overrides.json").write_text(json.dumps(overrides))
    result = subprocess.run(
        [sys.executable, "-m", "immuknow.rebundle", str(run_dir)],
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
    identical = bundle_pdfs.bundle_run(run_dir, record)
    assert identical["status"] == "completed"
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
        run_dir, record, {"allow_delivery_warnings": ["data.school_unmatced"]}
    )
    assert invalid["status"] == "failed"
    assert "Unknown warning code" in invalid["checks"][0]["message"]
    damaged = run_dir / first["original"]["path"]
    original = damaged.read_bytes()
    damaged.write_bytes(original + b"tampered")
    assert bundle_pdfs.bundle_run(run_dir, record, overrides)["status"] == "failed"
    damaged.write_bytes(original)
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
        bundle_pdfs.bundle_run(
            run_dir, record, {"clients": {first["client_id"]: "delivery"}}
        )
    assert (run_dir / "bundles.previous").is_dir()
    assert record["delivery_attempts"][-1]["status"] == "replacing"
    # Recovery reads saved state, as a fresh CLI invocation would.
    record = json.loads((run_dir / "run.json").read_text())
    bundle_pdfs.recover_delivery(run_dir, record)
    assert record["delivery_attempts"][-1]["status"] == "failed"
    assert [
        (entry["routing"], entry["bundle"]) for entry in record["entries"]
    ] == memberships
    assert {
        path.relative_to(run_dir): path.read_bytes()
        for path in (run_dir / "bundles").rglob("*.pdf")
    } == active
    assert not (run_dir / "bundles.previous").exists()
    assert not (run_dir / "bundles.next").exists()
    assert bundle_pdfs.bundle_run(run_dir, record, overrides)["status"] == "completed"
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
