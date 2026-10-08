"""Native custom templates remain isolated and work outside the checkout."""

from pathlib import Path
import shutil

import pytest
from pypdf import PdfReader

from pipeline.generate_notices import select_template
from tests.integration.test_native_pipeline import ROOT, prepare_cohort, run_cli

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("language", ["en", "fr"])
def test_single_language_custom_template(tmp_path: Path, language: str) -> None:
    """A PHU needs only its supported language, with its own unchanged source."""
    command, output_dir, _ = prepare_cohort(tmp_path, (language,))
    custom = tmp_path / "PHU modèles"
    shutil.copytree(ROOT / "templates", custom)
    other = "fr" if language == "en" else "en"
    (custom / f"overdue_standard_v1.{other}.typ").unlink()
    entry = custom / f"overdue_standard_v1.{language}.typ"
    entry.write_text(entry.read_text() + "\n#text(size: 8pt)[PHU CUSTOM TEMPLATE]\n")
    result = run_cli(command + ["--templates", str(custom)], tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    pdf = next((output_dir / "pdf_individual").glob("*.pdf"))
    assert "PHU CUSTOM TEMPLATE" in "\n".join(
        page.extract_text() for page in PdfReader(pdf).pages
    )
    with pytest.raises(FileNotFoundError, match="No language or PHU fallback"):
        select_template(custom, "overdue_standard_v1", other)


def test_python_only_custom_template_has_migration_error(tmp_path: Path) -> None:
    """Private Python templates are never imported or silently replaced."""
    (tmp_path / "en_template.py").write_text('raise RuntimeError("must not execute")')
    with pytest.raises(FileNotFoundError, match="Migrate en_template.py"):
        select_template(tmp_path, "legacy_overdue_v1", "en")


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
        select_template(ROOT / "templates", "affirmative_schedule_v1", "fr")
