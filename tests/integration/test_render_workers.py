"""Native runs retain row and delivery contracts with concurrent rendering."""

from __future__ import annotations

import json
import signal
import time
from concurrent.futures import ThreadPoolExecutor
import subprocess
import sys
from threading import Event, Lock, Thread

import pandas as pd
import pytest
from pypdf import PdfReader

from immuknow import compile_notices, orchestrator
from immuknow.orchestrator import run_pipeline
from immuknow.run_lock import run_lock
from tests.fixtures.sample_input import create_test_input_dataframe
from tests.integration.test_run_lock import paused_process
from tests.integration.test_run_accounting import prepare_inputs

pytestmark = pytest.mark.integration


def run_inputs(tmp_path, workers):
    tmp_path.mkdir(parents=True, exist_ok=True)
    source, config, templates, assignments = prepare_inputs(tmp_path)
    return run_pipeline(
        source,
        tmp_path / "runs",
        config_dir=config,
        template_dir=templates,
        notice_assignments=assignments,
        workers=workers,
    )


def text_of(path):
    return [page.extract_text() for page in PdfReader(path).pages]


def test_concurrent_rendering_preserves_native_outputs_and_row_association(
    tmp_path, monkeypatch
):
    serial = run_inputs(tmp_path / "serial", 1)
    original_compile = compile_notices.compile_render_job
    second_finished = Event()
    active_lock = Lock()
    active = 0
    maximum = 0
    completed = []

    def compile_job(job, *args, **kwargs):
        nonlocal active, maximum
        assert kwargs["jobs"] == 1
        with active_lock:
            active += 1
            maximum = max(maximum, active)
        try:
            # Force source row 2 to complete first, regardless of preparation order.
            if job.sequence == "row-000001":
                assert second_finished.wait(30)
            result = original_compile(job, *args, **kwargs)
            completed.append(job.sequence)
            if job.sequence == "row-000002":
                second_finished.set()
            return result
        finally:
            with active_lock:
                active -= 1

    monkeypatch.setattr(compile_notices, "compile_render_job", compile_job)
    concurrent = run_inputs(tmp_path / "concurrent", 2)
    assert completed == ["row-000002", "row-000001"]
    assert maximum == 2
    expected = json.loads(serial.read_text())
    actual = json.loads(concurrent.read_text())
    assert actual["status"] == expected["status"]
    assert [a["row_keys"] for a in actual["delivery_attempts"][0]["bundles"]] == [
        a["row_keys"] for a in expected["delivery_attempts"][0]["bundles"]
    ]
    for left, right in zip(expected["entries"], actual["entries"]):
        assert left["row_key"] == right["row_key"]
        assert left["assignment"] == right["assignment"]
        assert left["render_summary"] == right["render_summary"]
        assert left["checks"] == right["checks"]
        assert text_of(serial.parent / left["original"]["path"]) == text_of(
            concurrent.parent / right["original"]["path"]
        )
        assert right["client_id"] in " ".join(
            text_of(concurrent.parent / right["original"]["path"])
        )
        for field, excluded in (
            ("routing", {"accepted_tokens"}),
            ("bundle", {"path", "sha256"}),
        ):
            assert {k: v for k, v in left[field].items() if k not in excluded} == {
                k: v for k, v in right[field].items() if k not in excluded
            }


@pytest.mark.parametrize("operation", ["compile", "evidence", "evidence-oserror"])
def test_concurrent_expected_failure_retains_other_row(
    tmp_path, monkeypatch, operation
):
    original_compile = compile_notices.compile_render_job

    def compile_job(job, *args, **kwargs):
        if operation == "compile" and job.sequence == "row-000001":
            raise OSError("deliberate compilation failure")
        diagnostics, summary, error = original_compile(job, *args, **kwargs)
        if job.sequence == "row-000001":
            if operation == "evidence":
                return diagnostics, None, ValueError("deliberate evidence failure")
            if operation == "evidence-oserror":
                return diagnostics, None, OSError("deliberate evidence read failure")
        return diagnostics, summary, error

    monkeypatch.setattr(compile_notices, "compile_render_job", compile_job)
    record_path = run_inputs(tmp_path, 2)
    record = json.loads(record_path.read_text())
    first, second = record["entries"]
    assert record["status"] == "completed_with_failures"
    assert second["original"]["status"] == "completed"
    if operation == "compile":
        assert first["original"]["status"] == "failed"
        assert first["bundle"] is None
    else:
        assert first["original"]["status"] == "completed"
        assert PdfReader(record_path.parent / first["original"]["path"]).pages
        assert any(c["code"] == "render.evidence_failed" for c in first["checks"])
        assert first["routing"]["destination"] == "review"


