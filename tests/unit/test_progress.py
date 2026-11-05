"""Progress presentation stays bounded and cannot turn notice work into a failure."""

from __future__ import annotations

import io
import logging

import pytest

from immuknow import progress
from immuknow.progress import StageProgress


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_terminal_counts_saved_outcomes_and_throttles_refresh(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(progress, "perf_counter", lambda: clock[0])
    output = Terminal()
    with StageProgress("Rendering notices", 2, stream=output) as stage:
        initial = output.getvalue()
        stage.advance()
        assert output.getvalue() == initial
        clock[0] = 0.5
        stage.refresh()
        assert "1/2 completed, 0 failed" in output.getvalue()
        stage.advance(failed=True)
    text = output.getvalue()
    assert text.count("\r") == 3
    assert "[====================]: 2/2 completed, 1 failed" in text
    assert text.endswith("\n")


def test_redirected_progress_has_only_stage_summaries():
    output = io.StringIO()
    with StageProgress("Encrypting notices", 3, stream=output) as stage:
        stage.advance()
        stage.advance(failed=True)
        stage.advance()
    lines = output.getvalue().splitlines()
    assert len(lines) == 2
    assert "Encrypting notices started: 0/3" in lines[0]
    assert "Encrypting notices finished: 3/3 completed, 1 failed" in lines[1]
    assert "\r" not in output.getvalue() and "\x1b" not in output.getvalue()


def test_silent_stages_still_log_elapsed_time(caplog):
    with caplog.at_level(logging.INFO, logger="immuknow.progress"):
        with StageProgress("Preparing delivery"):
            pass
    assert "Preparing delivery finished; elapsed" in caplog.text


def test_interruption_ends_terminal_line_and_keeps_partial_counts():
    output = Terminal()
    with pytest.raises(KeyboardInterrupt):
        with StageProgress("Rendering notices", 2, stream=output) as stage:
            stage.advance()
            raise KeyboardInterrupt
    assert "Rendering notices stopped" in output.getvalue()
    assert "1/2 completed" in output.getvalue()
    assert output.getvalue().endswith("\n")
    assert "finished" not in output.getvalue()


def test_broken_progress_output_does_not_mask_work_or_errors(caplog):
    class BrokenStream(io.StringIO):
        def write(self, value: str) -> int:
            raise BrokenPipeError("closed consumer")

    with pytest.raises(ValueError, match="actual work failed"):
        with StageProgress("Rendering notices", 1, stream=BrokenStream()) as stage:
            stage.advance()
            raise ValueError("actual work failed")
    assert stage.completed == 1
    assert caplog.text.count("Progress output is unavailable") == 1
