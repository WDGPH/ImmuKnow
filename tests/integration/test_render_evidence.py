"""Real PDFs survive invalid evidence and cannot be released by deleting findings."""

import json
from copy import deepcopy

import pytest

from immuknow import bundle_pdfs, compile_notices, run_report
from immuknow.orchestrator import run_pipeline
from tests.integration.test_run_accounting import prepare_inputs

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("damage", ["row", "stage", "page", "component"])
def test_invalid_evidence_keeps_original_and_independent_row(
    tmp_path, monkeypatch, damage
):
    source, config, templates, _ = prepare_inputs(tmp_path)
    run_typst = compile_notices.run_typst

    def changed_report(command, **options):
        result = run_typst(command, **options)
        if command[1] == "eval" and any("row-000001" in part for part in command):
            reports = json.loads(result.stdout)
            report = reports[0]
            if damage == "row":
                report["identity"]["row_key"] = "row-000002"
            elif damage == "stage":
                report["checks"][0]["stage"] = "output"
            elif damage == "page":
                report["measurements"]["client"][0]["page"] = report["page_count"] + 1
            else:
                report["components"]["unknown"] = True
            result.stdout = json.dumps(reports)
        return result

    monkeypatch.setattr(compile_notices, "run_typst", changed_report)
    saved = run_pipeline(
        source,
        tmp_path / "runs",
        config_dir=config,
        notice_template=templates / "overdue_agents_v1.en.typ",
    )
    record = json.loads(saved.read_text())
    first, second = record["entries"]
    assert first["original"]["status"] == second["original"]["status"] == "completed"
    assert first.get("render_summary") is None
    assert second["render_summary"]["identity"]["row_key"] == second["row_key"]
    assert "render.evidence_failed" in first["routing"]["failed_checks"]
    assert first["routing"]["destination"] == "review"
    assert not second["routing"]["failed_checks"]
    original = (saved.parent / first["original"]["path"]).read_bytes()
    first["checks"] = [check for check in first["checks"] if check["status"] != "fail"]
    run_report.write_report(saved.parent, record)
    attempt = bundle_pdfs.bundle_run(saved.parent)
    assert attempt["status"] == "completed"
    current = json.loads(saved.read_text())["entries"][0]
    assert "render.evidence_failed" in current["routing"]["failed_checks"]
    assert current["routing"]["destination"] == "review"
    assert (saved.parent / first["original"]["path"]).read_bytes() == original


def test_saved_report_is_rechecked_before_replacing_bundles(tmp_path):
    source, config, templates, _ = prepare_inputs(tmp_path)
    saved = run_pipeline(
        source,
        tmp_path / "runs",
        config_dir=config,
        notice_template=templates / "overdue_agents_v1.en.typ",
    )
    record = json.loads(saved.read_text())
    active = {
        path: path.read_bytes() for path in (saved.parent / "bundles").rglob("*.pdf")
    }
    for damage in ("swapped", "version", "pages"):
        changed = deepcopy(record)
        first, second = changed["entries"]
        if damage == "swapped":
            first["render_summary"] = deepcopy(second["render_summary"])
        elif damage == "version":
            first["render_summary"]["schema_version"] = 1
        else:
            first["render_summary"]["page_count"] += 1
        run_report.write_report(saved.parent, changed)
        attempt = bundle_pdfs.bundle_run(saved.parent)
        assert attempt["status"] == "failed"
        assert {
            path: path.read_bytes()
            for path in (saved.parent / "bundles").rglob("*.pdf")
        } == active
