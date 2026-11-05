"""Encryption workers publish verified copies and report independent failures."""

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

from pypdf import PdfReader, PdfWriter
from pypdf.generic import BooleanObject, DictionaryObject, NameObject, TextStringObject

from immuknow import run_report
from immuknow.client_placeholders import CLIENT_PLACEHOLDERS, build_client_context
from immuknow.encrypt_notices import encrypt_many
from immuknow.orchestrator import run_pipeline
from immuknow.run_lock import run_lock
from tests.integration.test_run_accounting import prepare_inputs
from tests.fixtures.sample_input import create_test_client_record

pytestmark = pytest.mark.integration


def test_spawned_encryption_continues_after_bad_source(tmp_path: Path) -> None:
    source = tmp_path / "original.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=120, height=160)
    writer.write(source)
    before = source.read_bytes()
    client = create_test_client_record()
    outputs = [tmp_path / f"encrypted-{i}.pdf" for i in range(3)]
    tasks = [
        (client, source, outputs[0]),
        (client, tmp_path / "missing.pdf", outputs[1]),
        (client, source, outputs[2]),
    ]
    outcomes = []
    encrypt_many(
        tasks,
        {"password": {"template": "{date_of_birth_iso_compact}"}},
        2,
        lambda client, destination, details, error: outcomes.append(
            (destination, details, error)
        ),
    )
    assert len(outcomes) == 3
    assert {path for path, details, error in outcomes if error is None} == {
        outputs[0],
        outputs[2],
    }
    assert {path for path, details, error in outcomes if error is not None} == {
        outputs[1]
    }
    assert source.read_bytes() == before
    password = client.person["date_of_birth_iso"].replace("-", "")
    for output in (outputs[0], outputs[2]):
        reader = PdfReader(output)
        assert (
            reader.is_encrypted and not reader.decrypt("") and reader.decrypt(password)
        )
        assert len(reader.pages) == 1
    assert not outputs[1].exists()


def test_spawned_workers_support_non_dob_password_facts_and_missing_dob(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=120, height=160)
    writer.write(source)
    client = create_test_client_record()
    context = build_client_context(client)
    fields = sorted(
        CLIENT_PLACEHOLDERS - {"date_of_birth_iso", "date_of_birth_iso_compact"}
    )
    assert all(context[field] for field in fields)
    template = "|".join("{" + field + "}" for field in fields)
    missing = replace(client, person={**client.person, "date_of_birth_iso": ""})
    results = []
    encrypt_many(
        [
            (client, source, tmp_path / "valid.pdf"),
            (missing, source, tmp_path / "missing.pdf"),
        ],
        {"password": {"template": template + "|{date_of_birth_iso}"}},
        2,
        lambda client, destination, details, error: results.append(
            (destination, error)
        ),
    )
    assert (
        next(error for path, error in results if path.name == "missing.pdf") is not None
    )
    assert not (tmp_path / "missing.pdf").exists()
    reader = PdfReader(tmp_path / "valid.pdf")
    assert reader.decrypt(
        "|".join(context[field] for field in fields)
        + "|"
        + context["date_of_birth_iso"]
    )


def test_encrypted_copy_preserves_document_metadata_and_attachments(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=120, height=160)
    writer.add_metadata({"/Title": "Fixture title"})
    writer.add_attachment("details.txt", b"fixture attachment")
    writer._root_object[NameObject("/MarkInfo")] = DictionaryObject(
        {
            NameObject("/Marked"): BooleanObject(True),
        }
    )
    writer._root_object[NameObject("/Lang")] = TextStringObject("fr-CA")
    writer.write(source)
    original = source.read_bytes()
    client = create_test_client_record()
    output = tmp_path / "encrypted.pdf"
    results = []
    encrypt_many(
        [(client, source, output)],
        {"password": {"template": "test-password"}},
        2,
        lambda *result: results.append(result),
    )
    assert results[0][-1] is None
    encrypted = PdfReader(output)
    assert encrypted.decrypt("test-password")
    assert encrypted.metadata is not None
    assert encrypted.metadata.title == "Fixture title"
    assert encrypted.attachments["details.txt"] == [b"fixture attachment"]
    assert encrypted.root_object["/Lang"] == "fr-CA"
    assert encrypted.root_object["/MarkInfo"]["/Marked"]
    assert source.read_bytes() == original


