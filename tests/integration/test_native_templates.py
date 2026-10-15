"""Compile maintained entry points and retain semantic, literal-data and label checks."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from pypdf import PdfReader

from immuknow.compile_notices import compile_render_job, evaluate_render_job
from immuknow.generate_notices import prepare_render_jobs
from tests.fixtures.sample_input import create_test_client_record

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


def prepare_case(
    workspace: Path, version: str = "overdue_diseases_v1", language: str = "en"
):
    shutil.copytree(ROOT / "immuknow/templates", workspace / "resources/templates")
    client = replace(
        create_test_client_record(has_received_vaccines=True, language=language),
        version_id=version,
        overdue_diseases=[{"disease": "Measles", "dose": 2}],
        overdue_agents=["MMR", "DTaP"],
    )
    if version == "affirmative_schedule_v1":
        client = replace(client, overdue_diseases=[], overdue_agents=[])
    config = yaml.safe_load((ROOT / "immuknow/config/parameters.yaml").read_text())
    config["creation_timestamp"] = 1780272000
    job = prepare_render_jobs([client], workspace, config)[0]
    return job, json.loads(job.data.read_text())


def compile_case(job):
    assert not compile_render_job(job, os.environ.get("TYPST_BIN", "typst"))
    report = evaluate_render_job(job, os.environ.get("TYPST_BIN", "typst"))
    reader = PdfReader(job.pdf)
    assert report["page_count"] == len(reader.pages)
    return report, reader


@pytest.mark.parametrize(
    "version,language,title,selected_wording,pages",
    [
        (
            "overdue_diseases_v1",
            "en",
            "Request for Immunization Record",
            "your child has",
            2,
        ),
        (
            "overdue_diseases_v1",
            "fr",
            "Demande de dossier d'immunisation",
            "votre enfant n’a",
            2,
        ),
        (
            "overdue_agents_v1",
            "en",
            "Request for Immunization Record",
            "your child has",
            2,
        ),
        (
            "overdue_agents_v1",
            "fr",
            "Demande de dossier d'immunisation",
            "votre enfant n’a",
            2,
        ),
        (
            "affirmative_schedule_v1",
            "en",
            "Request for Immunization Record",
            "your child is",
            2,
        ),
        (
            "suspension_order_v1",
            "en",
            "Order for Suspension from Attendance at School",
            "twenty school days",
            1,
        ),
    ],
)
def test_maintained_entry_points_keep_their_content_and_component_choices(
    tmp_path: Path,
    version: str,
    language: str,
    title: str,
    selected_wording: str,
    pages: int,
):
    job, _ = prepare_case(tmp_path, version, language)
    report, reader = compile_case(job)
    first = " ".join(reader.pages[0].extract_text().split())
    assert title in first
    assert selected_wording in first
    assert "0000000001" in first
    assert reader.root_object["/Lang"] == language + "-CA"
    assert len(reader.pages) == pages
    assert report["identity"] == {
        "row_key": job.sequence,
        "template": job.template.name,
        "client_id": "0000000001",
        "version_id": version,
        "language": language,
    }
    assert (
        job.template.read_bytes()
        == (ROOT / "immuknow/templates" / job.template.name).read_bytes()
    )
    assert not any(
        "MARK_END_" in page.extract_text() or "MEASURE_" in page.extract_text()
        for page in reader.pages
    )
    suspension = version == "suspension_order_v1"
    assert report["components"]["history"] is (not suspension)
    assert report["components"]["privacy"] is (not suspension)
    privacy_text = (
        "The information in this notice was collected"
        if language == "en"
        else "Les renseignements figurant dans cet avis"
    )
    assert privacy_text not in first
    if not suspension:
        last = " ".join(reader.pages[-1].extract_text().split())
        assert privacy_text in last
        assert report["measurements"]["privacy"] == [{"page": pages}]
        assert any(
            check["code"] == "layout.privacy_page" and check["status"] == "pass"
            for check in report["checks"]
        )
        assert "2020-05-01" in last and "DTaP" in last
        assert (
            "End of immunization record"
            if language == "en"
            else "Fin du dossier d’immunisation"
        ) in last
    if version == "overdue_agents_v1":
        assert "MMR" in first and "DTaP" in first
        assert ("• Measles" if language == "en" else "• Rougeole") not in first
    elif version == "overdue_diseases_v1":
        assert ("Measles" if language == "en" else "Rougeole") in first


@pytest.mark.parametrize(
    "field,value,diagnostic",
    [
        ("language", "fr", "Notice language does not match this template"),
        (
            "version_id",
            "affirmative_schedule_v1",
            "Notice version does not match this template",
        ),
    ],
)
def test_trusted_filename_identity_rejects_mismatched_facts(
    tmp_path: Path, field, value, diagnostic
):
    job, notice = prepare_case(tmp_path)
    notice[field] = value
    job.data.write_text(json.dumps(notice))
    with pytest.raises(subprocess.CalledProcessError) as failure:
        compile_case(job)
    assert diagnostic in failure.value.stderr
    assert not job.pdf.exists()
    assert not job.pdf.with_suffix(".partial.pdf").exists()


def test_json_punctuation_remains_literal_text(tmp_path: Path):
    job, notice = prepare_case(tmp_path)
    literal = 'Élodie "O\'Connor" \\ #panic("EXECUTED") [*text*] $x$ @name'
    notice["client_data"]["name"] = literal
    notice["client_data"]["address"] = "First line\nSecond line"
    notice["history"] = []
    job.data.write_text(json.dumps(notice, ensure_ascii=False))
    _, reader = compile_case(job)
    text = " ".join(" ".join(page.extract_text().split()) for page in reader.pages)
    assert '#panic("EXECUTED")' in text
    assert "[*text*] $x$ @name" in text
    assert "First line Second line" in text


def compile_presentation_probe(
    workspace: Path, body: str
) -> subprocess.CompletedProcess:
    """Evaluate the maintained presentation helper with the real Typst compiler."""
    workspace.mkdir(parents=True)
    shutil.copytree(ROOT / "immuknow" / "templates", workspace / "templates")
    probe = workspace / "probe.typ"
    probe.write_text('#import "/templates/presentation.typ" as presentation\n' + body)
    return subprocess.run(
        [
            os.environ.get("TYPST_BIN", "typst"),
            "compile",
            "--root",
            str(workspace),
            str(probe),
            str(workspace / "probe.pdf"),
        ],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )


def test_presentation_dates_and_doses(tmp_path: Path) -> None:
    """Both languages cover every month, leap day, and ordinal exceptions."""
    workspace = tmp_path / "localized dates"
    expressions = []
    expected = []
    months_en = (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    )
    months_fr = (
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    )
    for month, (english, french) in enumerate(zip(months_en, months_fr), start=1):
        day = 29 if month == 2 else 1
        iso = f"2024-{month:02d}-{day:02d}"
        for language, formatted in (
            ("en", f"{english} {day}, 2024"),
            ("fr", f"{day} {french} 2024"),
        ):
            expressions.append(f'#presentation.long-date("{iso}", "{language}")')
            expected.append(formatted)
    for dose in (1, 2, 3, 11, 12, 13, 21):
        suffix = {1: "st", 2: "nd", 3: "rd", 21: "st"}.get(dose, "th")
        expressions.append(
            f'#presentation.overdue-label((disease: "Measles", dose: {dose}), true, "en")'
        )
        expected.append(f"Measles ({dose}{suffix} dose)")
        expressions.append(
            f'#presentation.overdue-label((disease: "Measles", dose: {dose}), true, "fr")'
        )
        expected.append(f"Rougeole ({dose}{'re' if dose == 1 else 'e'} dose)")
    body = "\n#linebreak()\n".join(expressions)
    body += '\n#assert(presentation.long-date("", "fr", required: false) == "")\n'
    result = compile_presentation_probe(workspace, body)
    assert result.returncode == 0, result.stderr
    rendered = "\n".join(
        page.extract_text() for page in PdfReader(workspace / "probe.pdf").pages
    )
    for value in expected:
        assert value in rendered


@pytest.mark.parametrize("value", ["", "2023-02-29", "2024-13-01", "2024-1-01"])
def test_presentation_rejects_missing_or_invalid_required_date(
    tmp_path: Path, value: str
) -> None:
    workspace = tmp_path / "invalid date"
    result = compile_presentation_probe(
        workspace,
        f'#presentation.long-date("{value}", "en")',
    )
    assert result.returncode != 0
    assert not (workspace / "probe.pdf").exists()


def test_missing_selected_language_label_warns_and_preserves_raw_disease(
    tmp_path: Path,
):
    job, _ = prepare_case(tmp_path, language="fr")
    path = tmp_path / "resources/templates/translations/fr_diseases_overdue.json"
    labels = json.loads(path.read_text())
    del labels["Measles"]
    path.write_text(json.dumps(labels))
    report, reader = compile_case(job)
    assert "Measles" in reader.pages[0].extract_text()
    assert any(
        c["code"] == "content.translation_missing"
        and c["status"] == "warn"
        and c["component"] == "overdue_diseases"
        for c in report["checks"]
    )


def test_uncatalogued_source_label_remains_visible(tmp_path: Path):
    job, notice = prepare_case(tmp_path, language="fr")
    notice["overdue_diseases"] = [
        {"disease": "Diphtheria/Tetanus/Pertussis", "dose": None}
    ]
    job.data.write_text(json.dumps(notice))
    _, reader = compile_case(job)
    assert "Diphtheria/Tetanus/Pertussis" in reader.pages[0].extract_text()
    assert "31 août 2025" in reader.pages[0].extract_text()


def test_duplicate_display_labels_keep_distinct_disease_cells(tmp_path: Path):
    job, notice = prepare_case(tmp_path, language="fr")
    chart = tmp_path / "resources/templates/translations/fr_diseases_chart.json"
    labels = json.loads(chart.read_text())
    labels.update(Measles="Même libellé", Mumps="Même libellé")
    chart.write_text(json.dumps(labels))
    settings = tmp_path / "resources/templates/settings.typ"
    settings.write_text(
        settings.read_text()
        + '\n#let immunization-history() = immuknow.immunization-history(notice, diseases: ("Measles", "Mumps"), include-other: false, labels: presentation.selected-labels())\n'
    )
    notice["history"] = [
        {
            "date_given": "2024-02-29",
            "agent": "source-agent",
            "display_name": "source-agent",
            "diseases": ["Measles"],
            "validity": "valid",
        }
    ]
    job.data.write_text(json.dumps(notice))
    report, reader = compile_case(job)
    chart_text = reader.pages[-1].extract_text()
    assert chart_text.count("Même libellé") == 2
    assert chart_text.count("⬤") == 1
    assert report["measurements"]["history"][0]["displayed_rows"] == 1
