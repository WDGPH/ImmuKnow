"""Complete CSV-to-validated-and-bundled notice workflow tests."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from pypdf import PdfReader

from tests.integration.test_native_pipeline import prepare_cohort, run_cli

pytestmark = pytest.mark.e2e


def assert_complete_notices(output_dir: Path, language: str, count: int) -> None:
    """Check the rendered and validated cohort, rather than only CLI success."""
    notices = sorted((output_dir / "pdf_individual").glob(f"{language}_notice_*.pdf"))
    assert len(notices) == count
    validation_files = list((output_dir / "metadata").glob("validation_*.json"))
    assert len(validation_files) == 1
    validation = json.loads(validation_files[0].read_text(encoding="utf-8"))
    assert validation["warning_count"] == 0
    assert validation["passed_count"] == count
    assert validation["page_count_distribution"] == {"2": count}
    assert all(len(PdfReader(notice).pages) == 2 for notice in notices)
    assert list((output_dir / "pdf_combined").glob("*.pdf"))


@pytest.mark.parametrize("language", ["en", "fr"])
def test_full_pipeline_for_language(tmp_path: Path, language: str) -> None:
    """Each assigned language reaches compilation, validation, and bundling."""
    command, output_dir, _ = prepare_cohort(tmp_path, (language,) * 3)
    result = run_cli(command, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Pipeline completed successfully" in result.stdout
    assert_complete_notices(output_dir, language, 3)


def test_full_pipeline_with_encryption(tmp_path: Path) -> None:
    """Every expected notice receives a decryptable encrypted delivery copy."""
    command, output_dir, _ = prepare_cohort(tmp_path, ("en",) * 3, encrypted=True)
    result = run_cli(command, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Pipeline completed successfully" in result.stdout
    encrypted = sorted((output_dir / "pdf_individual").glob("*_encrypted.pdf"))
    assert len(encrypted) == 3
    with Path(command[3]).open(newline="", encoding="utf-8") as source:
        passwords = {
            row["client_id"]: row["date_of_birth"].replace("-", "")
            for row in csv.DictReader(source)
        }
    for path in encrypted:
        pdf = PdfReader(path)
        assert pdf.is_encrypted
        client_id = path.stem.split("_")[-2]
        assert pdf.decrypt(passwords[client_id])
    assert list((output_dir / "pdf_combined").glob("*.pdf"))
