"""A new bundle set never overwrites the last published set on failure."""

import json
from pathlib import Path

import pytest
from pypdf import PdfWriter

from immuknow import bundle_pdfs, run_report


@pytest.fixture
def saved_run(tmp_path):
    original = tmp_path / "originals" / "row-000001.pdf"
    original.parent.mkdir()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(original)
    record = {
        "format_version": run_report.RUN_FORMAT_VERSION,
        "run_id": "publication-test",
        "status": "completed",
        "input": {"accepted": True},
        "configuration": {"effective": {"bundling": {"bundle_size": 10}}},
        "resources": {},
        "checks": [],
        "warning_acceptances": [],
        "withheld_rows": [],
        "delivery_attempts": [],
        "entries": [
            {
                "row_key": "row-000001",
                "client_id": "0000000001",
                "facts": {"prepared": {}},
                "original": {
                    "status": "completed",
                    "pages": 1,
                    **run_report.artifact_record(original, tmp_path),
                },
                "encryption": {},
                "routing": {},
                "bundle": None,
                "checks": [
                    {
                        "code": "output.readable",
                        "stage": "output",
                        "status": "pass",
                        "message": "PDF can be opened",
                    }
                ],
            }
        ],
    }
    run_report.write_report(tmp_path, record)
    first = bundle_pdfs.bundle_run(tmp_path)
    assert first["status"] == "completed"
    return tmp_path


def read_record(run_dir):
    return json.loads((run_dir / "run.json").read_text())


def test_failed_json_commit_keeps_old_membership_and_ignores_finished_orphan(
    saved_run, monkeypatch
):
    before = read_record(saved_run)
    previous = before["entries"][0]["bundle"]
    original_write = run_report.write_json

    def fail_commit(run_dir, record):
        if record["delivery_attempts"][-1]["status"] == "completed":
            raise OSError("Final record could not be saved")
        return original_write(run_dir, record)

    with monkeypatch.context() as failure:
        failure.setattr(run_report, "write_json", fail_commit)
        failed = bundle_pdfs.bundle_run(saved_run)
    assert failed["status"] == "failed"
    assert read_record(saved_run)["entries"][0]["bundle"] == previous
    orphan = saved_run / failed["directory"]
    assert orphan.is_dir()
    assert not orphan.name.endswith(".incomplete")
    previous_bytes = (saved_run / previous["path"]).read_bytes()

    retry = bundle_pdfs.bundle_run(saved_run)
    assert retry["status"] == "completed"
    assert retry["reused_from"] == 1
    assert retry["directory"] != failed["directory"]
    assert orphan.is_dir()
    assert (saved_run / previous["path"]).read_bytes() == previous_bytes


def test_failed_html_write_preserves_successful_json_commit(saved_run, monkeypatch):
    previous = read_record(saved_run)["entries"][0]["bundle"]

    def fail_html(*args):
        raise OSError("HTML could not be saved")

    with monkeypatch.context() as failure:
        failure.setattr(run_report, "_replace_text", fail_html)
        with pytest.raises(OSError, match="HTML could not be saved"):
            bundle_pdfs.bundle_run(saved_run)
    saved = read_record(saved_run)
    committed = saved["delivery_attempts"][-1]
    assert committed["status"] == "completed"
    assert saved["entries"][0]["bundle"]["path"] != previous["path"]
    assert (saved_run / previous["path"]).is_file()
    assert (saved_run / committed["bundles"][0]["path"]).is_file()
    retry = bundle_pdfs.bundle_run(saved_run)
    assert retry["status"] == "completed"
    assert retry["reused_from"] == committed["number"]


@pytest.mark.parametrize("after_rename", [False, True])
def test_interrupted_rename_leaves_old_membership_and_directory_alone(
    saved_run, monkeypatch, after_rename
):
    previous = read_record(saved_run)["entries"][0]["bundle"]
    original_rename = Path.rename
    abandoned = []

    def interrupt(path, target):
        if path.name.endswith(".incomplete"):
            abandoned.append(Path(target) if after_rename else path)
            if after_rename:
                original_rename(path, target)
            raise KeyboardInterrupt
        return original_rename(path, target)

    with monkeypatch.context() as failure:
        failure.setattr(Path, "rename", interrupt)
        with pytest.raises(KeyboardInterrupt):
            bundle_pdfs.bundle_run(saved_run)
    saved = read_record(saved_run)
    assert saved["delivery_attempts"][-1]["status"] == "running"
    assert saved["entries"][0]["bundle"] == previous
    assert len(abandoned) == 1 and abandoned[0].is_dir()
    retry = bundle_pdfs.bundle_run(saved_run)
    assert retry["status"] == "completed"
    assert retry["reused_from"] == 1
    assert saved_run / retry["directory"] != abandoned[0]
    assert abandoned[0].is_dir()
    assert (saved_run / previous["path"]).is_file()
