"""Competing processes must preserve saved decisions, bundles and recovery state."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import pytest
import yaml

from immuknow.orchestrator import run_pipeline
from tests.fixtures.sample_input import create_test_input_dataframe

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


def prepare_inputs(tmp_path):
    config = tmp_path / "config"
    shutil.copytree(ROOT / "immuknow/config", config)
    parameters = yaml.safe_load((config / "parameters.yaml").read_text())
    parameters["encryption"]["enabled"] = False
    parameters["bundling"] = {"bundle_size": 10}
    (config / "parameters.yaml").write_text(yaml.safe_dump(parameters))
    source = tmp_path / "clients.csv"
    frame = create_test_input_dataframe(num_clients=1)
    frame["overdue_disease"] = "Measles - 2"
    frame["overdue_agent"] = "M"
    frame.to_csv(source, index=False)
    return source, config, ROOT / "immuknow/templates/overdue_diseases_v1.en.typ"


@pytest.fixture
def saved_run(tmp_path):
    source, config, template = prepare_inputs(tmp_path)
    return run_pipeline(
        source, tmp_path / "runs", config_dir=config, notice_template=template
    ).parent


@contextmanager
def paused_process(tmp_path, script, *args):
    """Wait for an explicit child checkpoint, with bounded waits and cleanup."""
    marker = tmp_path / "child-ready"
    log = tmp_path / "child.log"
    with log.open("w") as output:
        process = subprocess.Popen(
            [sys.executable, "-u", "-c", script, str(marker), *map(str, args)],
            stdin=subprocess.PIPE,
            stdout=output,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            deadline = time.monotonic() + 30
            while not marker.exists():
                assert process.poll() is None, log.read_text()
                assert time.monotonic() < deadline, log.read_text()
                time.sleep(0.02)
            yield process
        finally:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
            assert process.stdin is not None
            process.stdin.close()


def rebundle(run_dir, *args):
    return subprocess.run(
        [sys.executable, "-m", "immuknow.rebundle", str(run_dir), *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


def read_record(run_dir):
    return json.loads((run_dir / "run.json").read_text())


def bundles(run_dir):
    return {
        str(path.relative_to(run_dir)): path.read_bytes()
        for path in (run_dir / "bundles").rglob("*.pdf")
    }


ASSEMBLY_PAUSE = """
import sys
from pathlib import Path
from unittest.mock import patch
from immuknow import bundle_pdfs
marker, run_dir, fail = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
assemble = bundle_pdfs._assemble
def pause(*args, **kwargs):
    marker.touch()
    sys.stdin.readline()
    if fail == "yes":
        raise ValueError("Deliberate assembly failure")
    return assemble(*args, **kwargs)
with patch.object(bundle_pdfs, "_assemble", pause):
    result = bundle_pdfs.bundle_run(run_dir, withhold=["row-000001"])
assert result["status"] == ("failed" if fail == "yes" else "completed")
"""


@pytest.mark.parametrize("fail", ["no", "yes"])
def test_competing_delivery_refuses_busy_run_and_releases_after_completion(
    tmp_path, saved_run, fail
):
    other = tmp_path / "other-run"
    shutil.copytree(saved_run, other)
    initial = read_record(saved_run)
    with paused_process(tmp_path, ASSEMBLY_PAUSE, saved_run, fail) as process:
        before = (saved_run / "run.json").read_bytes()
        active = bundles(saved_run)
        blocked = rebundle(saved_run, "--clear-withheld")
        assert blocked.returncode == 1
        assert "This run is in use" in blocked.stderr
        assert (saved_run / "run.json").read_bytes() == before
        assert bundles(saved_run) == active
        # A different directory has its own lock and can finish now.
        independent = rebundle(other)
        assert independent.returncode == 0, independent.stderr
        assert process.poll() is None
        process.communicate("continue\n", timeout=30)
        assert process.returncode == 0, (tmp_path / "child.log").read_text()

    current = read_record(saved_run)
    assert len(current["delivery_attempts"]) == len(initial["delivery_attempts"]) + 1
    if fail == "no":
        assert current["withheld_rows"] == ["row-000001"]
    # The next process reads the just-committed attempt and retains it unchanged.
    next_result = rebundle(saved_run, "--clear-withheld")
    assert next_result.returncode == 0, next_result.stderr
    final = read_record(saved_run)
    assert final["delivery_attempts"][:-1] == current["delivery_attempts"]
    assert final["delivery_attempts"][-1]["number"] == len(final["delivery_attempts"])
    assert final["withheld_rows"] == []


REPLACEMENT_PAUSE = """
import sys
from pathlib import Path
from unittest.mock import patch
from immuknow import bundle_pdfs, run_report
marker, run_dir, checkpoint = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
replace, write = Path.replace, run_report.write_report
def pause():
    marker.touch()
    sys.stdin.readline()
