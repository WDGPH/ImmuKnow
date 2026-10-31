"""CLI selection, inline assignment documentation and host logging isolation."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from immuknow import orchestrator


def test_import_does_not_configure_host_logging(tmp_path: Path) -> None:
    script = "import logging; root=logging.getLogger(); before=(root.level,tuple(root.handlers)); import immuknow.orchestrator; assert (root.level,tuple(root.handlers))==before"
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=tmp_path, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("selector", ["--template", "--notice-assignments"])
def test_cli_selection(selector: str) -> None:
    with patch("sys.argv", ["immuknow", "students.csv", selector, "selection"]):
        args = orchestrator.parse_args()
    assert args.input_file == Path("students.csv")
    assert (args.notice_template is None) != (args.notice_assignments is None)


@pytest.mark.parametrize(
    "selection", [[], ["--template", "a.en.typ", "--notice-assignments", "a.json"]]
)
def test_cli_requires_one_selector(selection: list[str]) -> None:
    with (
        patch("sys.argv", ["immuknow", "students.csv", *selection]),
        pytest.raises(SystemExit) as failure,
    ):
        orchestrator.parse_args()
    assert failure.value.code == 2


def test_help_has_parseable_assignment_example(capsys: pytest.CaptureFixture) -> None:
    with (
        patch("sys.argv", ["immuknow", "--help"]),
        pytest.raises(SystemExit) as success,
    ):
        orchestrator.parse_args()
    assert success.value.code == 0
    help_text = capsys.readouterr().out
    example = help_text.split("assignments.json is a UTF-8 JSON array:\n", 1)[1].split(
        "\n\n", 1
    )[0]
    assert json.loads(example)[1]["experiment_arm"] == "B"
    assert "one unambiguous assignment" in help_text
    assert "--templates ./templates --output ./runs" in help_text
    assert "filenames inside --templates, not paths" in help_text


def test_run_logging_preserves_host_handlers(tmp_path: Path) -> None:
    logger = logging.getLogger("immuknow")
    before = logger.level, tuple(logger.handlers)
    with pytest.raises(ValueError), orchestrator.run_logging(tmp_path / "run.log"):
        raise ValueError("deliberate failure")
    assert (logger.level, tuple(logger.handlers)) == before
    assert "Run failed" in (tmp_path / "run.log").read_text()
