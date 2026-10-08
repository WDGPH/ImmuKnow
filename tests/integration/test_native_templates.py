"""Compile maintained Typst entry points with JSON and compare legacy notice text.

These acceptance tests require the real compiler. A missing executable is a
failure, including in CI; mocked compilation cannot prove the template boundary.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import qrcode
import yaml
from pypdf import PdfReader

from pipeline.generate_notices import build_notice_data
from pipeline.utils import deserialize_client_record

ROOT = Path(__file__).resolve().parents[2]
BASELINES = ROOT / "tests" / "fixtures" / "notice_baseline"
CASES = sorted(
    path.stem for path in BASELINES.glob("*.json") if path.stem != "compiler_comparison"
)
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
    shutil.copytree(ROOT / "templates", workspace / "templates")
    fixture = json.loads((BASELINES / f"{case}.json").read_text())
    client = deserialize_client_record(fixture["client"])
    config = yaml.safe_load((ROOT / "config" / "parameters.yaml").read_text())
    config["preprocess"]["show_validity_markers"] = True
    config_path = workspace / "parameters.yaml"
    config_path.write_text(yaml.safe_dump(config))
    notice = build_notice_data(client, config_path=config_path)
    notice.update(
        version_id=fixture["version_id"],
        logo_path="/templates/assets/logo.png",
        signature_path="/templates/assets/signature.png",
    )
    qrcode.make(client.qr["payload"]).save(workspace / "qr.png")
    notice["client_data"]["qr_img"] = "/qr.png"
    version_dir = (
        "" if fixture["version_id"] == "legacy_fixed_v1" else fixture["version_id"]
    )
    template = workspace / "templates" / version_dir / f"{client.language}.typ"
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
    )


@pytest.mark.parametrize("case", CASES)
def test_native_template_retains_baseline_text(tmp_path: Path, case: str) -> None:
    """Every maintained entry point preserves prose, identity, history, and markers."""
    workspace = tmp_path / "Notices été"
    template, data_file, _ = prepare_case(workspace, case)
    result = compile_notice(template, data_file, workspace)
    assert result.returncode == 0, result.stderr
    pages = PdfReader(workspace / "notice.pdf").pages
    text = "\n\f\n".join(page.extract_text() for page in pages) + "\n"
    assert text == (BASELINES / f"{case}-0.15.1.txt").read_text()
    assert "MARK_END_SIGNATURE_BLOCK" in text
    assert "0000000001" in text
    # Compilation reads the maintained source without personalizing it.
    relative = template.relative_to(workspace)
    assert template.read_bytes() == (ROOT / relative).read_bytes()


@pytest.mark.parametrize(
    ("field", "value", "diagnostic"),
    [
        ("language", "fr", "Notice language does not match this template"),
        (
            "version_id",
            "affirmative_schedule_v1",
            "Notice version does not match this template",
        ),
        (
            "vaccines_due_agents_array",
            [],
            "This overdue template requires vaccine agent data",
        ),
    ],
)
def test_native_template_rejects_incompatible_data(
    tmp_path: Path, field: str, value: object, diagnostic: str
) -> None:
    """Direct invocation cannot bypass template identity or required agent content."""
    workspace = tmp_path / "assertions"
    template, data_file, notice = prepare_case(workspace, "overdue_en")
    notice[field] = value
    data_file.write_text(json.dumps(notice))
    result = compile_notice(template, data_file, workspace)
    assert result.returncode != 0
    assert diagnostic in result.stderr
    assert not (workspace / "notice.pdf").exists()


def test_json_punctuation_remains_text(tmp_path: Path) -> None:
    """Input punctuation, accents, empty collections, and nulls never become code."""
    workspace = tmp_path / "ordinary data"
    template, data_file, notice = prepare_case(workspace, "legacy_en")
    literal = 'Élodie "O\'Connor" \\ #panic("EXECUTED") [*text*] $x$ @name'
    notice["client_data"]["name"] = literal
    notice["client_data"]["address"] = "First line\nSecond line"
    notice["received"] = []
    notice["num_rows"] = 0
    notice["optional_metadata"] = None
    data_file.write_text(json.dumps(notice, ensure_ascii=False))
    result = compile_notice(template, data_file, workspace)
    assert result.returncode == 0, result.stderr
    text = "\n".join(
        page.extract_text() for page in PdfReader(workspace / "notice.pdf").pages
    )
    assert '#panic("EXECUTED")' in text
    assert "[*text*] $x$ @name" in " ".join(text.split())
