"""Input failures stop the complete file; corrected facts can produce notices."""

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
from pypdf import PdfReader

from immuknow.orchestrator import run_pipeline
from tests.integration.test_native_pipeline import ROOT, prepare_cohort, run_cli

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("mode", ["cli", "api"])
@pytest.mark.parametrize("selection", ["template", "manifest"])
def test_bad_history_rejects_every_row_through_both_entry_points(
    tmp_path, mode, selection
):
    command, output, config = prepare_cohort(
        tmp_path, ("en", "en", "en"), encrypted=True
    )
    source = command[3]
    frame = pd.read_csv(source, dtype=str, keep_default_na=False)
    frame.loc[1, "imms_given"] = "May 1, 2020 - MMR - INVALID"
    frame.loc[2, "imms_given"] = (
        "Feb 31, 2020 - Not Specified - Valid; May 1, 2020 - MMR - Valid - Invalid"
    )
    frame.to_csv(source, index=False)
    template = ROOT / "immuknow/templates/overdue_agents_v1.en.typ"
    assignments = command[-1]
    if selection == "template":
        command[-2:] = ["--template", str(template)]
    if mode == "cli":
        result = run_cli(command, tmp_path)
        assert result.returncode == 1, result.stdout + result.stderr
        (saved,) = output.glob("*/run.json")
    else:
        saved = run_pipeline(
            Path(source),
            output,
            config_dir=config,
            notice_template=template if selection == "template" else None,
            notice_assignments=Path(assignments) if selection == "manifest" else None,
        )
    record = json.loads(saved.read_text())
    assert record["status"] == "rejected_input"
    assert record["input"]["accepted"] is False
    assert len(record["entries"]) == 3
    assert all(entry["original"]["status"] == "not_run" for entry in record["entries"])
    assert all(
        entry["encryption"]["status"] == "not_run" for entry in record["entries"]
    )
    assert not record["delivery_attempts"]
    assert not list(saved.parent.rglob("*.pdf"))
    problems = [
        (entry["row_key"], check)
        for entry in record["entries"]
        for check in entry["checks"]
        if check["code"] == "source.history_invalid"
    ]
    assert [key for key, _ in problems] == ["row-000002", "row-000003", "row-000003"]
    assert all(
        check["status"] == "fail" and check["measurements"]["column"] == "imms_given"
        for _, check in problems
    )
    assert (
        record["entries"][1]["source"]["values"]["imms_given"]
        == frame.loc[1, "imms_given"]
    )
    rebundle = subprocess.run(
        [sys.executable, "-m", "immuknow.rebundle", str(saved.parent)],
        capture_output=True,
        text=True,
    )
    assert rebundle.returncode == 1
    assert "Input checks did not accept" in rebundle.stderr
    assert json.loads(saved.read_text()) == record


@pytest.mark.parametrize("selection", ["template", "manifest"])
def test_identifier_and_assignment_problems_are_collected_before_rejection(
    tmp_path, selection
):
    command, output, _ = prepare_cohort(tmp_path, ("en", "en", "en", "en"))
    source = command[3]
    frame = pd.read_csv(source, dtype=str, keep_default_na=False)
    frame.loc[1, "client_id"] = frame.loc[0, "client_id"]
    frame.loc[3, "client_id"] = "０００００００００４"
    frame.to_csv(source, index=False)

    assignments = Path(command[-1])
    rows = json.loads(assignments.read_text())
    rows[3]["client_id"] = frame.loc[3, "client_id"]
    rows.pop(2)
    assignments.write_text(json.dumps(rows))
    if selection == "template":
        command[-2:] = [
            "--template",
            str(ROOT / "immuknow/templates/overdue_agents_v1.en.typ"),
        ]
    result = run_cli(command, tmp_path)
    assert result.returncode == 1
    (saved,) = output.glob("*/run.json")
    record = json.loads(saved.read_text())
    assert record["status"] == "rejected_input"
    codes = [
        [check["code"] for check in entry["checks"] if check["status"] == "fail"]
        for entry in record["entries"]
    ]
    assert (
        "assignment.duplicate_client_id" in codes[0]
        and "assignment.duplicate_client_id" in codes[1]
    )
    assert ("assignment.missing_assignment" in codes[2]) is (selection == "manifest")
    assert "source.client_id_format" in codes[3]
    assert not list(saved.parent.rglob("*.pdf"))


def test_corrected_history_creates_a_new_run_and_keeps_the_rejection(tmp_path):
    command, output, _ = prepare_cohort(tmp_path, ("en",))
    source = command[3]
    frame = pd.read_csv(source, dtype=str, keep_default_na=False)
    frame.loc[0, "imms_given"] = "May 1, 2020 - MMR - invalid"
    frame.to_csv(source, index=False)
    assert run_cli(command, tmp_path).returncode == 1
    (rejected,) = output.glob("*/run.json")
    saved_rejection = rejected.read_bytes()
    frame.loc[0, "imms_given"] = "May 1, 2020 - MMR - Invalid"
    frame.to_csv(source, index=False)
    result = run_cli(command, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    (completed,) = [path for path in output.glob("*/run.json") if path != rejected]
    record = json.loads(completed.read_text())
    assert record["input"]["accepted"] is True
    (entry,) = record["entries"]
    (dose,) = entry["facts"]["prepared"]["history"]
    assert dose["validity"] == "invalid"
    assert dose["diseases"] == ["Measles", "Mumps", "Rubella"]
    text = " ".join(
        page.extract_text()
        for page in PdfReader(completed.parent / entry["original"]["path"]).pages
    )
    assert "MMR" in text
    assert rejected.read_bytes() == saved_rejection
