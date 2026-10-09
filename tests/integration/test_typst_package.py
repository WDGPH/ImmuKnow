"""Exercise the shared package with real native compilation and isolated roots."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from pypdf import PdfReader

from tests.integration.test_native_templates import ROOT, compile_notice, prepare_case

PACKAGE = ROOT / "immuknow/templates/lib/immuknow"
pytestmark = pytest.mark.integration


@pytest.mark.parametrize("installed", [False, True], ids=["vendored", "installed"])
def test_import_needs_no_client_input(tmp_path: Path, installed: bool):
    if installed:
        shutil.copytree(PACKAGE, tmp_path / "packages/local/immuknow/0.1.0")
        module = "@local/immuknow:0.1.0"
    else:
        shutil.copytree(PACKAGE, tmp_path / "lib/immuknow")
        module = "lib/immuknow/lib.typ"
    source = tmp_path / "probe.typ"
    source.write_text(
        f'#import "{module}" as ik\n#assert(type(ik.check-notice) == function)\n'
    )
    result = subprocess.run(
        [
            os.environ.get("TYPST_BIN", "typst"),
            "compile",
            "--root",
            str(tmp_path),
            "--package-path",
            str(tmp_path / "packages"),
            str(source),
            str(tmp_path / "probe.pdf"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_installed_package_validates_a_relocated_maintained_notice(
    tmp_path: Path, monkeypatch
):
    workspace = tmp_path / "relocated project"
    template, data, _ = prepare_case(workspace, "overdue_agents_fr")
    vendored = compile_notice(template, data, workspace)
    assert vendored.returncode == 0, vendored.stderr
    original_text = [
        page.extract_text() for page in PdfReader(workspace / "notice.pdf").pages
    ]
    shutil.copytree(PACKAGE, tmp_path / "packages/local/immuknow/0.1.0")
    shutil.rmtree(workspace / "templates/lib")
    template.write_text(
        template.read_text().replace(
            '"lib/immuknow/lib.typ"', '"@local/immuknow:0.1.0"'
        )
    )
    monkeypatch.setenv("TYPST_PACKAGE_PATH", str(tmp_path / "packages"))
    monkeypatch.setenv("TYPST_PACKAGE_CACHE_PATH", str(tmp_path / "empty-cache"))
    result = compile_notice(template, data, workspace)
    assert result.returncode == 0, result.stderr
    assert [
        page.extract_text() for page in PdfReader(workspace / "notice.pdf").pages
    ] == original_text


@pytest.mark.parametrize(
    "field,value,diagnostic",
    [
        ("schema_version", 2, "Unsupported rendering schema_version"),
        ("schema_version", "1", "Unsupported rendering schema_version"),
        ("history", None, "history must be an array"),
        ("validity_coverage", "valid", "Invalid validity_coverage"),
        ("rendering_defaults", {}, "missing required field: diseases"),
    ],
)
def test_native_boundary_rejects_malformed_payload(tmp_path, field, value, diagnostic):
    template, data, payload = prepare_case(tmp_path / "project", "overdue_agents_en")
    payload[field] = value
    data.write_text(json.dumps(payload))
    result = compile_notice(template, data, template.parent.parent)
    assert result.returncode != 0
    assert diagnostic in result.stderr
    assert not (template.parent.parent / "notice.pdf").exists()


def test_native_boundary_reports_missing_schema(tmp_path):
    template, data, payload = prepare_case(tmp_path / "project", "overdue_agents_en")
    del payload["schema_version"]
    data.write_text(json.dumps(payload))
    result = compile_notice(template, data, template.parent.parent)
    assert result.returncode != 0
    assert "missing required field: schema_version" in result.stderr


def test_native_boundary_rejects_nonconsecutive_duplicate_columns(tmp_path):
    template, data, payload = prepare_case(tmp_path / "project", "overdue_agents_en")
    payload["rendering_defaults"]["diseases"] = ["Measles", "Mumps", "Measles"]
    data.write_text(json.dumps(payload))
    result = compile_notice(template, data, template.parent.parent)
    assert result.returncode != 0
    assert "contains duplicate values" in result.stderr