def test_rejected_input_never_starts_workers(tmp_path, monkeypatch):
    source, config, templates, assignments = prepare_inputs(tmp_path)
    # Duplicate identifiers reject the whole cohort at preflight.
    frame = pd.read_csv(source, dtype=str, keep_default_na=False)
    frame.loc[1, "client_id"] = frame.loc[0, "client_id"]
    frame.to_csv(source, index=False)

    def unexpected(*args, **kwargs):
        pytest.fail("Rendering started for rejected input")

    monkeypatch.setattr(compile_notices, "compile_render_job", unexpected)
    path = run_pipeline(
        source,
        tmp_path / "runs",
        config_dir=config,
        template_dir=templates,
        notice_assignments=assignments,
        workers=2,
    )
    record = json.loads(path.read_text())
    assert not record["input"]["accepted"]
    assert not record["delivery_attempts"]
    assert all(e["original"]["status"] == "not_run" for e in record["entries"])


@pytest.mark.parametrize("workers", ["0", "-1", "not-a-number"])
def test_cli_rejects_invalid_worker_count_before_running(tmp_path, workers):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "immuknow.orchestrator",
            "missing.csv",
            "--workers",
            workers,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "workers" in result.stderr.lower()
    assert not list(tmp_path.glob("*/run.json"))


@pytest.mark.parametrize("failure_stage", ["compilation", "evidence"])
def test_unexpected_worker_failure_drains_active_work_and_saves_accounting(
    tmp_path, monkeypatch, failure_stage
):
    original_compile = compile_notices.compile_render_job
    other_started = Event()

    def compile_job(job, *args, **kwargs):
        if job.sequence == "row-000001":
            assert other_started.wait(30)
            error = RuntimeError("deliberate unexpected worker failure")
            if failure_stage == "evidence":
                diagnostics, _, _ = original_compile(job, *args, **kwargs)
                return diagnostics, None, error
            raise error
        other_started.set()
        return original_compile(job, *args, **kwargs)

    monkeypatch.setattr(compile_notices, "compile_render_job", compile_job)
    with pytest.raises(RuntimeError, match="deliberate unexpected worker failure"):
        run_inputs(tmp_path, 2)
    (record_path,) = (tmp_path / "runs").glob("*/run.json")
    record = json.loads(record_path.read_text())
    first, second = record["entries"]
    assert record["status"] == "completed_with_failures"
    assert first["original"]["status"] == (
        "completed" if failure_stage == "evidence" else "failed"
    )
    if failure_stage == "evidence":
        assert any(c["code"] == "render.evidence_failed" for c in first["checks"])
    assert second["original"]["status"] == "completed"
    assert second["render_summary"]
    assert not record["delivery_attempts"]
    assert any("deliberate unexpected" in c["message"] for c in record["checks"])


INTERRUPT_SCRIPT = """
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from immuknow import compile_notices, orchestrator
marker, source, config, templates, assignments, runs = map(Path, sys.argv[1:])
started = Event()
compile_job = compile_notices.compile_render_job
class Executor(ThreadPoolExecutor):
    def shutdown(self, *args, **kwargs):
        marker.with_suffix(".draining").touch()
        return super().shutdown(*args, **kwargs)
def compile_one(job, *args, **kwargs):
    if job.sequence == "row-000001":
        started.set()
        sys.stdin.readline()
    result = compile_job(job, *args, **kwargs)
    if job.sequence == "row-000002":
        assert started.wait(30)
        marker.touch()
    return result
orchestrator.ThreadPoolExecutor = Executor
compile_notices.compile_render_job = compile_one
try:
    orchestrator.run_pipeline(source, runs, config_dir=config, template_dir=templates,
                              notice_assignments=assignments, workers=2)
except KeyboardInterrupt:
    pass
else:
    raise AssertionError("Expected KeyboardInterrupt")
"""


