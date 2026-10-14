"""Small CLI boundary checks complement the run-accounting and package journeys."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from tests.fixtures.sample_input import create_test_input_dataframe

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


def prepare_cohort(
    tmp_path: Path,
    languages: tuple[str, ...] = ("en", "fr"),
    group_by: str | None = None,
    encrypted: bool = False,
) -> tuple[list[str], Path, Path]:
    """Create original CSV and explicit filename assignments for an external CLI run."""
    config_dir = tmp_path / "Configuration été"
    shutil.copytree(ROOT / "immuknow/config", config_dir)
    config_path = config_dir / "parameters.yaml"
    config = yaml.safe_load(config_path.read_text())
    config["bundling"] = {"bundle_size": 10, "group_by": group_by}
    config["encryption"]["enabled"] = encrypted
    config_path.write_text(yaml.safe_dump(config))
    frame = create_test_input_dataframe(num_clients=len(languages))
    frame["overdue_disease"] = "Measles - 2"
    source = tmp_path / "Élèves synthétiques.csv"
    frame.to_csv(source, index=False)
    assignments = tmp_path / "Assignments.json"
    assignments.write_text(
        json.dumps(
            [
                {"client_id": cid, "template": f"overdue_agents_v1.{language}.typ"}
                for cid, language in zip(frame["client_id"], languages)
            ]
        )
    )
    output = tmp_path / "Notices été"
    command = [
        sys.executable,
        "-m",
        "immuknow.orchestrator",
        str(source),
        "--output",
        str(output),
        "--config",
        str(config_dir),
        "--notice-assignments",
        str(assignments),
    ]
    return command, output, config_dir


def run_cli(command: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Use the checkout under test while the process runs in an unrelated directory."""
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
    )


def test_cli_missing_assignment_template_saves_failed_setup(tmp_path: Path):
    command, output, _ = prepare_cohort(tmp_path, ("en",))
    path = Path(command[command.index("--notice-assignments") + 1])
    path.write_text('[{"client_id":"0000000001"}]')
    result = run_cli(command, tmp_path)
    assert result.returncode == 1
    record = json.loads(next(output.glob("*/run.json")).read_text())
    assert record["status"] == "failed_setup"
    assert len(record["entries"]) == 1
    assert record["entries"][0]["source"]["values"]["client_id"] == "0000000001"
    assert record["entries"][0]["original"]["status"] == "not_run"
    assert not list(output.rglob("*.pdf"))


def test_cli_invalid_filename_retains_prior_runs_and_accounts_for_failed_row(
    tmp_path: Path,
):
    command, output, _ = prepare_cohort(tmp_path, ("en",))
    path = Path(command[command.index("--notice-assignments") + 1])
    path.write_text('[{"client_id":"0000000001","template":"../outside.en.typ"}]')
    output.mkdir()
    sentinel = output / "prior.txt"
    sentinel.write_text("preserve")
    result = run_cli(command, tmp_path)
    assert result.returncode == 1
    assert sentinel.read_text() == "preserve"
    record = json.loads(next(output.glob("*/run.json")).read_text())
    entry = record["entries"][0]
    assert entry["assignment"]["template"] == "../outside.en.typ"
    assert any(
        c["code"] == "assignment.missing_template" and c["status"] == "fail"
        for c in entry["checks"]
    )
    assert record["status"] == "rejected_input"
    assert entry["original"]["status"] == "not_run"
    assert not list(output.rglob("*.pdf"))
