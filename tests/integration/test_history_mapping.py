"""History mapping follows each selected notice's explicit agent exclusions."""

import json
from pathlib import Path

import pandas as pd
import pytest
from pypdf import PdfReader

from immuknow import bundle_pdfs
from immuknow.orchestrator import run_pipeline
from tests.integration.test_native_pipeline import prepare_cohort, run_cli

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("mode", ["cli", "api"])
@pytest.mark.parametrize("selection", ["template", "manifest"])
def test_unknown_history_fails_release_while_explicitly_ignored_agents_are_allowed(
    tmp_path, mode, selection
):
    command, output, config = prepare_cohort(tmp_path, ("en", "en", "en"))
    source = command[3]
    frame = pd.read_csv(source, dtype=str, keep_default_na=False)
    frame["imms_given"] = [
        "2020-05-01 - MMR - Valid;",
        "2020-05-01 - HepA - Invalid;",
        "2020-05-01 - Ig - Valid;",
    ]
    frame.to_csv(source, index=False)
    templates = Path(command[command.index("--templates") + 1])
    template = templates / "overdue_agents_v1.en.typ"
    assignments = Path(command[-1])
    if selection == "template":
        command[-4:] = ["--template", str(template)]
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
            notice_assignments=assignments if selection == "manifest" else None,
            template_dir=templates if selection == "manifest" else None,
        )
    record = json.loads(saved.read_text())
    assert record["status"] == "completed_with_failures"
    assert record["input"]["accepted"] is True
    assert all(
        entry["original"]["status"] == "completed" for entry in record["entries"]
    )
    for index, entry in enumerate(record["entries"]):
        assert entry["source"]["values"]["imms_given"] == frame.loc[index, "imms_given"]
        (check,) = [
            check
            for check in entry["checks"]
            if check["code"] == "content.history_mapping"
        ]
        assert check["status"] == ("fail" if index == 1 else "pass")
        assert check["measurements"]["unmapped_agents"] == (
            ["HepA"] if index == 1 else []
        )
    ignored = record["entries"][2]
    assert ignored["facts"]["prepared"]["history"][0]["mapping_known"] is False
    text = " ".join(
        page.extract_text()
        for page in PdfReader(saved.parent / ignored["original"]["path"]).pages
    )
    assert "Ig" not in text
    failed = record["entries"][1]
    assert failed["routing"]["destination"] == "review"
    evaluations = record["delivery_attempts"][-1]["evaluations"]
    assert "content.history_mapping" in evaluations[failed["row_key"]]["failed_checks"]
    tokens = [
        token
        for evaluation in evaluations.values()
        for token in evaluation["warning_tokens"].values()
    ]
    bundle_pdfs.bundle_run(saved.parent, accept=tokens, reason="Reviewed layout")
    after = json.loads(saved.read_text())
    assert [entry["routing"]["destination"] for entry in after["entries"]] == [
        "delivery",
        "review",
        "delivery",
    ]


def test_unknown_agents_are_retained_without_an_unused_history_check(tmp_path):
    command, output, config = prepare_cohort(tmp_path, ("en",))
    source = Path(command[3])
    frame = pd.read_csv(source, dtype=str, keep_default_na=False)
    frame["imms_given"] = "2020-05-01 - Unknown agent - Valid;"
    frame.to_csv(source, index=False)
    template = (
        Path(command[command.index("--templates") + 1]) / "overdue_agents_v1.en.typ"
    )
    template.write_text(template.read_text().replace("#immunization-history()", ""))
    saved = run_pipeline(source, output, config_dir=config, notice_template=template)
    record = json.loads(saved.read_text())
    assert record["input"]["accepted"] is True
    (entry,) = record["entries"]
    assert entry["original"]["status"] == "completed"
    assert entry["facts"]["prepared"]["history"][0]["mapping_known"] is False
    assert not any(
        check["code"] == "content.history_mapping" for check in entry["checks"]
    )


def test_ignored_agents_do_not_bypass_history_syntax_checks(tmp_path):
    command, output, _ = prepare_cohort(tmp_path, ("en",))
    source = Path(command[3])
    frame = pd.read_csv(source, dtype=str, keep_default_na=False)
    frame["imms_given"] = "2020-02-31 - Ig - Valid;"
    frame.to_csv(source, index=False)
    result = run_cli(command, tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    (saved,) = output.glob("*/run.json")
    record = json.loads(saved.read_text())
    assert record["status"] == "rejected_input"
    assert any(
        check["code"] == "source.history_invalid" and check["status"] == "fail"
        for check in record["entries"][0]["checks"]
    )
    assert not list(saved.parent.rglob("*.pdf"))


@pytest.mark.parametrize("agent", ["Not Specified", "-unspecified"])
def test_unmapped_source_tokens_require_a_mapping_or_explicit_exclusion(
    tmp_path, agent
):
    command, output, _ = prepare_cohort(tmp_path, ("en",))
    source = Path(command[3])
    frame = pd.read_csv(source, dtype=str, keep_default_na=False)
    frame["imms_given"] = f"2020-05-01 - {agent} - Valid;"
    frame.to_csv(source, index=False)
    result = run_cli(command, tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    (failed,) = output.glob("*/run.json")
    (entry,) = json.loads(failed.read_text())["entries"]
    assert entry["facts"]["prepared"]["history"][0]["agent"] == agent
    assert any(
        check["code"] == "content.history_mapping"
        and check["status"] == "fail"
        and check["measurements"]["unmapped_agents"] == [agent]
        for check in entry["checks"]
    )
    template = (
        Path(command[command.index("--templates") + 1]) / "overdue_agents_v1.en.typ"
    )
    template.write_text(
        template.read_text().replace(
            "#immunization-history()",
            f"#immuknow.immunization-history(notice, ignore-agents: ({json.dumps(agent)},))",
        )
    )
    result = run_cli(command, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    (completed,) = [path for path in output.glob("*/run.json") if path != failed]
    (entry,) = json.loads(completed.read_text())["entries"]
    assert entry["facts"]["prepared"]["history"][0]["agent"] == agent
    assert any(
        check["code"] == "content.history_mapping" and check["status"] == "pass"
        for check in entry["checks"]
    )


@pytest.mark.parametrize("diseases", [["Measles", "Mumps", "Rubella"], []])
def test_project_specific_mappings_resolve_unknown_names_in_a_new_run(
    tmp_path, diseases
):
    command, output, config = prepare_cohort(tmp_path, ("en",))
    source = command[3]
    frame = pd.read_csv(source, dtype=str, keep_default_na=False)
    frame["imms_given"] = "2020-05-01 - Project agent - Valid;"
    frame.to_csv(source, index=False)
    assert run_cli(command, tmp_path).returncode == 1
    (failed,) = output.glob("*/run.json")
    original = failed.read_bytes()
    reference_path = config / "vaccine_reference.json"
    reference = json.loads(reference_path.read_text())
    reference["Project agent"] = diseases
    reference_path.write_text(json.dumps(reference))
    result = run_cli(command, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    (completed,) = [path for path in output.glob("*/run.json") if path != failed]
    (entry,) = json.loads(completed.read_text())["entries"]
    (dose,) = entry["facts"]["prepared"]["history"]
    assert dose["mapping_known"] is True
    assert dose["diseases"] == diseases
    assert any(
        check["code"] == "content.history_mapping" and check["status"] == "pass"
        for check in entry["checks"]
    )
    assert failed.read_bytes() == original
