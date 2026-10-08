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

import pytest
import yaml
from pypdf import PdfReader

from pipeline import bundle_pdfs, compile_notices, generate_notices, orchestrator
from tests.fixtures.sample_input import create_test_input_dataframe

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


def prepare_cohort(
    tmp_path: Path,
    languages: tuple[str, ...] = ("en", "fr"),
    default_language: str = "en",
    group_by: str | None = None,
    encrypted: bool = False,
    qr: bool = False,
) -> tuple[list[str], Path, Path]:
    """Prepare synthetic Excel, manifest, and external config for a real CLI run."""
    config_dir = tmp_path / "Configuration été"
    shutil.copytree(ROOT / "config", config_dir)
    config_path = config_dir / "parameters.yaml"
    config = yaml.safe_load(config_path.read_text())
    config["bundling"] = {"bundle_size": 10, "group_by": group_by}
    config["encryption"]["enabled"] = encrypted
    config["qr"]["enabled"] = qr
    config["preprocess"]["include_dose"] = True
    config_path.write_text(yaml.safe_dump(config))
    catalog_path = config_dir / "notice_versions.yaml"
    catalog = yaml.safe_load(catalog_path.read_text())
    catalog["default_language"] = default_language
    catalog_path.write_text(yaml.safe_dump(catalog))

    frame = create_test_input_dataframe(num_clients=len(languages))
    frame["overdue_disease"] = "Measles - 2"
    input_path = tmp_path / "Élèves synthétiques.xlsx"
    frame.to_excel(input_path, index=False)
    manifest_path = tmp_path / "Assignments.json"
    manifest_path.write_text(
        json.dumps(
            [
                {
                    "client_id": str(client_id),
                    "notice_version": "overdue_standard_v1",
                    "language": language,
                }
                for client_id, language in zip(frame["client_id"], languages)
            ]
        )
    )
    output_dir = tmp_path / "Notices été"
    command = [
        sys.executable,
        "-m",
        "pipeline.orchestrator",
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
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True)


@pytest.mark.parametrize("group_by", [None, "school", "board"])
@pytest.mark.parametrize("options", [False, True])
def test_mixed_cohort_processed_exactly_once(
    tmp_path: Path, group_by: str | None, options: bool
) -> None:
    """Both languages pass validation, encryption options, and every bundle strategy."""
    command, output_dir, _ = prepare_cohort(
        tmp_path, group_by=group_by, encrypted=options, qr=options
    )
    result = run_cli(command, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    jobs = generate_notices.read_render_jobs(
        output_dir / "artifacts", require_compiled=True
    )
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
        assert ("qr_img" in notice["client_data"]) == options
        assert (
            job.template.read_bytes()
            == (
                ROOT / "templates" / f"overdue_standard_v1.{job.language}.typ"
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
    "default_language,assigned_language,month",
    [("en", "fr", "janvier"), ("fr", "en", "January")],
)
def test_assigned_language_controls_every_display_date(
    tmp_path: Path, default_language: str, assigned_language: str, month: str
) -> None:
    """A catalog default cannot relocalize an explicitly assigned notice later."""
    command, output_dir, _ = prepare_cohort(
        tmp_path, (assigned_language,), default_language
    )
    result = run_cli(command, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    job = generate_notices.read_render_jobs(
        output_dir / "artifacts", require_compiled=True
    )[0]
    notice = json.loads(job.data.read_text())
    assert month in notice["client_data"]["date_of_birth"]
    cutoff_month = "août" if assigned_language == "fr" else "August"
    assert cutoff_month in notice["client_data"]["date_data_cutoff"]
    assert len(list((output_dir / "pdf_combined").glob("*.pdf"))) == 1


def test_failed_compilation_invalidates_old_outputs(tmp_path: Path) -> None:
    """A real assertion failure removes an old PDF and prevents downstream reuse."""
    command, output_dir, config_dir = prepare_cohort(tmp_path)
    assert run_cli(command, tmp_path).returncode == 0
    artifact_dir = output_dir / "artifacts"
    jobs = generate_notices.read_render_jobs(artifact_dir, require_compiled=True)
    job = next(job for job in jobs if job.language == "fr")
    notice = json.loads(job.data.read_text())
    notice["version_id"] = "affirmative_schedule_v1"
    job.data.write_text(json.dumps(notice))
    with pytest.raises(subprocess.CalledProcessError):
        compile_notices.compile_with_config(
            artifact_dir, job.pdf.parent, config_dir / "parameters.yaml"
        )
    assert not job.pdf.exists()
    assert not list(job.pdf.parent.glob("*.partial.pdf"))
    with pytest.raises(FileNotFoundError):
        generate_notices.read_render_jobs(artifact_dir, require_compiled=True)


def test_nondefault_language_validation_failure_fails_run(tmp_path: Path) -> None:
    """An invalid French notice must fail an English-default run before bundling."""
    command, output_dir, _ = prepare_cohort(tmp_path)
    custom = tmp_path / "PHU modèles"
    shutil.copytree(ROOT / "templates", custom)
    french = custom / "overdue_standard_v1.fr.typ"
    french.write_text(
        french.read_text().replace("notice.client_row", '("9999999999",)')
    )
    result = run_cli(command + ["--templates", str(custom)], tmp_path)
    assert result.returncode == 1
    assert "PDF validation failed" in result.stderr
    assert "Pipeline completed successfully" not in result.stdout
    assert not list((output_dir / "pdf_combined").glob("*.pdf"))


def test_expected_outputs_exclude_stale_files_and_require_every_pdf(
    tmp_path: Path,
) -> None:
    """Validation and bundling follow the job map, even beside stale and encrypted PDFs."""
    command, output_dir, config_dir = prepare_cohort(tmp_path)
    assert run_cli(command, tmp_path).returncode == 0
    artifact_dir = output_dir / "artifacts"
    manifest = json.loads((artifact_dir / "render_jobs.json").read_text())
    jobs = generate_notices.read_render_jobs(artifact_dir, require_compiled=True)
    (output_dir / "pdf_individual" / "en_notice_stale.pdf").write_text("not a PDF")
    (output_dir / "pdf_individual" / "fr_notice_old_encrypted.pdf").write_text(
        "not a PDF"
    )
    orchestrator.run_step_6_validate_pdfs(output_dir, manifest["run_id"], config_dir)
    bundles = bundle_pdfs.bundle_pdfs_with_config(
        output_dir, None, manifest["run_id"], config_dir / "parameters.yaml"
    )
    assert sum(len(bundle.bundle_plan.clients) for bundle in bundles) == 2
    jobs[0].pdf.unlink()
    with pytest.raises(FileNotFoundError, match="Expected notice PDF is missing"):
        orchestrator.run_step_6_validate_pdfs(
            output_dir, manifest["run_id"], config_dir
        )
    with pytest.raises(FileNotFoundError, match="Expected notice PDF is missing"):
        bundle_pdfs.bundle_pdfs_with_config(
            output_dir, None, manifest["run_id"], config_dir / "parameters.yaml"
        )
