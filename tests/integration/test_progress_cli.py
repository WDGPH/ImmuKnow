"""CLI progress is useful in captured output and can be disabled independently."""

import json

import pytest

from tests.integration.test_native_pipeline import prepare_cohort, run_cli

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("show_progress", [True, False])
def test_cli_progress_and_timings_preserve_complete_outputs(tmp_path, show_progress):
    command, output, _ = prepare_cohort(tmp_path, encrypted=True)
    command += ["--workers", "2"]
    if not show_progress:
        command.append("--no-progress")
    result = run_cli(command, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "original PDFs" in result.stdout
    if show_progress:
        for stage in ("Rendering", "Encryption", "Delivery"):
            assert f"{stage} started" in result.stderr
            assert f"{stage} finished" in result.stderr
        assert "2/2 completed, 0 failed" in result.stderr
        assert "\r" not in result.stderr and "\x1b" not in result.stderr
        assert "0000000001" not in result.stderr
        assert "0000000002" not in result.stderr
        assert "Alice" not in result.stderr and "Benoit" not in result.stderr
    else:
        assert result.stderr == ""
    (saved,) = output.glob("*/run.json")
    record = json.loads(saved.read_text())
    assert all(
        entry["original"]["status"] == "completed" for entry in record["entries"]
    )
    assert all(
        entry["encryption"]["status"] == "completed" for entry in record["entries"]
    )
    log = (saved.parent / "logs/run.log").read_text()
    for stage in ("Rendering", "Encryption", "Delivery"):
        assert f"{stage} finished" in log
    assert "Report checkpoint took" in log
