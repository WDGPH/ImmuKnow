"""Three real native journeys prove run identity, failures and saved outputs."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pandas as pd
import pytest
import yaml
from pypdf import PdfReader

from immuknow import preprocess
from immuknow.orchestrator import run_pipeline
from tests.fixtures.sample_input import create_test_input_dataframe

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "filename,content,expected",
    [
        (
            "parameters.yaml",
            "encryption:\n  enabled: true\n  enabled: false\n",
            "Repeated field",
        ),
        (
            "parameters.yaml",
            "bundling:\n  bundle_szie: 20\n",
            "Unknown bundling fields",
        ),
        (
            "notice_versions.yaml",
            "schema_version: 1\nversions:\n  v1: {kind: overdue}\n  v1: {kind: informational}\n",
            "Repeated field",
        ),
        (
            "vaccine_reference.json",
            '{"MMR":["Measles"],"MMR":["Mumps"]}',
            "Repeated field",
        ),
        (
            "disease_normalization.json",
            '{"measles":"Measles","measles":"Mumps"}',
            "Repeated field",
        ),
        (
            "school_reference.json",
            '{"phus":{"Example PHU":{"SCHOOL":"001","SCHOOL":"002"}}}',
            "Repeated field",
        ),
        (
            "assignments.json",
            '[{"client_id":"0000000001","client_id":"0000000002","template":"overdue_agents_v1.en.typ"}]',
            "Repeated field",
        ),
    ],
)
def test_ambiguous_shared_files_stop_before_notices_and_save_source_rows(
    tmp_path, filename, content, expected
):
    source, config, templates, assignments = prepare_inputs(tmp_path)
    target = assignments if filename == "assignments.json" else config / filename
    if filename == "school_reference.json":
        parameters = yaml.safe_load((config / "parameters.yaml").read_text())
        parameters["school_validation"].update(enabled=True, target_phu="Example PHU")
        (config / "parameters.yaml").write_text(yaml.safe_dump(parameters))
    target.write_text(content)
    with pytest.raises(ValueError, match=expected):
        run_pipeline(
            source,
            tmp_path / "runs",
            config_dir=config,
            template_dir=templates,
            notice_assignments=assignments,
        )
    (saved,) = (tmp_path / "runs").glob("*/run.json")
    record = json.loads(saved.read_text())
    assert record["status"] == "failed_setup"
    assert len(record["entries"]) == 2
    assert all(entry["original"]["status"] == "not_run" for entry in record["entries"])
    assert not record["delivery_attempts"]
    assert not list((saved.parent / "originals").glob("*.pdf"))
    assert any(expected in check["message"] for check in record["checks"])


def test_csv_rejection_retains_source_without_starting_notices(tmp_path):
    source = tmp_path / "clients.csv"
    content = b"client_id,client_id\n0000000001,0000000002\n"
    source.write_bytes(content)
    with pytest.raises(ValueError, match="Repeated CSV headers"):
        run_pipeline(
            source,
            tmp_path / "runs",
            notice_template=ROOT / "immuknow/templates/overdue_diseases_v1.en.typ",
        )
    (saved,) = (tmp_path / "runs").glob("*/run.json")
    record = json.loads(saved.read_text())
    assert record["status"] == "failed_setup"
    assert (saved.parent / record["input"]["path"]).read_bytes() == content
    assert record["entries"] == []
    assert record["delivery_attempts"] == []
    assert not list(saved.parent.rglob("*.pdf"))


def test_cli_csv_encoding_is_recorded_and_windows_punctuation_reaches_pdf(tmp_path):
    source, config, templates, _ = prepare_inputs(tmp_path)
    source.write_bytes(source.read_text().replace("Alpha", "D’Angelo").encode("cp1252"))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "immuknow.orchestrator",
            str(source),
            "--input-encoding",
            "cp1252",
            "--config",
            str(config),
            "--template",
            str(templates / "overdue_agents_v1.en.typ"),
            "--output",
            str(tmp_path / "runs"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    (saved,) = (tmp_path / "runs").glob("*/run.json")
    record = json.loads(saved.read_text())
    assert record["input"]["requested_encoding"] == "cp1252"
    assert record["input"]["encoding"] == "cp1252"
    entry = record["entries"][1]
    assert entry["source"]["values"]["last_name"] == "D’Angelo"
    assert entry["client_id"] == "0000000002"
    text = " ".join(
        page.extract_text()
        for page in PdfReader(saved.parent / entry["original"]["path"]).pages
    )
    assert "D’Angelo" in text


def prepare_inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    config_dir = tmp_path / "config"
    templates = tmp_path / "templates"
    shutil.copytree(ROOT / "immuknow/config", config_dir)
    shutil.copytree(ROOT / "immuknow/templates", templates)
    config_path = config_dir / "parameters.yaml"
    config = yaml.safe_load(config_path.read_text())
    config["bundling"] = {"bundle_size": 10}
    config["encryption"]["enabled"] = True
    config["encryption"]["password"] = {"template": "literal-secret-for-test"}
    config_path.write_text(yaml.safe_dump(config))
    frame = create_test_input_dataframe(num_clients=2)
    # Reverse the sorting order and retain literal source text in the HTML.
    frame.loc[0, "last_name"] = 'Zulu <script>alert("x")</script>'
    frame.loc[1, "last_name"] = "Alpha"
    source = tmp_path / "clients.csv"
    frame.to_csv(source, index=False)
    assignments = tmp_path / "assignments.json"
    assignments.write_text(
        json.dumps(
            [
                {
                    "client_id": frame.iloc[0]["client_id"],
                    "template": "overdue_agents_v1.en.typ",
                    "experiment_arm": "A",
                },
                {
                    "client_id": frame.iloc[1]["client_id"],
                    "template": "overdue_agents_v1.fr.typ",
                    "experiment_arm": "B",
                },
            ]
        )
    )
    return source, config_dir, templates, assignments


def test_both_selectors_keep_complete_outputs_and_original_source_order(
    tmp_path: Path,
) -> None:
    source, config, templates, assignments = prepare_inputs(tmp_path)
    outputs = tmp_path / "runs"
    for selector in (
        {"notice_assignments": assignments, "template_dir": templates},
        {"notice_template": templates / "overdue_agents_v1.en.typ"},
    ):
        record_path = run_pipeline(
            source,
            outputs,
            config_dir=config,
            notice_template=selector.get("notice_template"),
            notice_assignments=selector.get("notice_assignments"),
            template_dir=selector.get("template_dir"),
        )
        record = json.loads(record_path.read_text())
        assert record["status"] in {"completed", "completed_with_warnings"}
        assert [entry["row_key"] for entry in record["entries"]] == [
            "row-000001",
            "row-000002",
        ]
        assert record["entries"][0]["source"]["values"]["last_name"].startswith("Zulu")
        assert record["entries"][0]["facts"]["prepared"]["sequence"] == "row-000001"
        run_dir = record_path.parent
        assert record["input"]["sha256"] == sha256(source.read_bytes()).hexdigest()
        assert record["resources"]["files"]
        assert "password" not in record["configuration"]["effective"]["encryption"]
        assert "literal-secret-for-test" not in record_path.read_text()
        assert (
            "literal-secret-for-test"
            not in (run_dir / "resources/config/parameters.yaml").read_text()
        )
        assert record["delivery_attempts"][0]["status"] == "completed"
        assert record["delivery_attempts"][0]["bundles"][0]["row_keys"] == [
            "row-000001",
            "row-000002",
        ]
        for entry in record["entries"]:
            original = run_dir / entry["original"]["path"]
            assert (
                entry["original"]["sha256"] == sha256(original.read_bytes()).hexdigest()
            )
            assert entry["client_id"] in PdfReader(original).pages[0].extract_text()
            assert PdfReader(run_dir / entry["encryption"]["path"]).is_encrypted
            assert entry["bundle"]["end_page"] >= entry["bundle"]["start_page"]
        html = (run_dir / "report.html").read_text()
        assert '<script>alert("x")</script>' not in html
        assert "&lt;script&gt;" in html
        assert not list(run_dir.glob("*manifest.json"))
        assert not list(run_dir.rglob("compilation.json"))
        assert not list(run_dir.rglob("render_jobs.json"))
    assert len(list(outputs.glob("*/run.json"))) == 2


def test_broken_notice_retains_other_original_and_reports_partial_run(
    tmp_path: Path,
) -> None:
    source, config, templates, assignments = prepare_inputs(tmp_path)
    parameters = config / "parameters.yaml"
    settings_data = yaml.safe_load(parameters.read_text())
    settings_data["encryption"]["password"] = {
        "template": "{date_of_birth_iso_compact}"
    }
    parameters.write_text(yaml.safe_dump(settings_data))
    frame = pd.read_csv(source, dtype=str, keep_default_na=False)
    extra = frame.iloc[0].copy()
    extra["client_id"] = "0000000003"
    extra["last_name"] = "Still overdue"
    frame.loc[0, "street_address_line_1"] = ""
    frame.loc[0, "date_of_birth"] = "unusable date"
    frame.loc[0, "province"] = "Québec"
    frame.loc[0, "imms_given"] = "May 01, 2020 - MMR - Valid; Jun 15, 2021 - IPV;"
    without_evidence = extra.copy()
    without_evidence["client_id"] = "0000000004"
    pd.concat(
        [frame, extra.to_frame().T, without_evidence.to_frame().T], ignore_index=True
    ).to_csv(source, index=False)
    manifest = json.loads(assignments.read_text())
    manifest.append(
        {"client_id": "0000000003", "template": "affirmative_schedule_v1.en.typ"}
    )
    manifest.append({"client_id": "0000000004", "template": "custom.en.typ"})
    assignments.write_text(json.dumps(manifest))
    (templates / "custom.en.typ").write_text(
        '#let notice = json(sys.inputs.at("data"))\n'
        "Useful custom notice. Client ID: #notice.client_id\n"
    )
    settings = templates / "settings.typ"
    settings.write_text(
        settings.read_text().replace("show-validity: false", "show-validity: true")
    )
    french = templates / "overdue_agents_v1.fr.typ"
    french.write_text(french.read_text() + '\n#panic("deliberate notice failure")\n')
    record_path = run_pipeline(
        source,
        tmp_path / "runs",
        config_dir=config,
        template_dir=templates,
        notice_assignments=assignments,
    )
    record = json.loads(record_path.read_text())
    assert record["status"] == "completed_with_failures"
    assert [entry["original"]["status"] for entry in record["entries"]] == [
        "completed",
        "failed",
        "completed",
        "completed",
    ]
    assert (record_path.parent / record["entries"][0]["original"]["path"]).is_file()
    assert record["entries"][1]["bundle"] is None
    assert any(
        check["code"] == "rendering.failed" for check in record["entries"][1]["checks"]
    )
    bundled = [
        row_key
        for bundle in record["delivery_attempts"][0]["bundles"]
        for row_key in bundle["row_keys"]
    ]
    assert sorted(bundled) == ["row-000001", "row-000003", "row-000004"]
    evidence_entry = record["entries"][3]
    assert evidence_entry["routing"]["destination"] == "review"
    assert any(
        check["code"] == "render.evidence_failed" and check["status"] == "fail"
        for check in evidence_entry["checks"]
    )
    assert any(
        check["code"] == "output.evidence_matches" and check["status"] == "fail"
        for check in evidence_entry["checks"]
    )
    warning_entry = record["entries"][0]
    assert warning_entry["encryption"]["status"] == "failed"
    assert record["entries"][2]["encryption"]["status"] == "completed"
    assert not (record_path.parent / "encrypted/row-000001.pdf").exists()
    codes = {
        check["code"] for check in warning_entry["checks"] if check["status"] == "warn"
    }
    assert {
        "source.address_incomplete",
        "source.age_unknown",
        "content.history_validity",
    } <= codes
    facts = json.loads(
        (record_path.parent / warning_entry["facts"]["path"]).read_text()
    )
    assert facts["client_data"]["over_16"] is None
    assert facts["client_data"]["province"] == "Québec"
    assert facts["validity_coverage"] == "mixed"
    text = " ".join(
        page.extract_text()
        for page in PdfReader(
            record_path.parent / warning_entry["original"]["path"]
        ).pages
    )
    assert "Québec" in text
    explicit = record["entries"][2]
    assert explicit["assignment"]["template"] == "affirmative_schedule_v1.en.typ"
    assert any(
        check["code"] == "assignment.eligibility_conflict" and check["status"] == "warn"
        for check in explicit["checks"]
    )


@pytest.mark.parametrize("history", ["omitted", "displayed", "no_evidence", "failed"])
def test_bad_history_rejects_input_before_any_template_is_rendered(
    tmp_path: Path, history: str
) -> None:
    source, config, templates, _ = prepare_inputs(tmp_path)
    frame = pd.read_csv(source, dtype=str, keep_default_na=False).iloc[:1]
    fragment = "unusable history fragment"
    frame.loc[0, "imms_given"] += f" {fragment};"
    frame.to_csv(source, index=False)
    template = templates / "suspension_order_v1.en.typ"
    if history == "displayed":
        template.write_text(
            template.read_text() + "\n#pagebreak()\n#immunization-history()\n"
        )
    elif history == "no_evidence":
        template.write_text(
            '#let notice = json(sys.inputs.at("data"))\n'
            "Suspension order. Client ID: #notice.client_id\n"
        )
    elif history == "failed":
        template.write_text(template.read_text() + '\n#panic("failed preview")\n')

    record_path = run_pipeline(
        source, tmp_path / "runs", config_dir=config, notice_template=template
    )
    record = json.loads(record_path.read_text())
    assert record["status"] == "rejected_input"
    (entry,) = record["entries"]
    (check,) = [
        check for check in entry["checks"] if check["code"] == "source.history_invalid"
    ]
    assert check["status"] == "fail"
    assert fragment in check["measurements"]["fragment"]
    assert entry["original"]["status"] == "not_run"
    assert not record["delivery_attempts"]
    assert not list(record_path.parent.rglob("*.pdf"))


@pytest.mark.parametrize(
    "location",
    [
        "external_absolute",
        "external_relative",
        "internal_absolute",
        "internal_relative",
    ],
)
def test_school_lookup_uses_saved_reference_after_source_changes(
    tmp_path, monkeypatch, location
):
    source, config, templates, _ = prepare_inputs(tmp_path)
    frame = pd.read_csv(source, dtype=str, keep_default_na=False)
    frame["school_name"] = "Example School - 001"
    frame.to_csv(source, index=False)
    reference = (
        tmp_path if location.startswith("external") else config
    ) / "schools.json"
    content = json.dumps({"phus": {"Example PHU": {"EXAMPLE SCHOOL": "001"}}}).encode()
    reference.write_bytes(content)
    configured_path = (
        str(reference)
        if location.endswith("absolute")
        else ("../schools.json" if location.startswith("external") else "schools.json")
    )
    parameters = config / "parameters.yaml"
    settings = yaml.safe_load(parameters.read_text())
    settings["school_validation"] = {
        "enabled": True,
        "reference_file": configured_path,
        "target_phu": "Example PHU",
    }
    parameters.write_text(yaml.safe_dump(settings))
    prepare = preprocess.prepare_clients

    def change_source_before_lookup(*args, **kwargs):
        reference.write_text('{"phus":{"Example PHU":{}}}')
        return prepare(*args, **kwargs)

    monkeypatch.setattr(preprocess, "prepare_clients", change_source_before_lookup)
    saved = run_pipeline(
        source,
        tmp_path / "runs",
        config_dir=config,
        notice_template=templates / "overdue_agents_v1.en.typ",
    )
    record = json.loads(saved.read_text())
    frozen_config = saved.parent / "resources/config"
    effective = record["configuration"]["effective"]["school_validation"][
        "reference_file"
    ]
    retained = (frozen_config / effective).resolve()
    assert retained.is_relative_to(saved.parent)
    assert retained.read_bytes() == content
    assert reference.read_bytes() != content
    assert record["configuration"]["school_reference_source"] == str(reference)
    assert (
        yaml.safe_load((frozen_config / "parameters.yaml").read_text())[
            "school_validation"
        ]["reference_file"]
        == effective
    )
    assert {
        "path": retained.relative_to(saved.parent).as_posix(),
        "sha256": sha256(content).hexdigest(),
    } in record["resources"]["files"]
    for entry in record["entries"]:
        check = next(c for c in entry["checks"] if c["code"] == "data.school_match")
        assert check["status"] == "pass"
        assert check["measurements"]["reference_sha256"] == sha256(content).hexdigest()
        assert entry["original"]["status"] == "completed"


def test_school_conflicts_reject_the_cohort_with_reference_details(tmp_path):
    source, config, templates, _ = prepare_inputs(tmp_path)
    frame = pd.concat(
        [create_test_input_dataframe(num_clients=2)] * 3, ignore_index=True
    )
    frame["client_id"] = [f"{index:010d}" for index in range(1, 7)]
    names = [
        "Tunnel Academy - 001",
        "Tunnel Academy",
        "Tunnel Academy - 999",
        "Different School - 001",
        "Foreign School - 003",
        "Unknown School",
    ]
    frame["school_name"] = names
    frame["school_id"] = "0007"
    frame.to_csv(source, index=False)
    reference = config / "school_reference.json"
    reference.write_text(
        json.dumps(
            {
                "phus": {
                    "Example PHU": {"TUNNEL ACADEMY": "001"},
                    "Other PHU": {"FOREIGN SCHOOL": "003"},
                }
            }
        )
    )
    parameters = config / "parameters.yaml"
    settings = yaml.safe_load(parameters.read_text())
    settings["school_validation"] = {
        "enabled": True,
        "target_phu": "Example PHU",
        "reference_file": reference.name,
        "column_prefix": "lookup_",
    }
    parameters.write_text(yaml.safe_dump(settings))
    saved = run_pipeline(
        source,
        tmp_path / "runs",
        config_dir=config,
        notice_template=templates / "overdue_agents_v1.en.typ",
    )
    record = json.loads(saved.read_text())
    assert record["status"] == "rejected_input"
    assert len(record["entries"]) == 6
    expected_hash = sha256(
        (saved.parent / "resources/config/school_reference.json").read_bytes()
    ).hexdigest()
    for entry, name, status, reason in zip(
        record["entries"],
        names,
        ["pass", "warn", "fail", "fail", "fail", "fail"],
        ["exact", "name_only", "id_mismatch", "id_only", "not_found", "not_found"],
    ):
        checks = [c for c in entry["checks"] if c["code"] == "data.school_match"]
        assert len(checks) == 1
        check = checks[0]
        assert check["status"] == status
        assert check["measurements"]["reason"] == reason
        assert check["measurements"]["reference_sha256"] == expected_hash
        assert check["measurements"]["target_phu"] == "Example PHU"
        assert check["measurements"]["source_school"] == name
        assert entry["facts"]["prepared"]["school"] == {"name": name, "id": "0007"}
        assert entry["original"]["status"] == "not_run"
    assert not record["delivery_attempts"]
    assert not list(saved.parent.rglob("*.pdf"))


def test_setup_failure_preserves_all_source_rows_in_report(tmp_path: Path) -> None:
    source, config, templates, assignments = prepare_inputs(tmp_path)
    assignments.write_text("invalid JSON")
    output = tmp_path / "runs"
    with pytest.raises(ValueError):
        run_pipeline(
            source,
            output,
            config_dir=config,
            template_dir=templates,
            notice_assignments=assignments,
        )
    record_path = next(output.glob("*/run.json"))
    record = json.loads(record_path.read_text())
    assert record["status"] == "failed_setup"
    assert len(record["entries"]) == 2
    assert all(entry["original"]["status"] == "not_run" for entry in record["entries"])
    assert not record["delivery_attempts"]
    assert (record_path.parent / "report.html").is_file()


@pytest.mark.parametrize(
    "diseases,agents,status,missing,extra,unmapped",
    [
        ("Measles; Mumps; Rubella", "MMR", "pass", [], [], []),
        ("Measles", "MMR", "warn", [], ["Mumps", "Rubella"], []),
        ("Measles; Polio", "IPV", "fail", ["Measles"], [], []),
        ("Polio", "MMR", "fail", ["Polio"], ["Measles", "Mumps", "Rubella"], []),
        ("Measles", "Unlisted agent", "fail", ["Measles"], [], ["Unlisted agent"]),
        (
            "Measles; Mumps; Rubella",
            "MMR; Unlisted agent",
            "warn",
            [],
            [],
            ["Unlisted agent"],
        ),
        ("Poliomyelitis - 2", "IPV", "pass", [], [], []),
        ("", "", "not_applicable", [], [], []),
        ("", "MMR", "warn", [], ["Measles", "Mumps", "Rubella"], []),
    ],
)
def test_forecast_agents_must_cover_overdue_diseases_before_notices(
    tmp_path, diseases, agents, status, missing, extra, unmapped
):
    source, config, templates, assignments = prepare_inputs(tmp_path)
    frame = pd.read_csv(source, dtype=str, keep_default_na=False)
    frame.loc[0, "overdue_disease"] = diseases
    frame.loc[0, "overdue_agent"] = agents
    frame.to_csv(source, index=False)
    if not diseases and not agents:
        manifest = json.loads(assignments.read_text())
        manifest[0]["template"] = "affirmative_schedule_v1.en.typ"
        assignments.write_text(json.dumps(manifest))
    saved = run_pipeline(
        source,
        tmp_path / "runs",
        config_dir=config,
        template_dir=templates,
        notice_assignments=assignments,
    )
    record = json.loads(saved.read_text())
    assert len(record["entries"]) == 2
    first, second = record["entries"]
    check = next(c for c in first["checks"] if c["code"] == "data.forecast_coverage")
    assert check["status"] == status
    assert check["measurements"] == {
        "missing_diseases": missing,
        "extra_diseases": extra,
        "unmapped_agents": unmapped,
    }
    assert first["source"]["values"]["overdue_disease"] == diseases
    assert first["source"]["values"]["overdue_agent"] == agents
    assert (
        next(c for c in second["checks"] if c["code"] == "data.forecast_coverage")[
            "status"
        ]
        == "pass"
    )
    assert record["input"]["accepted"] == (status != "fail")
    if status == "fail":
        assert all(
            entry["original"]["status"] == "not_run" for entry in record["entries"]
        )
        assert not record["delivery_attempts"]
        assert not list((saved.parent / "originals").glob("*.pdf"))
        assert not list((saved.parent / "encrypted").glob("*.pdf"))
    else:
        assert all(
            entry["original"]["status"] == "completed" for entry in record["entries"]
        )
        assert first["routing"]["destination"] == "review"
        warnings = first["routing"]["unresolved_warnings"]
        assert any(code.startswith("content.multiple_links:") for code in warnings)
        assert any(code.startswith("data.forecast_coverage:") for code in warnings) == (
            status == "warn"
        )


def test_forecast_coverage_uses_the_selected_lookup_string_values(tmp_path):
    source, config, templates, assignments = prepare_inputs(tmp_path)
    frame = pd.read_csv(source, dtype=str, keep_default_na=False)
    frame.loc[0, "overdue_disease"] = "Measles"
    frame.to_csv(source, index=False)
    reference = config / "vaccine_reference.json"
    lookup = json.loads(reference.read_text())
    lookup["MMR"] = "Measles"
    reference.write_text(json.dumps(lookup))
    saved = run_pipeline(
        source,
        tmp_path / "runs",
        config_dir=config,
        template_dir=templates,
        notice_assignments=assignments,
    )
    first = json.loads(saved.read_text())["entries"][0]
    check = next(c for c in first["checks"] if c["code"] == "data.forecast_coverage")
    assert check["status"] == "pass"
    assert check["measurements"] == {
        "missing_diseases": [],
        "extra_diseases": [],
        "unmapped_agents": [],
    }
    assert first["original"]["status"] == "completed"
