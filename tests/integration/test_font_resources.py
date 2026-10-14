"""Native runs use system fonts without staging or distributing font files."""

from __future__ import annotations

import json
import os
import shutil
import subprocess

import pymupdf
import pytest

from immuknow.bundle_pdfs import bundle_run
from tests.integration.test_native_pipeline import ROOT, prepare_cohort, run_cli

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "family,pdf_font", [("FreeSans", "FreeSans"), ("FreeSerif", "FreeSerif")]
)
def test_native_notice_uses_fonts_available_locally(tmp_path, family, pdf_font):
    compiler = os.environ.get("TYPST_BIN", "typst")
    available = subprocess.run(
        [compiler, "fonts"], capture_output=True, text=True, check=True, timeout=10
    ).stdout.splitlines()
    if family not in available:
        pytest.skip(f"{family} is not installed on this machine")
    command, output, _ = prepare_cohort(tmp_path, ("en", "fr"))
    templates = tmp_path / "templates"
    shutil.copytree(ROOT / "immuknow/templates", templates)
    settings = templates / "settings.typ"
    settings.write_text(
        settings.read_text().replace(
            'body-font = "FreeSans"', f'body-font = "{family}"'
        )
    )
    command += ["--templates", str(templates)]
    result = run_cli(command, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    report = next(output.glob("*/run.json"))
    record = json.loads(report.read_text())
    assert "compiler_fonts" not in record["resources"]
    assert not list(report.parent.rglob("*.ttf"))
    for entry in record["entries"]:
        assert entry["original"]["status"] == "completed"
        assert not any(
            check["code"] == "compiler.font_substitution" for check in entry["checks"]
        )
        with pymupdf.open(report.parent / entry["original"]["path"]) as pdf:
            assert any(pdf_font in font[3] for page in pdf for font in page.get_fonts())
    originals = [entry["original"] for entry in record["entries"]]
    assert bundle_run(report.parent)["status"] == "completed"
    after = json.loads(report.read_text())
    assert [entry["original"] for entry in after["entries"]] == originals
