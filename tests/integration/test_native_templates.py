"""Compile maintained Typst examples with JSON and compare baseline notice text.

These acceptance tests require the real compiler. A missing executable is a
failure, including in CI; mocked compilation cannot prove the template boundary.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import qrcode
import yaml
from pypdf import PdfReader

from immuknow.data_models import ClientRecord
from immuknow.generate_notices import build_notice_data

ROOT = Path(__file__).resolve().parents[2]
BASELINES = ROOT / "tests" / "fixtures" / "notice_baseline"
CASES = sorted(path.stem for path in BASELINES.glob("*.json"))
SIGNATURE_PAGE = {
    "affirmative_en": 1,
    "overdue_diseases_en": 2,
    "overdue_diseases_fr": 2,
    "long_address": 2,
    "long_record": 1,
    "overdue_agents_en": 1,
    "overdue_agents_fr": 2,
}
pytestmark = pytest.mark.integration


def prepare_case(workspace: Path, case: str) -> tuple[Path, Path, dict]:
    """Stage static templates and one synthetic notice in an external directory.

    Parameters
    ----------
    workspace : Path
        Test-owned file root, deliberately outside the checkout.
    case : str
        Name of a captured synthetic baseline.

    Returns
    -------
    tuple
        Selected entry point, data file, and ordinary notice data.
    """
    workspace.mkdir(parents=True)
    shutil.copytree(ROOT / "immuknow" / "templates", workspace / "templates")
    shutil.copytree(
        ROOT / "immuknow" / "config" / "translations", workspace / "translations"
    )
    fixture = json.loads((BASELINES / f"{case}.json").read_text())
    client = ClientRecord(**fixture["client"])
    config = yaml.safe_load(
        (ROOT / "immuknow" / "config" / "parameters.yaml").read_text()
    )
    config["preprocess"]["show_validity_markers"] = True
    config["preprocess"]["include_dose"] = fixture.get("include_dose", False)
    notice = build_notice_data(client, config)
    notice.update(
        version_id=fixture["version_id"],
        logo_path="/templates/assets/logo.png",
        signature_path="/templates/assets/signature.png",
    )
    assert client.qr is not None
    qrcode.make(client.qr["payload"]).save(workspace / "qr.png")
    notice["client_data"]["qr_img"] = "/qr.png"
    template = (
        workspace / "templates" / f"{fixture['version_id']}.{client.language}.typ"
    )
    data_file = workspace / "notice.json"
    data_file.write_text(json.dumps(notice, ensure_ascii=False))
    return template, data_file, notice


def compile_notice(
    template: Path, data_file: Path, workspace: Path
) -> subprocess.CompletedProcess:
    """Invoke real Typst with only a file reference in its command-line input."""
    return subprocess.run(
        [
            os.environ.get("TYPST_BIN", "typst"),
            "compile",
            "--root",
            str(workspace),
            "--input",
            "data=/notice.json",
            str(template),
            str(workspace / "notice.pdf"),
        ],
        cwd=workspace,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("case", CASES)
def test_native_template_retains_baseline_text(tmp_path: Path, case: str) -> None:
    """Every maintained entry point preserves prose, identity, history, and markers."""
    workspace = tmp_path / "Notices été"
    template, data_file, _ = prepare_case(workspace, case)
    result = compile_notice(template, data_file, workspace)
    assert result.returncode == 0, result.stderr
    reader = PdfReader(workspace / "notice.pdf")
    pages = [page.extract_text() for page in reader.pages]
    expected_pages = (BASELINES / f"{case}-0.15.1.txt").read_text().split("\n\f\n")
    assert len(pages) == len(expected_pages)
    for actual, expected in zip(pages, expected_pages):
        assert " ".join(actual.split()) == " ".join(expected.split())

    assert reader.root_object.get("/Lang") == f"{case_language(case)}-CA"
    assert [
        i for i, page in enumerate(pages, start=1) if "MARK_END_SIGNATURE_BLOCK" in page
    ] == [SIGNATURE_PAGE[case]]
    assert "0000000001" in pages[0]
    contact = re.search(r"MEASURE_CONTACT_HEIGHT:([0-9.]+)", pages[0])
    assert contact is not None
    assert float(contact.group(1)) <= 81.0 + 0.01
    table_date_heading = (
        "Date Given" if case_language(case) == "en" else "Date de l'administration"
    )
    assert table_date_heading in " ".join(pages[-1].split())
    # Compilation reads the maintained source without personalizing it.
    relative = template.relative_to(workspace)
    assert template.read_bytes() == (ROOT / "immuknow" / relative).read_bytes()


def case_language(case: str) -> str:
    """Read the assigned language from the synthetic baseline input."""
    return json.loads((BASELINES / f"{case}.json").read_text())["client"]["language"]


@pytest.mark.parametrize(
    ("case", "field", "value", "diagnostic"),
    [
        (
            "overdue_agents_en",
            "language",
            "fr",
            "Notice language does not match this template",
        ),
        (
            "overdue_agents_fr",
            "language",
            "en",
            "Notice language does not match this template",
        ),
        (
            "overdue_agents_en",
            "version_id",
            "affirmative_schedule_v1",
            "Notice version does not match this template",
        ),
        (
            "overdue_agents_en",
            "overdue_agents",
            [],
            "This overdue template requires vaccine agent data",
        ),
        (
            "overdue_agents_fr",
            "overdue_agents",
            [],
            "This overdue template requires vaccine agent data",
        ),
    ],
)
def test_native_template_rejects_incompatible_data(
    tmp_path: Path, case: str, field: str, value: object, diagnostic: str
) -> None:
    """Direct invocation cannot bypass template identity or required agent content."""
    workspace = tmp_path / "assertions"
    template, data_file, notice = prepare_case(workspace, case)
    notice[field] = value
    data_file.write_text(json.dumps(notice))
    result = compile_notice(template, data_file, workspace)
    assert result.returncode != 0
    assert diagnostic in result.stderr
    assert not (workspace / "notice.pdf").exists()


@pytest.mark.parametrize("case", ["overdue_agents_en", "overdue_agents_fr"])
def test_agent_templates_show_agents_independently_of_diseases(
    tmp_path: Path, case: str
) -> None:
    """An agent notice displays selected vaccine agents in either language."""
    workspace = tmp_path / "agent content"
    template, data_file, notice = prepare_case(workspace, case)
    notice["overdue_diseases"] = []
    notice["overdue_agents"] = ["MMR", "DTaP"]
    data_file.write_text(json.dumps(notice, ensure_ascii=False))
    result = compile_notice(template, data_file, workspace)
    assert result.returncode == 0, result.stderr
    first_page = PdfReader(workspace / "notice.pdf").pages[0].extract_text()
    assert "• MMR" in first_page
    assert "• DTaP" in first_page
    assert "• Measles" not in first_page
    assert "• Rougeole" not in first_page


def test_json_punctuation_remains_text(tmp_path: Path) -> None:
    """Input punctuation, accents, empty collections, and nulls never become code."""
    workspace = tmp_path / "ordinary data"
    template, data_file, notice = prepare_case(workspace, "overdue_diseases_en")
    literal = 'Élodie "O\'Connor" \\ #panic("EXECUTED") [*text*] $x$ @name'
    notice["client_data"]["name"] = literal
    notice["client_data"]["address"] = "First line\nSecond line"
    notice["received"] = []
    notice["optional_metadata"] = None
    data_file.write_text(json.dumps(notice, ensure_ascii=False))
    result = compile_notice(template, data_file, workspace)
    assert result.returncode == 0, result.stderr
    text = "\n".join(
        page.extract_text() for page in PdfReader(workspace / "notice.pdf").pages
    )
    assert '#panic("EXECUTED")' in text
    assert "[*text*] $x$ @name" in " ".join(text.split())


def compile_presentation_probe(
    workspace: Path, body: str
) -> subprocess.CompletedProcess:
    """Evaluate the maintained presentation helper with the real Typst compiler."""
    workspace.mkdir(parents=True)
    shutil.copytree(ROOT / "immuknow" / "templates", workspace / "templates")
    shutil.copytree(
        ROOT / "immuknow" / "config" / "translations", workspace / "translations"
    )
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


def test_missing_approved_label_fails_native_render(tmp_path: Path) -> None:
    """An incomplete selected dictionary cannot silently drop an overdue item."""
    workspace = tmp_path / "missing label"
    template, data_file, _ = prepare_case(workspace, "overdue_diseases_fr")
    path = workspace / "translations" / "fr_diseases_overdue.json"
    labels = json.loads(path.read_text())
    del labels["Measles"]
    path.write_text(json.dumps(labels, ensure_ascii=False))
    result = compile_notice(template, data_file, workspace)
    assert result.returncode != 0
    assert "Missing fr diseases_overdue label for Measles" in result.stderr
    assert not (workspace / "notice.pdf").exists()


def test_uncatalogued_source_label_remains_visible(tmp_path: Path) -> None:
    """Grouped source text is preserved without inventing a translated label."""
    workspace = tmp_path / "uncatalogued source label"
    template, data_file, notice = prepare_case(workspace, "overdue_diseases_fr")
    notice["overdue_diseases"] = [
        {"disease": "Diphtheria/Tetanus/Pertussis", "dose": None}
    ]
    data_file.write_text(json.dumps(notice))
    result = compile_notice(template, data_file, workspace)
    assert result.returncode == 0, result.stderr
    text = "\n".join(
        page.extract_text() for page in PdfReader(workspace / "notice.pdf").pages
    )
    assert "Diphtheria/Tetanus/Pertussis" in text
    assert "31 août 2025" in text


def test_duplicate_display_labels_do_not_merge_chart_cells(tmp_path: Path) -> None:
    """Two canonical keys can share a heading while their record cells stay distinct."""
    workspace = tmp_path / "duplicate display labels"
    template, data_file, notice = prepare_case(workspace, "overdue_diseases_fr")
    chart_path = workspace / "translations" / "fr_diseases_chart.json"
    labels = json.loads(chart_path.read_text())
    labels["Measles"] = "Même libellé"
    labels["Mumps"] = "Même libellé"
    chart_path.write_text(json.dumps(labels, ensure_ascii=False))
    notice["received"] = [
        {
            "date_given": "2024-02-29",
            "date_rowspan": 1,
            "vaccines": ["MMR"],
            "columns": {"Measles": "valid"},
        }
    ]
    notice["show_validity_markers"] = False
    data_file.write_text(json.dumps(notice, ensure_ascii=False))
    result = compile_notice(template, data_file, workspace)
    assert result.returncode == 0, result.stderr
    chart_text = PdfReader(workspace / "notice.pdf").pages[-1].extract_text()
    assert chart_text.count("Même libellé") == 2
    assert chart_text.count("⬤") == 1
