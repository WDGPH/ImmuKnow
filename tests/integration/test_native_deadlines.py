"""Real sleeping compiler processes exercise timeout recording and recovery."""

from __future__ import annotations

import json
import shutil
import sys
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from pypdf import PdfReader

from immuknow import bundle_pdfs, run_report
from immuknow.compile_notices import CompilerTimeoutError
from immuknow.orchestrator import run_pipeline
from tests.integration.test_run_accounting import prepare_inputs

pytestmark = pytest.mark.integration

# Long enough for the stub interpreter to start under coverage and parallel load.
VERSION_DEADLINE = 3


def sleeping_compiler(tmp_path: Path, operation: str) -> Path:
    """Delegate to real Typst except for one deliberately stalled operation."""
    native = shutil.which("typst")
    assert native is not None
    executable = tmp_path / "sleeping-typst"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import os, sys, time\n"
        "from pathlib import Path\n"
        f"operation = {operation!r}\n"
        "args = sys.argv[1:]\n"
        "selected_row = any('row-000001' in arg for arg in args)\n"
        "stall = (operation == 'version' and args == ['--version']) or (\n"
        "    operation == 'compile' and args[0] == 'compile' and selected_row\n"
        ") or (operation == 'evidence' and args[0] == 'eval' and selected_row) or (\n"
        "    operation in ('review_sheet', 'review_stamp') and args[0] == 'compile'\n"
        "    and any(Path(arg).name == operation + '.typ' for arg in args)\n"
        ")\n"
        "if stall:\n"
        f"    Path({str(tmp_path / 'stalled-operation')!r}).write_text(operation)\n"
        "    if args[0] == 'compile':\n"
        "        Path(args[-1]).write_bytes(b'incomplete output')\n"
        "    time.sleep(60)\n"
        f"os.execv({native!r}, [{native!r}, *args])\n"
    )
    executable.chmod(0o700)
    return executable


def set_deadline(config: Path, operation: str) -> None:
    parameters = config / "parameters.yaml"
    settings = yaml.safe_load(parameters.read_text())
    settings["typst"]["timeouts_seconds"] = {
        operation: VERSION_DEADLINE if operation == "version" else 5
    }
    parameters.write_text(yaml.safe_dump(settings))


def test_version_timeout_preserves_failed_setup(tmp_path, monkeypatch):
    source, config, templates, _ = prepare_inputs(tmp_path)
    set_deadline(config, "version")
    monkeypatch.setenv("TYPST_BIN", str(sleeping_compiler(tmp_path, "version")))
    output = tmp_path / "runs"
    with pytest.raises(
        CompilerTimeoutError, match=f"version probe.*{VERSION_DEADLINE}-second"
    ):
        run_pipeline(
            source,
            output,
            config_dir=config,
            notice_template=templates / "overdue_agents_v1.en.typ",
        )
    record_path = next(output.glob("*/run.json"))
    record = json.loads(record_path.read_text())
    assert record["status"] == "failed_setup"
    assert len(record["entries"]) == 2
    assert all(entry["original"]["status"] == "not_run" for entry in record["entries"])
    assert not record["delivery_attempts"]
    assert not list(record_path.parent.rglob("*.pdf"))
    assert "version probe" in record["checks"][-1]["message"]


@pytest.mark.parametrize("operation", ["compile", "evidence"])
def test_row_timeout_continues_independent_rows(tmp_path, monkeypatch, operation):
    source, config, templates, _ = prepare_inputs(tmp_path)
    set_deadline(config, operation)
    monkeypatch.setenv("TYPST_BIN", str(sleeping_compiler(tmp_path, operation)))
    record_path = run_pipeline(
        source,
        tmp_path / "runs",
        config_dir=config,
        notice_template=templates / "overdue_agents_v1.en.typ",
    )
    record = json.loads(record_path.read_text())
    first, second = record["entries"]
    assert record["status"] == "completed_with_failures"
    assert second["original"]["status"] == "completed"
    assert second["render_summary"]
    assert not list(record_path.parent.rglob("*.partial.pdf"))
    limits = record["configuration"]["effective"]["typst"]["timeouts_seconds"]
    assert limits[operation] == 5
    assert (tmp_path / "stalled-operation").read_text() == operation
    assert limits["version"] == 10
    if operation == "compile":
        assert first["original"]["status"] == "failed"
        assert first["bundle"] is None
        assert not (record_path.parent / "originals/row-000001.pdf").exists()
    else:
        assert first["original"]["status"] == "completed"
        original = record_path.parent / first["original"]["path"]
        original_bytes = original.read_bytes()
        assert PdfReader(original).pages
        assert first["routing"]["destination"] == "review"
        # A failure alone must remain held, when the operator clears withholding.
        first["checks"] = [
            check for check in first["checks"] if check["status"] != "warn"
        ]
        run_report.write_report(record_path.parent, record)
        attempt = bundle_pdfs.bundle_run(record_path.parent, withhold=[])
        record = json.loads(record_path.read_text())
        first = record["entries"][0]
        assert attempt["status"] == "completed"
        assert first["routing"]["destination"] == "review"
        assert first["routing"]["reason"] == "Failed checks"
        assert "render.evidence_failed" in first["routing"]["failed_checks"]
        assert original.read_bytes() == original_bytes


@pytest.mark.parametrize("operation", ["version", "review_sheet", "review_stamp"])
def test_review_timeout_preserves_committed_bundles(tmp_path, monkeypatch, operation):
    source, config, templates, _ = prepare_inputs(tmp_path)
    record_path = run_pipeline(
        source,
        tmp_path / "runs",
        config_dir=config,
        notice_template=templates / "overdue_agents_v1.en.typ",
    )
    run_dir = record_path.parent
    record = json.loads(record_path.read_text())
    active = {
        path.name: path.read_bytes() for path in (run_dir / "bundles").rglob("*.pdf")
    }
    memberships = deepcopy(
        [(entry["routing"], entry["bundle"]) for entry in record["entries"]]
    )
    record["configuration"]["effective"]["typst"]["timeouts_seconds"][
        "version" if operation == "version" else "review"
    ] = VERSION_DEADLINE if operation == "version" else 5
    monkeypatch.setenv("TYPST_BIN", str(sleeping_compiler(tmp_path, operation)))
    run_report.write_report(run_dir, record)
    attempt = bundle_pdfs.bundle_run(
        run_dir,
        withhold=[entry["row_key"] for entry in record["entries"]],
    )
    record = json.loads(record_path.read_text())
    assert attempt["status"] == "failed"
    assert (tmp_path / "stalled-operation").read_text() == operation
    assert "deadline" in attempt["checks"][-1]["message"]
    assert [
        (entry["routing"], entry["bundle"]) for entry in record["entries"]
    ] == memberships
    assert {
        path.name: path.read_bytes() for path in (run_dir / "bundles").rglob("*.pdf")
    } == active
    assert not (run_dir / "bundles.next").exists()
    assert not (run_dir / "bundles.previous").exists()
    saved = json.loads(record_path.read_text())
    assert saved["delivery_attempts"][-1]["status"] == "failed"
