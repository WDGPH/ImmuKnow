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


def test_slow_snapshots_lengthen_interval_but_outcome_limit_still_saves(
    tmp_path, monkeypatch
):
    now = [0.0]
    durations = iter([8.0, 0.1, 0.1])
    saved = []
    monkeypatch.setattr(run_report, "perf_counter", lambda: now[0])

    def write_json(*args):
        saved.append(now[0])
        now[0] += next(durations)

    monkeypatch.setattr(run_report, "write_json", write_json)
    checkpoint = run_report._OutcomeCheckpoint(tmp_path, sample_record(1))
    now[0] = 30
    checkpoint.advance()
    now[0] = 68
    checkpoint.advance()
    assert saved == [30]
    for _ in range(999):
        checkpoint.advance()
    assert saved == [30, 68]
    now[0] = 98.2
    checkpoint.advance()
    assert saved == [30, 68, 98.2]


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


def test_chunked_record_matches_standard_json_with_policies_and_prior_attempts(
    tmp_path,
):
    record = sample_record(2)
    record["entries"][0]["source"] = {"name": 'Adèle · "quoted"\n😀'}
    policy = {"rules": {}, "clients": [{"selector": {"row_key": "row-000001"}}]}
    record["configuration"] = {"effective": {"validation": policy}}
    record["validation_policy"] = policy
    record["warning_acceptances"] = [{"token": "é<token>", "reason": "Reviewed"}]
    record["withheld_rows"] = ["row-000002"]
    record["delivery_attempts"] = [
        {
            "number": number,
            "rule_settings": policy,
            "review": {"accepted_tokens": ["é<token>"], "withheld_rows": []},
            "evaluations": {"row-000001": {"results": [], "score": 1.25}},
            "resolved_rules": {"row-000001": {}},
            "memberships": {"row-000001": {"bundle": None}},
            "previous_memberships": {"row-000001": {}},
            "bundles": [{"row_keys": ["row-000001"]}],
        }
        for number in (1, 2)
    ]
    expected = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    run_report.write_json(tmp_path, record)
    assert (tmp_path / "run.json").read_text() == expected
    assert json.loads(expected) == record


def test_invalid_split_mapping_key_preserves_previous_json(tmp_path):
    record = sample_record(1)
    run_report.write_json(tmp_path, record)
    previous = (tmp_path / "run.json").read_bytes()
    record[123] = "invalid field name"
    with pytest.raises(TypeError, match="field names must be strings"):
        run_report.write_json(tmp_path, record)
    assert (tmp_path / "run.json").read_bytes() == previous


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