@pytest.mark.skipif(
    sys.platform == "win32", reason="SIGINT delivery differs on Windows"
)
def test_parent_interrupt_drains_worker_and_saves_partial_accounting(tmp_path):
    source, config, templates, assignments = prepare_inputs(tmp_path)
    with paused_process(
        tmp_path,
        INTERRUPT_SCRIPT,
        source,
        config,
        templates,
        assignments,
        tmp_path / "runs",
    ) as process:
        process.send_signal(signal.SIGINT)
        deadline = time.monotonic() + 30
        while not (tmp_path / "child-ready.draining").exists():
            assert process.poll() is None, (tmp_path / "child.log").read_text()
            assert time.monotonic() < deadline
            time.sleep(0.02)
        (run_dir,) = (tmp_path / "runs").iterdir()
        with pytest.raises(ValueError, match="This run is in use"):
            with run_lock(run_dir):
                pytest.fail("Run lock was released before interrupted workers drained")
        process.communicate("continue\n", timeout=30)
        assert process.returncode == 0, (tmp_path / "child.log").read_text()
    record = json.loads((run_dir / "run.json").read_text())
    assert record["status"] != "running"
    assert all(e["original"]["status"] != "not_run" for e in record["entries"])
    assert any(e["original"]["status"] == "completed" for e in record["entries"])
    assert not record["delivery_attempts"]


def test_failure_drains_with_run_locked_and_limits_submissions(tmp_path, monkeypatch):
    source, config, templates, assignments = prepare_inputs(tmp_path)
    frame = create_test_input_dataframe(num_clients=4)
    frame.to_csv(source, index=False)
    assignments.write_text(
        json.dumps(
            [
                {"client_id": client_id, "template": "overdue_agents_v1.en.typ"}
                for client_id in frame["client_id"]
            ]
        )
    )
    original_compile = compile_notices.compile_render_job
    both_started = Event()
    release = Event()
    draining = Event()
    submit_count = 0
    active_count = 0
    started_lock = Lock()
    errors = []

    class ObservedExecutor(ThreadPoolExecutor):
        def submit(self, *args, **kwargs):
            nonlocal submit_count
            submit_count += 1
            return super().submit(*args, **kwargs)

        def shutdown(self, *args, **kwargs):
            draining.set()
            return super().shutdown(*args, **kwargs)

    def compile_job(job, *args, **kwargs):
        nonlocal active_count
        with started_lock:
            active_count += 1
            if active_count == 2:
                both_started.set()
            rank = active_count
        assert both_started.wait(30)
        if rank == 1:
            raise RuntimeError("deliberate worker failure")
        assert release.wait(30)
        return original_compile(job, *args, **kwargs)

    def pipeline():
        try:
            run_pipeline(
                source,
                tmp_path / "runs",
                config_dir=config,
                template_dir=templates,
                notice_assignments=assignments,
                workers=2,
            )
        except BaseException as exc:
            errors.append(exc)

    monkeypatch.setattr(orchestrator, "ThreadPoolExecutor", ObservedExecutor)
    monkeypatch.setattr(compile_notices, "compile_render_job", compile_job)
    thread = Thread(target=pipeline)
    thread.start()
    try:
        assert draining.wait(30)
        assert submit_count == 2
        (run_dir,) = (tmp_path / "runs").iterdir()
        with pytest.raises(ValueError, match="This run is in use"):
            with run_lock(run_dir):
                pytest.fail("Run lock was released before workers drained")
    finally:
        release.set()
        thread.join(timeout=30)
    assert not thread.is_alive()
    assert len(errors) == 1
    assert isinstance(errors[0], RuntimeError)
    assert "deliberate worker failure" in str(errors[0])
    record = json.loads((run_dir / "run.json").read_text())
    assert not record["delivery_attempts"]
    assert sum(e["original"]["status"] == "completed" for e in record["entries"]) == 1
    assert all(e["original"]["status"] != "not_run" for e in record["entries"])
    with run_lock(run_dir):
        pass
