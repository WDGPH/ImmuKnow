"""Large reports stay reviewable while periodic snapshots retain JSON evidence."""

import json
import stat
from pathlib import Path

import pytest

from immuknow import run_report


def sample_record(count: int) -> dict:
    entries = [
        {
            "row_key": f"row-{number:06d}",
            "client_id": f"client-{number:06d}",
            "original": {"status": "completed", "path": f"originals/{number}.pdf"},
            "encryption": {},
            "bundle": None,
            "checks": [],
        }
        for number in range(1, count + 1)
    ]
    return {
        "run_id": "run <unsafe>",
        "status": "completed",
        "input": {"accepted": True},
        "checks": [],
        "entries": entries,
        "delivery_attempts": [],
        "warning_acceptances": [],
    }


def test_periodic_snapshots_write_json_only_by_count_or_elapsed_time(
    tmp_path, monkeypatch
):
    record = sample_record(1)
    now = [0.0]
    monkeypatch.setattr(run_report, "perf_counter", lambda: now[0])
    (tmp_path / "report.html").write_text("unchanged")
    checkpoint = run_report._OutcomeCheckpoint(tmp_path, record)
    for _ in range(999):
        checkpoint.advance()
    assert not (tmp_path / "run.json").exists()
    checkpoint.advance()
    assert json.loads((tmp_path / "run.json").read_text()) == record
    assert stat.S_IMODE((tmp_path / "run.json").stat().st_mode) == 0o600
    record["status"] = "updated"
    now[0] = 30
    checkpoint.advance()
    assert json.loads((tmp_path / "run.json").read_text())["status"] == "updated"
    assert (tmp_path / "report.html").read_text() == "unchanged"


def test_large_report_pages_include_all_rows_and_escape_links_and_warning_tokens(
    tmp_path,
):
    record = sample_record(1001)
    record["entries"][0]["client_id"] = "<unsafe>"
    record["entries"][0]["original"]["path"] = 'originals/"unsafe.pdf'
    record["checks"] = [
        {
            "status": "fail",
            "code": "input.rejected",
            "message": "bad",
            "measurements": {"failed_rows": list(range(1001))},
        }
    ]
    record["delivery_attempts"] = [
        {
            "number": 1,
            "status": "completed",
            "checks": [],
            "bundles": [],
            "evaluations": {
                "row-000001": {
                    "results": [],
                    "warning_tokens": {"warn<id>": "token<unsafe>"},
                }
            },
            "huge": "DO_NOT_EMBED_ATTEMPT",
        }
    ]
    record["warning_acceptances"] = [{"token": "token<unsafe>"}]
    run_report.write_report(tmp_path, record)
    index = (tmp_path / "report.html").read_text()
    pages = sorted(tmp_path.glob("report-*.html"))
    assert len(pages) == 11
    page_text = "\n".join(page.read_text() for page in pages)
    assert all(page.name in index for page in pages)
    assert all(
        page_text.count(f"client-{number:06d}") == 1 for number in range(2, 1002)
    )
    assert (
        "&lt;unsafe&gt;" in page_text
        and 'href="originals/&quot;unsafe.pdf"' in page_text
    )
    assert "warn&lt;id&gt;" in page_text and "token&lt;unsafe&gt;" in page_text
    assert "Accepted" in page_text
    assert "DO_NOT_EMBED_ATTEMPT" not in index + page_text
    assert "981 more; see run.json" in index
    assert json.loads((tmp_path / "run.json").read_text()) == record
    assert Path(tmp_path / "report-00011.html").exists()


def test_failed_streamed_snapshot_preserves_previous_record(tmp_path):
    record = sample_record(1)
    run_report.write_json(tmp_path, record)
    previous = (tmp_path / "run.json").read_bytes()
    record["entries"][0]["unserializable"] = object()
    with pytest.raises(TypeError):
        run_report.write_json(tmp_path, record)
    assert (tmp_path / "run.json").read_bytes() == previous
    assert stat.S_IMODE((tmp_path / "run.json.tmp").stat().st_mode) == 0o600
    del record["entries"][0]["unserializable"]
    record["status"] = "updated"
    run_report.write_json(tmp_path, record)
    assert json.loads((tmp_path / "run.json").read_text()) == record


def test_large_report_only_links_bundles_from_latest_completed_attempt(tmp_path):
    record = sample_record(1001)
    old = {
        "number": 1,
        "status": "completed",
        "checks": [],
        "bundles": [{"path": "bundles/stale.pdf"}],
    }
    newest = {
        "number": 2,
        "status": "failed",
        "checks": [],
        "bundles": [{"path": "bundles/prepared.pdf"}],
    }
    record["delivery_attempts"] = [old, newest]
    run_report.write_report(tmp_path, record)
    index = (tmp_path / "report.html").read_text()
    assert 'href="bundles/stale.pdf"' not in index
    assert 'href="bundles/prepared.pdf"' not in index
    newest["status"] = "completed"
    run_report.write_report(tmp_path, record)
    index = (tmp_path / "report.html").read_text()
    assert 'href="bundles/stale.pdf"' not in index
    assert 'href="bundles/prepared.pdf"' in index