@pytest.mark.parametrize("workers", [1, 2])
def test_coordinator_records_artifact_errors_and_continues(
    tmp_path, monkeypatch, workers
):
    source, config, templates, _ = prepare_inputs(tmp_path)
    artifact = run_report.artifact_record
    advance = run_report._OutcomeCheckpoint.advance
    coordinator = os.getpid()
    calls = []

    def fail_one(path, run_dir):
        if path.name == "row-000001.pdf" and path.parent.name == "encrypted":
            raise OSError("Cannot record encrypted artifact")
        return artifact(path, run_dir)

    def checkpoint(self):
        calls.append(os.getpid())
        return advance(self)

    monkeypatch.setattr(run_report, "artifact_record", fail_one)
    monkeypatch.setattr(run_report._OutcomeCheckpoint, "advance", checkpoint)
    saved = run_pipeline(
        source,
        tmp_path / "runs",
        config_dir=config,
        notice_template=templates / "overdue_agents_v1.en.typ",
        workers=workers,
    )
    first, second = json.loads(saved.read_text())["entries"]
    assert first["encryption"]["status"] == "failed"
    assert any(
        check["code"] == "encryption.failed"
        and "Cannot record encrypted artifact" in check["message"]
        for check in first["checks"]
    )
    assert second["encryption"]["status"] == "completed"
    assert (saved.parent / second["encryption"]["path"]).exists()
    assert len(calls) >= 4 and set(calls) == {coordinator}


def test_sigint_waits_for_spawned_workers_before_releasing_lock(tmp_path: Path) -> None:
    script = tmp_path / "interrupt.py"
    script.write_text("""
import signal, sys, time
from pathlib import Path

from immuknow.data_models import ClientRecord
from immuknow.run_lock import run_lock

work = Path(sys.argv[1])

def slow(client, source, destination, settings):
    (work / (destination.name + ".started")).write_text("started")
    deadline = time.monotonic() + 30
    while not (work / "release").exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("worker was not released")
        time.sleep(0.01)
    try:
        with run_lock(work):
            raise AssertionError("run lock was released before publication")
    except ValueError as error:
        if "in use" not in str(error):
            raise
    (work / (destination.name + ".lock-held")).write_text("held")
    destination.write_text("finished")
    return {}

if __name__ == "__main__":
    from immuknow import encrypt_notices
    encrypt_notices.encrypt_notice = slow
    client = ClientRecord("row", "client", "en", {}, {}, {}, {}, [], [], {})
    tasks = [(client, work / str(i), work / (str(i) + ".out")) for i in range(8)]
    def interrupt(signum, frame):
        (work / "interrupted").write_text("received")
        raise KeyboardInterrupt
    signal.signal(signal.SIGINT, interrupt)
    with run_lock(work):
        (work / "coordinator-locked").touch()
        try:
            encrypt_notices.encrypt_many(tasks, {}, 2, lambda *args: None)
        except KeyboardInterrupt:
            (work / "returned").write_text("done")
""")
    env = dict(
        os.environ,
        PYTHONPATH=str(Path(__file__).resolve().parents[2]),
    )
    output = tmp_path / "child-output.txt"
    with output.open("w") as errors:
        process = subprocess.Popen(
            [sys.executable, str(script), str(tmp_path)],
            env=env,
            stdout=errors,
            stderr=errors,
            start_new_session=True,
        )

    def diagnostics() -> str:
        return f"exit: {process.poll()}; child output:\n{output.read_text()}"

    try:
        # Coverage makes the coordinator's pypdf import slow on Python 3.12.
        deadline = time.monotonic() + 60
        while (
            not (tmp_path / "coordinator-locked").exists()
            and time.monotonic() < deadline
        ):
            assert process.poll() is None, diagnostics()
            time.sleep(0.05)
        assert (tmp_path / "coordinator-locked").exists(), diagnostics()
        deadline = time.monotonic() + 20
        while not list(tmp_path.glob("*.started")) and time.monotonic() < deadline:
            assert process.poll() is None, diagnostics()
            time.sleep(0.05)
        assert list(tmp_path.glob("*.started")), diagnostics()
        process.send_signal(signal.SIGINT)
        deadline = time.monotonic() + 20
        while not (tmp_path / "interrupted").exists() and time.monotonic() < deadline:
            assert process.poll() is None
            time.sleep(0.05)
        assert (tmp_path / "interrupted").exists()
        assert process.poll() is None
        with pytest.raises(ValueError, match="in use"):
            with run_lock(tmp_path):
                pass
        (tmp_path / "release").write_text("release")
        assert process.wait(timeout=20) == 0
        assert (tmp_path / "returned").exists()
        with run_lock(tmp_path):
            snapshot = {p.name: p.read_bytes() for p in tmp_path.glob("*.out")}
            assert snapshot
            assert {
                p.name.removesuffix(".started") for p in tmp_path.glob("*.started")
            } == set(snapshot)
            assert all((tmp_path / (name + ".lock-held")).exists() for name in snapshot)
            time.sleep(0.5)
            assert {p.name: p.read_bytes() for p in tmp_path.glob("*.out")} == snapshot
        assert len(list(tmp_path.glob("*.started"))) <= 2
    finally:
        (tmp_path / "release").touch()
        # Clean up the whole process group if startup or an assertion fails.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
