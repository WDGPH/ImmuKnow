"""Compiler discovery and pinned-version diagnostics."""

from __future__ import annotations

import subprocess
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from immuknow import compile_notices
from immuknow.data_models import RenderJob
from immuknow.render_contract import report_schema
from immuknow.validate_pdfs import inspect_notice

FONT_PATH = Path(__file__).resolve().parents[2] / "immuknow/templates/fonts"


@pytest.mark.unit
def test_missing_compiler_has_installation_guidance() -> None:
    """An unavailable executable should explain the supported selection routes."""
    with pytest.raises(RuntimeError, match="Install Typst 0.15.1.*TYPST_BIN"):
        compile_notices.check_compiler("/missing/typst")


@pytest.mark.unit
@pytest.mark.parametrize("version", ["0.14.2", "0.15.0", "0.16.0-rc1"])
def test_unsupported_compiler_is_rejected(version: str) -> None:
    """Older compilers and untested prereleases must fail before notice compilation."""
    result = subprocess.CompletedProcess([], 0, stdout=f"typst {version} (test)")
    with (
        patch("immuknow.compile_notices.subprocess.run", return_value=result),
        pytest.raises(RuntimeError, match="Unsupported compiler"),
    ):
        compile_notices.check_compiler("typst")


@pytest.mark.integration
def test_pdf_and_required_evidence_are_separate_outputs(tmp_path: Path) -> None:
    """A real warning PDF survives missing evidence, and a phone is not identity."""
    data = tmp_path / "data.json"
    data.write_text("{}")
    entry = tmp_path / "example.en.typ"
    summary = {
        "schema_version": 2,
        "identity": {
            "row_key": "row-000001",
            "template": "example.en.typ",
            "client_id": "0000000001",
            "version_id": "example",
            "language": "en",
        },
        "page_count": 1,
        "components": {
            name: name == "client"
            for name in report_schema()["properties"]["components"]["properties"]
        },
        "checks": [
            {
                "code": "compiler.warning",
                "stage": "render",
                "status": "warn",
                "message": "Visible warning example.",
            }
        ],
        "qr_urls": [],
        "measurements": {
            "client": [{"client_id": "0000000001", "page": 1, "x_pt": 0, "y_pt": 0}]
        },
    }
    summary["checks"] += [
        {
            "code": f"component.{name}.absent",
            "stage": "render",
            "status": "not_applicable",
            "message": "Component was not used.",
            "component": name,
        }
        for name, placed in summary["components"].items()
        if not placed
    ]
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(summary))
    source = (
        '#set text(font: "Unavailable ImmuKnow Test Font")\n'
        "Phone: 0000000001\n\nClient ID: 9999999999\n"
        '#context { [#metadata(json("evidence.json")) <immuknow-report>] }'
    )
    entry.write_text(source)
    job = RenderJob(
        "row-000001",
        "0000000001",
        "en",
        "example",
        tmp_path,
        entry,
        data,
        tmp_path / "original.pdf",
        1735689600,
    )
    warnings = compile_notices.compile_render_job(job, "typst")
    assert [warning.code for warning in warnings] == ["compiler.font_substitution"]
    report = compile_notices.evaluate_render_job(job, "typst")
    original, checks = inspect_notice(job, tmp_path, report)
    assert original["pages"] == 1
    assert report["checks"][0]["code"] == "compiler.warning"
    assert (
        next(check for check in checks if check.code == "output.client_identity").status
        == "fail"
    )
    entry.write_text(source.replace("9999999999", "0000000001"))
    compile_notices.compile_render_job(job, "typst")
    _, checks = inspect_notice(
        job, tmp_path, compile_notices.evaluate_render_job(job, "typst")
    )
    assert (
        next(check for check in checks if check.code == "output.client_identity").status
        == "pass"
    )
    entry.write_text("Client ID: 0000000001")
    compile_notices.compile_render_job(job, "typst")
    with pytest.raises(ValueError, match="exactly one"):
        compile_notices.evaluate_render_job(job, "typst")
    assert job.pdf.is_file()
    _, checks = inspect_notice(job, tmp_path, None)
    assert any(
        check.code == "output.evidence_matches" and check.status == "fail"
        for check in checks
    )
    entry.write_text('#panic("real compile failure")')
    with pytest.raises(subprocess.CalledProcessError) as failure:
        compile_notices.compile_render_job(job, "typst")
    assert "real compile failure" in failure.value.stderr
    assert not job.pdf.exists()
