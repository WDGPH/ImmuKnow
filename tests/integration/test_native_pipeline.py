"""Exercise native rendering through the CLI and explicit expected-output stages.

These tests use maintained templates and a real pinned Typst executable. All
inputs are synthetic; outputs live outside the checkout in caller-owned paths.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml
from pypdf import PdfReader

from immuknow import (
    bundle_pdfs,
    compile_notices,
    encrypt_notice,
    orchestrator,
    validate_pdfs,
)
from immuknow.config_loader import load_config
from immuknow.data_models import ClientRecord, RenderJob
from tests.fixtures.sample_input import create_test_input_dataframe

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


def read_render_jobs(artifact_dir: Path) -> list[RenderJob]:
    """Inspect persisted compilation evidence produced by a complete test run."""
    manifest = json.loads((artifact_dir / "render_jobs.json").read_text())
    evidence = json.loads((artifact_dir / "compilation.json").read_text())
    assert evidence["outputs"] == [raw["pdf"] for raw in manifest["jobs"]]
    assert len(manifest["jobs"]) == manifest["total_clients"]
    jobs = []
    for raw in manifest["jobs"]:
        for field in ("workspace", "template", "data", "pdf"):
            raw[field] = Path(raw[field])
        jobs.append(RenderJob(**raw))
    assert all(job.pdf.is_file() for job in jobs)
    return jobs


def prepare_cohort(
    tmp_path: Path,
    languages: tuple[str, ...] = ("en", "fr"),
    group_by: str | None = None,
    encrypted: bool = False,
    qr: bool = False,
    include_dose: bool = False,
    show_validity_markers: bool = False,
) -> tuple[list[str], Path, Path]:
    """Prepare synthetic CSV, manifest, and external config for a real CLI run."""
    config_dir = tmp_path / "Configuration été"
    shutil.copytree(ROOT / "immuknow" / "config", config_dir)
    config_path = config_dir / "parameters.yaml"
    config = yaml.safe_load(config_path.read_text())
    config["bundling"] = {"bundle_size": 10, "group_by": group_by}
    config["encryption"]["enabled"] = encrypted
    config["qr"]["enabled"] = qr
    config["preprocess"]["include_dose"] = include_dose
    config["preprocess"]["show_validity_markers"] = show_validity_markers
    config_path.write_text(yaml.safe_dump(config))

    frame = create_test_input_dataframe(num_clients=len(languages))
    frame["overdue_disease"] = "Measles - 2"
    input_path = tmp_path / "Élèves synthétiques.csv"
    frame.to_csv(input_path, index=False)
    manifest_path = tmp_path / "Assignments.json"
    manifest_path.write_text(
        json.dumps(
            [
                {
                    "client_id": str(client_id),
                    "template": f"overdue_agents_v1.{language}.typ",
                }
                for client_id, language in zip(frame["client_id"], languages)
            ]
        )
    )
    output_dir = tmp_path / "Notices été"
    command = [
        sys.executable,
        "-m",
        "immuknow.orchestrator",
        str(input_path),
        "--output",
        str(output_dir),
        "--config",
        str(config_dir),
        "--notice-assignments",
        str(manifest_path),
    ]
    return command, output_dir, config_dir


def run_cli(command: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Run from an unrelated directory, without inheriting a checkout path."""
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=False)


@pytest.mark.parametrize(
    "field,value",
    [("first_name", "   "), ("date_of_birth", "2015-02-30"), ("client_id", "123")],
)
def test_invalid_csv_stops_before_notices(
    tmp_path: Path, field: str, value: str
) -> None:
    command, output, _ = prepare_cohort(tmp_path, ("en",))
    source = Path(command[3])
    frame = pd.read_csv(source, dtype=str, keep_default_na=False)
    frame.loc[0, field] = value
    frame.to_csv(source, index=False)

    result = run_cli(command, tmp_path)

    assert result.returncode == 1
    assert "Input file does not conform to expected schema" in result.stderr
    assert field in result.stderr
    assert not list(output.rglob("*.pdf"))
    assert not list((output / "metadata").glob("completion_*.json"))


