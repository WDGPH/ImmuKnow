"""Native custom templates remain isolated and work outside the checkout."""

import json
import shutil

import pandas as pd
from pathlib import Path

import pytest
from pypdf import PdfReader

from immuknow.generate_notices import select_template
from immuknow.orchestrator import run_pipeline
from tests.integration.test_native_pipeline import ROOT, prepare_cohort, run_cli

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("language", ["en", "fr"])
def test_single_language_custom_template(tmp_path: Path, language: str) -> None:
    """A PHU needs only its supported language, with its own unchanged source."""
    command, output_dir, _ = prepare_cohort(tmp_path, (language,))
    custom = tmp_path / "PHU modèles"
    shutil.copytree(ROOT / "immuknow" / "templates", custom)
    other = "fr" if language == "en" else "en"
    (custom / f"overdue_agents_v1.{other}.typ").unlink()
    entry = custom / f"overdue_agents_v1.{language}.typ"
    entry.write_text(entry.read_text() + "\n#text(size: 8pt)[PHU CUSTOM TEMPLATE]\n")
    result = run_cli(command + ["--templates", str(custom)], tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    pdf = next(output_dir.glob("*/originals/*.pdf"))
    assert "PHU CUSTOM TEMPLATE" in "\n".join(
        page.extract_text() for page in PdfReader(pdf).pages
    )
    with pytest.raises(FileNotFoundError, match="Notice template not found"):
        select_template(custom, "overdue_agents_v1", other)


@pytest.mark.parametrize(
    "version", ["../private", "/tmp/template", "a/b", "a\\b", ".."]
)
def test_unsafe_template_version_rejected(tmp_path: Path, version: str) -> None:
    """Version identifiers must not escape the selected template directory."""
    with pytest.raises(ValueError, match="Unsafe notice version"):
        select_template(tmp_path, version, "en")


def test_missing_affirmative_translation_is_not_invented() -> None:
    """French affirmative notices remain unavailable until an author supplies one."""
    with pytest.raises(FileNotFoundError, match="fr.typ"):
        select_template(
            ROOT / "immuknow" / "templates", "affirmative_schedule_v1", "fr"
        )


def test_sequential_runs_freeze_project_labels_and_keep_source_facts(tmp_path: Path):
    """Later Settings/label edits affect the new run without changing saved originals."""
    command, output, config = prepare_cohort(tmp_path, ("fr",))
    source = Path(command[3])
    frame = pd.read_csv(source, dtype=str, keep_default_na=False)
    frame["imms_given"] = "2020-05-01 - MMR; 2020-05-02 - Ig;"
    frame.to_csv(source, index=False)
    custom = tmp_path / "project"
    shutil.copytree(ROOT / "immuknow/templates", custom)
    template = custom / "overdue_diseases_v1.fr.typ"
    first_path = run_pipeline(
        source, output, config_dir=config, notice_template=template
    )
    first_bytes = first_path.read_bytes()
    first = json.loads(first_bytes)
    first_pdf = first_path.parent / first["entries"][0]["original"]["path"]
    first_pdf_bytes = first_pdf.read_bytes()
    labels_path = custom / "translations/fr_diseases_overdue.json"
    labels = json.loads(labels_path.read_text())
    labels["Measles"] = "LIBELLÉ LOCAL SÉLECTIONNÉ"
    labels_path.write_text(json.dumps(labels, ensure_ascii=False))
    settings = custom / "settings.typ"
    settings.write_text(
        settings.read_text().replace(
            'ignore-agents: ("RSVAb", "VarIg", "HBIg", "RabIg", "Ig"),',
            "ignore-agents: (),",
        )
    )
    second_path = run_pipeline(
        source, output, config_dir=config, notice_template=template
    )
    second = json.loads(second_path.read_text())
    second_pdf = second_path.parent / second["entries"][0]["original"]["path"]
    assert first_path.parent != second_path.parent
    assert first_path.read_bytes() == first_bytes
    assert first_pdf.read_bytes() == first_pdf_bytes
    first_text = " ".join(
        " ".join(p.extract_text().split()) for p in PdfReader(first_pdf).pages
    )
    second_text = " ".join(
        " ".join(p.extract_text().split()) for p in PdfReader(second_pdf).pages
    )
    assert "Rougeole" in first_text and "LIBELLÉ LOCAL SÉLECTIONNÉ" not in first_text
    assert "LIBELLÉ LOCAL SÉLECTIONNÉ" in second_text
    assert " Ig " not in first_text and " Ig " in second_text
    for path, record in ((first_path, first), (second_path, second)):
        facts = json.loads(
            (path.parent / record["entries"][0]["facts"]["path"]).read_text()
        )
        assert [row["agent"] for row in facts["history"]] == ["MMR", "Ig"]
        assert facts["overdue_diseases"] == [{"disease": "Measles", "dose": 2}]


def test_template_symlink_keeps_the_selected_filename_and_project(tmp_path: Path):
    command, output, config = prepare_cohort(tmp_path, ("fr",))
    source = Path(command[3])
    custom = tmp_path / "project"
    shutil.copytree(ROOT / "immuknow/templates", custom)
    # A filename chooses identity even when its bytes come from a symlink.
    # Surrounding authored English prose is not automatically translated.
    entry = custom / "overdue_diseases_v1.fr.typ"
    entry.unlink()
    entry.symlink_to(ROOT / "immuknow/templates/overdue_diseases_v1.en.typ")
    labels = custom / "translations/fr_diseases_overdue.json"
    selected = json.loads(labels.read_text())
    selected["Measles"] = "PROJECT LABEL RETAINED"
    labels.write_text(json.dumps(selected))
    saved = run_pipeline(source, output, config_dir=config, notice_template=entry)
    record = json.loads(saved.read_text())
    assigned = record["entries"][0]
    assert assigned["assignment"]["template"] == entry.name
    assert assigned["render_summary"]["identity"]["language"] == "fr"
    assert record["configuration"]["templates"] == str(custom)
    text = " ".join(
        page.extract_text()
        for page in PdfReader(saved.parent / assigned["original"]["path"]).pages
    )
    assert "PROJECT LABEL RETAINED" in text