def swap(path, destination):
    if path.name == "bundles.next" and checkpoint == "before_replace":
        pause()
    result = replace(path, destination)
    if path.name == "bundles.next" and checkpoint == "after_replace":
        pause()
    return result
def report(path, record):
    result = write(path, record)
    if record["delivery_attempts"][-1]["status"] == "completed" and checkpoint == "after_commit":
        pause()
    return result
with patch.object(Path, "replace", swap), patch.object(run_report, "write_report", report):
    bundle_pdfs.bundle_run(run_dir, withhold=["row-000001"])
"""


@pytest.mark.parametrize(
    "checkpoint", ["before_replace", "after_replace", "after_commit"]
)
def test_killed_writer_releases_lock_and_next_delivery_recovers(
    tmp_path, saved_run, checkpoint
):
    original_record = read_record(saved_run)
    original_bundles = bundles(saved_run)
    with paused_process(tmp_path, REPLACEMENT_PAUSE, saved_run, checkpoint) as process:
        assert (saved_run / "bundles.previous").is_dir()
        paused = read_record(saved_run)
        committed_bundles = bundles(saved_run)
        process.kill()
        process.wait(timeout=10)

    # Refuse this new choice after recovery, so the recovered bundles remain visible.
    result = rebundle(
        saved_run, "--accept-warning", "unknown-warning-token", "--reason", "Reviewed"
    )
    assert result.returncode == 1
    assert "This run is in use" not in result.stderr
    recovered = read_record(saved_run)
    assert recovered["delivery_attempts"][-1]["status"] == "failed"
    prior = recovered["delivery_attempts"][-2]
    if checkpoint == "after_commit":
        assert prior == paused["delivery_attempts"][-1]
        assert prior["status"] == "completed"
        assert bundles(saved_run) == committed_bundles
        expected = paused
    else:
        assert prior["status"] == "failed"
        assert prior["checks"][-1]["code"] == "delivery.interrupted"
        assert bundles(saved_run) == original_bundles
        expected = original_record
    assert [entry["bundle"] for entry in recovered["entries"]] == [
        entry["bundle"] for entry in expected["entries"]
    ]
    assert not (saved_run / "bundles.previous").exists()
    assert not (saved_run / "bundles.next").exists()
    completed = rebundle(saved_run)
    assert completed.returncode == 0, completed.stderr


PIPELINE_PAUSE = """
import sys
from pathlib import Path
from unittest.mock import patch
from immuknow import run_report
from immuknow.orchestrator import run_pipeline
marker, source, config, template, runs = map(Path, sys.argv[1:6])
checkpoint = sys.argv[6]
write = run_report.write_report
completed_writes = 0
def report(path, record):
    global completed_writes
    result = write(path, record)
    attempts = record["delivery_attempts"]
    if attempts and attempts[-1]["status"] == "completed":
        completed_writes += 1
    if (checkpoint == "first_write" and not record["configuration"]) or (checkpoint == "final_write" and completed_writes == 2):
        marker.write_text(str(path))
        sys.stdin.readline()
    return result
with patch.object(run_report, "write_report", report):
    run_pipeline(source, runs, config_dir=config, notice_template=template)
"""


@pytest.mark.parametrize("checkpoint", ["first_write", "final_write"])
def test_new_run_is_locked_through_its_final_report(tmp_path, checkpoint):
    source, config, template = prepare_inputs(tmp_path)
    with paused_process(
        tmp_path,
        PIPELINE_PAUSE,
        source,
        config,
        template,
        tmp_path / "runs",
        checkpoint,
    ) as process:
        run_dir = Path((tmp_path / "child-ready").read_text())
        before = (run_dir / "run.json").read_bytes()
        result = rebundle(run_dir)
        assert result.returncode == 1
        assert "This run is in use" in result.stderr
        assert (run_dir / "run.json").read_bytes() == before
        process.communicate("continue\n", timeout=30)
        assert process.returncode == 0, (tmp_path / "child.log").read_text()
    result = rebundle(run_dir)
    assert result.returncode == 0, result.stderr
