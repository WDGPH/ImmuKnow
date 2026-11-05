"""Coordinator stops submitting on fatal worker failures and drains in-flight work."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event

import pytest

from immuknow import encrypt_notices
from immuknow.client_placeholders import build_client_context
from tests.fixtures.sample_input import create_test_client_record


def test_fatal_failure_drains_already_submitted_jobs(
    monkeypatch, tmp_path: Path
) -> None:
    release = Event()
    running = Event()
    submitted = []
    incorporated = []

    def encrypt(client, source, destination, settings):
        submitted.append(source.name)
        if source.name == "fail":
            assert running.wait(5)
            release.set()
            raise RuntimeError("unexpected worker failure")
        running.set()
        assert release.wait(5)
        destination.write_text("completed")
        return {"algorithm": "AES-256"}

    monkeypatch.setattr(encrypt_notices, "encrypt_notice", encrypt)
    monkeypatch.setattr(
        encrypt_notices,
        "ProcessPoolExecutor",
        lambda max_workers, mp_context: ThreadPoolExecutor(max_workers=max_workers),
    )
    client = create_test_client_record()
    tasks = [
        (client, tmp_path / name, tmp_path / (name + ".out"))
        for name in ("fail", "running", "never-submitted")
    ]
    with pytest.raises(RuntimeError, match="unexpected worker failure"):
        encrypt_notices.encrypt_many(
            tasks,
            {},
            2,
            lambda client, destination, details, error: incorporated.append(
                destination.name
            ),
        )
    assert set(submitted) == {"fail", "running"}
    assert incorporated == ["running.out"]
    assert (tmp_path / "running.out").exists()


def test_parallel_worker_receives_all_password_facts_without_history(
    monkeypatch, tmp_path
):
    client = replace(
        create_test_client_record(),
        history=[{"sensitive": "record"}],
        unparsed_history=["private"],
        overdue_agents=["agent"],
        overdue_diseases=[{"disease": "test"}],
        metadata={"private": "value"},
    )
    received = []

    def encrypt(reduced, source, destination, settings):
        received.append(reduced)
        return {"algorithm": "AES-256"}

    monkeypatch.setattr(encrypt_notices, "encrypt_notice", encrypt)
    monkeypatch.setattr(
        encrypt_notices,
        "ProcessPoolExecutor",
        lambda max_workers, mp_context: ThreadPoolExecutor(max_workers=max_workers),
    )
    encrypt_notices.encrypt_many(
        [(client, tmp_path / "source", tmp_path / "out")], {}, 2, lambda *args: None
    )
    assert build_client_context(received[0]) == build_client_context(client)
    assert not received[0].history and not received[0].unparsed_history
    assert not received[0].overdue_agents and not received[0].overdue_diseases
    assert not received[0].metadata