def test_cleaned_csv_values_reach_pdf_and_incomplete_address_report(
    tmp_path: Path,
) -> None:
    command, output, _ = prepare_cohort(tmp_path)
    source = Path(command[3])
    frame = pd.read_csv(source, dtype=str, keep_default_na=False)
    first_id, excluded_id = frame["client_id"]
    frame.loc[0, "client_id"] = f"  {first_id}  "
    frame.loc[0, "first_name"] = "  nan  "
    frame.loc[0, "last_name"] = " NA "
    frame.loc[0, "date_of_birth"] = "2015-1-2"
    frame.loc[1, "postal_code"] = "   "
    frame.drop(columns=["street_address_line_2"]).to_csv(source, index=False)
    index = command.index("--notice-assignments")
    command[index:] = [
        "--template",
        str(ROOT / "immuknow" / "templates" / "overdue_agents_v1.en.typ"),
    ]

    result = run_cli(command, tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    jobs = read_render_jobs(output / "artifacts")
    assert [job.client_id for job in jobs] == [first_id]
    notice = json.loads(jobs[0].data.read_text())
    assert notice["client_data"]["name"] == "nan NA"
    assert notice["client_data"]["date_of_birth_iso"] == "2015-01-02"
    assert "nan NA" in PdfReader(jobs[0].pdf).pages[0].extract_text()
    excluded = pd.read_csv(output / "incomplete_addresses.csv", dtype=str)
    assert excluded["client_id"].tolist() == [excluded_id]
    assert next((output / "metadata").glob("completion_*.json")).is_file()


def test_cli_requires_template_in_every_assignment(tmp_path: Path) -> None:
    """An old identity pair cannot silently select a maintained entry point."""
    command, output_dir, _ = prepare_cohort(tmp_path, languages=("en",))
    manifest_path = Path(command[command.index("--notice-assignments") + 1])
    assignments = json.loads(manifest_path.read_text())
    assignments[0].pop("template")
    assignments[0].update(version_id="overdue_agents_v1", language="en")
    manifest_path.write_text(json.dumps(assignments), encoding="utf-8")

    result = run_cli(command, tmp_path)
    assert result.returncode != 0
    assert "required field 'template'" in result.stdout + result.stderr
    assert not list(output_dir.rglob("*.pdf"))


def test_unsupported_template_language_preserves_existing_output(
    tmp_path: Path,
) -> None:
    """A bad manifest suffix fails before an earlier delivery is purged."""
    command, output_dir, _ = prepare_cohort(tmp_path, languages=("en",))
    manifest_path = Path(command[command.index("--notice-assignments") + 1])
    assignments = json.loads(manifest_path.read_text())
    assignments[0]["template"] = "overdue_agents_v1.es.typ"
    manifest_path.write_text(json.dumps(assignments), encoding="utf-8")
    output_dir.mkdir()
    sentinel = output_dir / "prior-delivery.txt"
    sentinel.write_text("preserve", encoding="utf-8")

    result = run_cli(command, tmp_path)
    assert result.returncode != 0
    assert "language" in (result.stdout + result.stderr).lower()
    assert sentinel.read_text(encoding="utf-8") == "preserve"
    assert not list(output_dir.rglob("*.pdf"))


@pytest.mark.parametrize(
    "group_by,options,input_form",
    [
        (None, False, "filename"),
        ("school", True, "relative"),
        ("board", False, "absolute"),
    ],
)
def test_mixed_cohort_processed_exactly_once(
    tmp_path: Path, group_by: str | None, options: bool, input_form: str
) -> None:
    """Both languages pass validation and every configured notice option."""
    command, output_dir, _ = prepare_cohort(
        tmp_path,
        group_by=group_by,
        encrypted=options,
        qr=options,
        include_dose=options,
        show_validity_markers=options,
    )
    source = Path(command[3])
    if input_form == "filename":
        command[3] = source.name
    elif input_form == "relative":
        nested = tmp_path / "input"
        nested.mkdir()
        source = source.rename(nested / source.name)
        command[3] = str(source.relative_to(tmp_path))
    result = run_cli(command, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    completion = json.loads(
        next((output_dir / "metadata").glob("completion_*.json")).read_text()
    )
    assert completion["input"] == str(source)
    jobs = read_render_jobs(output_dir / "artifacts")
    assert len(jobs) == 2
    assert {job.language for job in jobs} == {"en", "fr"}
    validation = json.loads(
        next((output_dir / "metadata").glob("validation_*.json")).read_text()
    )
    assert validation["total_pdfs"] == 2
    manifests = [
        json.loads(path.read_text())
        for path in (output_dir / "metadata").glob("*_manifest.json")
    ]
    included = [
        client["client_id"] for manifest in manifests for client in manifest["clients"]
    ]
    assert sorted(included) == sorted(job.client_id for job in jobs)
    if group_by is None:
        assert len(manifests) == 1
        assert manifests[0]["languages"] == ["en", "fr"]
    encrypted_files = list((output_dir / "pdf_individual").glob("*_encrypted.pdf"))
    assert len(encrypted_files) == (2 if options else 0)
    for job in jobs:
        notice = json.loads(job.data.read_text())
        assert notice["overdue_diseases"] == [{"disease": "Measles", "dose": 2}]
        assert notice["include_dose"] is options
        assert notice["show_validity_markers"] is options
        assert ("qr_img" in notice["client_data"]) == options
        assert (
            job.template.read_bytes()
            == (
                ROOT
                / "immuknow"
                / "templates"
                / f"overdue_agents_v1.{job.language}.typ"
            ).read_bytes()
        )
        if options:
            encrypted = PdfReader(job.pdf.with_name(job.pdf.stem + "_encrypted.pdf"))
            assert encrypted.is_encrypted
            assert encrypted.decrypt(
                notice["client_data"]["date_of_birth_iso"].replace("-", "")
            )
    assert not list((output_dir / "artifacts").glob("typst/*.typ"))


@pytest.mark.parametrize(
    "assigned_language,month",
    [("fr", "janvier"), ("en", "January")],
)
def test_assigned_language_controls_every_display_date(
    tmp_path: Path, assigned_language: str, month: str
) -> None:
    """Assigned entry points control both birth and cutoff date presentation."""
    command, output_dir, _ = prepare_cohort(tmp_path, (assigned_language,))
    result = run_cli(command, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    job = read_render_jobs(output_dir / "artifacts")[0]
    notice = json.loads(job.data.read_text())
    text = "\n".join(page.extract_text() for page in PdfReader(job.pdf).pages)
    assert month in text
    assert notice["client_data"]["date_of_birth_iso"] == "2015-01-02"
    cutoff_month = "août" if assigned_language == "fr" else "August"
    assert cutoff_month in text
    assert len(list((output_dir / "pdf_combined").glob("*.pdf"))) == 1


def test_single_template_assigns_every_client_and_qr_language(tmp_path: Path) -> None:
    """One French entry point supplies identity and language without a manifest."""
    command, output, config = prepare_cohort(tmp_path, qr=True)
    template = ROOT / "immuknow" / "templates" / "overdue_agents_v1.fr.typ"
    completion = orchestrator.run_pipeline(
        Path(command[3]), output, config_dir=config, notice_template=template
    )
    assert completion is not None
    record = json.loads(completion.read_text())
    assert record["notice_template"] == str(template)
    assert record["notice_assignments"] is None
    cohort = json.loads(Path(record["cohort"]).read_text())
    assert len(cohort["clients"]) == 2
    for client in cohort["clients"]:
        assert client["language"] == "fr"
        assert client["version_id"] == "overdue_agents_v1"
        assert client["metadata"]["assignment_source"] == "template"
        assert "lang=fr" in client["qr"]["payload"]
    jobs = read_render_jobs(output / "artifacts")
    assert len(jobs) == 2
    assert all(PdfReader(job.pdf).root_object["/Lang"] == "fr-CA" for job in jobs)


@pytest.mark.parametrize(
    "failure", ["ineligible", "language_mismatch", "linked_language_mismatch"]
)
def test_single_template_cannot_bypass_eligibility_or_native_language(
    tmp_path: Path, failure: str
) -> None:
    command, output, config = prepare_cohort(tmp_path)
    custom = tmp_path / "custom"
    shutil.copytree(ROOT / "immuknow" / "templates", custom)
    if failure == "ineligible":
        template = custom / "affirmative_schedule_v1.en.typ"
        diagnostic = "Notice assignment preflight failed"
    else:
        template = custom / "overdue_agents_v1.fr.typ"
        english = custom / "overdue_agents_v1.en.typ"
        if failure == "linked_language_mismatch":
            template.unlink()
            template.symlink_to(english)
        else:
            template.write_bytes(english.read_bytes())
        diagnostic = "Notice language does not match this template"
    result = run_cli(
        [
            sys.executable,
            "-m",
            "immuknow.orchestrator",
            command[3],
            "--output",
            str(output),
            "--config",
            str(config),
            "--template",
            str(template),
        ],
        tmp_path,
    )
    assert result.returncode == 1
    assert diagnostic in result.stdout + result.stderr
    assert not list((output / "pdf_combined").glob("*.pdf"))
    assert not list((output / "metadata").glob("completion_*.json"))


def test_failed_compilation_invalidates_old_outputs(tmp_path: Path) -> None:
    """A real assertion failure removes an old PDF and prevents downstream reuse."""
    command, output_dir, config_dir = prepare_cohort(tmp_path)
    assert run_cli(command, tmp_path).returncode == 0
    artifact_dir = output_dir / "artifacts"
    jobs = read_render_jobs(artifact_dir)
    job = next(job for job in jobs if job.language == "fr")
    notice = json.loads(job.data.read_text())
    notice["version_id"] = "affirmative_schedule_v1"
    job.data.write_text(json.dumps(notice))
    with pytest.raises(subprocess.CalledProcessError):
        compile_notices.compile_notices(
            jobs, artifact_dir, load_config(config_dir / "parameters.yaml")
        )
    assert not job.pdf.exists()
    assert not list(job.pdf.parent.glob("*.partial.pdf"))
    with pytest.raises(FileNotFoundError):
        read_render_jobs(artifact_dir)


@pytest.mark.parametrize("failure", ["wrong_client", "missing_entry", "compile_error"])
def test_french_notice_failure_prevents_successful_delivery(
    tmp_path: Path, failure: str
) -> None:
    """Every selected language must compile and validate, including a failed rerun."""
    command, output_dir, _ = prepare_cohort(tmp_path)
    custom = tmp_path / "PHU modèles"
    shutil.copytree(ROOT / "immuknow" / "templates", custom)
    selected_command = command + ["--templates", str(custom)]
    french = custom / "overdue_agents_v1.fr.typ"
    if failure == "wrong_client":
        french.write_text(
            french.read_text().replace("notice.client_id", '"9999999999"')
        )
        diagnostic = "PDF validation failed"
    elif failure == "missing_entry":
        french.unlink()
        diagnostic = "Notice template not found"
    else:
        initial = run_cli(selected_command, tmp_path)
        assert initial.returncode == 0, initial.stdout + initial.stderr
        assert list((output_dir / "pdf_combined").glob("*.pdf"))
        french.write_text(
            french.read_text() + '\n#panic("deliberate recompilation failure")\n'
        )
        diagnostic = "deliberate recompilation failure"
    result = run_cli(selected_command, tmp_path)
    assert result.returncode == 1
    assert diagnostic in result.stderr
    assert "Pipeline completed successfully" not in result.stdout
    assert not list((output_dir / "pdf_combined").glob("*.pdf"))
    assert not list((output_dir / "metadata").glob("completion_*.json"))


def test_expected_outputs_exclude_stale_files_and_require_every_pdf(
    tmp_path: Path,
) -> None:
    """Validation and bundling follow the job map, even beside stale and encrypted PDFs."""
    command, output_dir, config_dir = prepare_cohort(tmp_path)
    assert run_cli(command, tmp_path).returncode == 0
    artifact_dir = output_dir / "artifacts"
    manifest = json.loads((artifact_dir / "render_jobs.json").read_text())
    jobs = read_render_jobs(artifact_dir)
    (output_dir / "pdf_individual" / "en_notice_stale.pdf").write_text("not a PDF")
    (output_dir / "pdf_individual" / "fr_notice_old_encrypted.pdf").write_text(
        "not a PDF"
    )
    clients = [
        ClientRecord(**raw)
        for raw in json.loads(
            next(artifact_dir.glob("preprocessed_clients_*.json")).read_text()
        )["clients"]
    ]
    config = load_config(config_dir / "parameters.yaml")
    validate_pdfs.validate_notices(
        [job.pdf for job in jobs],
        enabled_rules=config["pdf_validation"]["rules"],
        client_id_map={job.pdf.name: job.client_id for job in jobs},
    )
    bundles = bundle_pdfs.bundle_notices(
        clients, jobs, output_dir, manifest["run_id"], config
    )
    assert sum(len(bundle.bundle_plan.clients) for bundle in bundles) == 2
    jobs[0].pdf.unlink()
    with pytest.raises(FileNotFoundError, match="Expected notice PDF is missing"):
        validate_pdfs.validate_notices([job.pdf for job in jobs])
    with pytest.raises(FileNotFoundError, match="Expected notice PDF is missing"):
        bundle_pdfs.bundle_notices(
            clients, jobs, output_dir, manifest["run_id"], config
        )


def test_encryption_rejects_job_client_mismatch(tmp_path: Path) -> None:
    """A compiled job cannot be encrypted under another client's password."""
    command, output_dir, config_dir = prepare_cohort(tmp_path, ("en",))
    result = run_cli(command, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    artifact_dir = output_dir / "artifacts"
    artifact_path = next(artifact_dir.glob("preprocessed_clients_*.json"))
    artifact = json.loads(artifact_path.read_text())
    artifact["clients"][0]["client_id"] = "different_client"
    artifact_path.write_text(json.dumps(artifact))

    with pytest.raises(
        ValueError, match="Render jobs do not match the prepared client list"
    ):
        encrypt_notice.encrypt_expected_notices(
            [ClientRecord(**raw) for raw in artifact["clients"]],
            read_render_jobs(artifact_dir),
            load_config(config_dir / "parameters.yaml"),
        )


def test_sequential_callable_runs_keep_resources_and_assignments_isolated(
    tmp_path: Path,
) -> None:
    """A mixed affirmative/overdue run cannot leak resources into an all-French run."""
    command, first_output, first_config = prepare_cohort(tmp_path / "first")
    input_path = Path(command[3])
    frame = pd.read_csv(input_path, dtype=str)
    frame.loc[0, "overdue_disease"] = ""
    frame.loc[0, "overdue_vaccine"] = ""
    frame.to_csv(input_path, index=False)
    assignment_path = Path(command[command.index("--notice-assignments") + 1])
    assignments = json.loads(assignment_path.read_text())
    assignments[0]["template"] = "affirmative_schedule_v1.en.typ"
    assignment_path.write_text(json.dumps(assignments))
    first_completion = orchestrator.run_pipeline(
        input_path,
        first_output,
        config_dir=first_config,
        notice_assignments=assignment_path,
    )
    assert first_completion is not None
    first_jobs = read_render_jobs(first_output / "artifacts")
    assert {(job.version_id, job.language) for job in first_jobs} == {
        ("affirmative_schedule_v1", "en"),
        ("overdue_agents_v1", "fr"),
    }

    command, second_output, second_config = prepare_cohort(tmp_path / "second", ("fr",))
    second_assignments = Path(command[command.index("--notice-assignments") + 1])
    assignments = json.loads(second_assignments.read_text())
    assignments[0]["template"] = "overdue_diseases_v1.fr.typ"
    second_assignments.write_text(json.dumps(assignments))
    translation = second_config / "translations" / "fr_diseases_overdue.json"
    labels = json.loads(translation.read_text())
    labels["Measles"] = "LIBELLÉ LOCAL SÉLECTIONNÉ"
    translation.write_text(json.dumps(labels, ensure_ascii=False))
    custom = tmp_path / "Modèles privés"
    shutil.copytree(ROOT / "immuknow" / "templates", custom)
    entry = custom / "overdue_diseases_v1.fr.typ"
    entry.write_text(entry.read_text() + "\n#text[SECOND TEMPLATE SET]\n")
    second_completion = orchestrator.run_pipeline(
        Path(command[3]),
        second_output,
        config_dir=second_config,
        template_dir=custom,
        notice_assignments=second_assignments,
    )
    assert second_completion is not None
    second_jobs = read_render_jobs(second_output / "artifacts")
    assert len(second_jobs) == 1 and second_jobs[0].language == "fr"
    assert second_jobs[0].version_id == "overdue_diseases_v1"
    text = "\n".join(
        page.extract_text() for page in PdfReader(second_jobs[0].pdf).pages
    )
    assert "LIBELLÉ LOCAL SÉLECTIONNÉ" in text
    assert "SECOND TEMPLATE SET" in text
    for output, expected in ((first_output, first_jobs), (second_output, second_jobs)):
        manifests = [
            json.loads(path.read_text())
            for path in (output / "metadata").glob("*_manifest.json")
        ]
        bundled = [
            client["client_id"]
            for manifest in manifests
            for client in manifest["clients"]
        ]
        assert sorted(bundled) == sorted(job.client_id for job in expected)
        assert len(
            json.loads(
                next((output / "metadata").glob("completion_*.json")).read_text()
            )["notices"]
        ) == len(expected)


@pytest.mark.parametrize("failure", ["unknown_version", "version_conflict"])
def test_preflight_preserves_actionable_sensitive_findings(
    tmp_path: Path, failure: str
) -> None:
    """A failed assignment identifies its client and reason without publishing output."""
    command, output, config_dir = prepare_cohort(tmp_path, ("fr",))
    manifest = Path(command[command.index("--notice-assignments") + 1])
    assignments = json.loads(manifest.read_text())
    if failure == "unknown_version":
        assignments[0]["template"] = "not_in_the_catalog.fr.typ"
        custom = tmp_path / "uncatalogued templates"
        shutil.copytree(ROOT / "immuknow" / "templates", custom)
        (custom / "not_in_the_catalog.fr.typ").write_bytes(
            (custom / "overdue_agents_v1.fr.typ").read_bytes()
        )
    else:
        frame = pd.read_csv(Path(command[3]), dtype=str)
        frame["version_id"] = "overdue_diseases_v1"
        frame.to_csv(Path(command[3]), index=False)
    manifest.write_text(json.dumps(assignments))
    with pytest.raises(ValueError, match="Sensitive assignment diagnostics"):
        orchestrator.run_pipeline(
            Path(command[3]),
            output,
            config_dir=config_dir,
            notice_assignments=manifest,
            template_dir=custom
            if failure == "unknown_version"
            else ROOT / "immuknow" / "templates",
        )
    diagnostic = next((output / "metadata").glob("assignment_findings_*.json"))
    finding = json.loads(diagnostic.read_text())[0]
    assert finding["client_id"] == assignments[0]["client_id"]
    assert finding["version_id"] == assignments[0]["template"].split(".")[0]
    assert finding["version_id"] in finding["reason"]
    assert finding["kind"] == failure
    assert diagnostic.stat().st_mode & 0o777 == 0o600
    assert not list(output.rglob("*.pdf"))
    assert not list((output / "metadata").glob("completion_*.json"))
