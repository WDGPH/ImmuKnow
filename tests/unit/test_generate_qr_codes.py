"""QR images and payloads produced from canonical clients."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from immuknow.generate_qr_codes import encode_qr_payload_url, generate_qr_codes
from tests.fixtures.sample_input import create_test_client_record

pytestmark = pytest.mark.unit


def client(client_id: str, sequence: str, language: str):
    record = create_test_client_record(client_id=client_id)
    return replace(
        record,
        sequence=sequence,
        language=language,
        person={
            **record.person,
            "first_name": "François",
            "date_of_birth_iso": "2015-03-15",
        },
    )


def test_qr_payload_keeps_url_structure_and_encodes_values() -> None:
    assert encode_qr_payload_url(
        "https://example.ca/update?name=François Smith&dob=2015-03-15&flag"
    ) == ("https://example.ca/update?name=Fran%C3%A7ois%20Smith&dob=2015-03-15&flag")


def test_qr_generation_returns_updated_clients_and_real_png(tmp_path: Path) -> None:
    clients = [client("C001", "00001", "fr"), client("C002", "00002", "en")]
    config = {
        "qr": {
            "enabled": True,
            "payload_template": (
                "https://example.ca/update?id={client_id}&name={first_name}"
                "&dob={date_of_birth_iso}&compact={date_of_birth_iso_compact}&lang={language_code}"
            ),
        }
    }

    updated, paths = generate_qr_codes(clients, tmp_path, config)

    assert len(paths) == len(updated) == 2
    assert [p.name for p in paths] == [
        "qr_code_00001_C001.png",
        "qr_code_00002_C002.png",
    ]
    assert updated[0].qr is not None
    assert updated[0].qr["payload"] == (
        "https://example.ca/update?id=C001&name=Fran%C3%A7ois"
        "&dob=2015-03-15&compact=20150315&lang=fr"
    )
    assert updated[1].qr is not None
    assert updated[1].qr["payload"].endswith("lang=en")
    assert clients[0].qr is None
    for path in paths:
        with Image.open(path) as png:
            png.verify()


def test_disabled_qr_does_not_write_images(tmp_path: Path) -> None:
    clients = [client("C001", "00001", "en")]
    updated, paths = generate_qr_codes(clients, tmp_path, {"qr": {"enabled": False}})
    assert updated == clients
    assert paths == []
    assert not (tmp_path / "qr_codes").exists()


def test_qr_failure_preserves_record_and_other_clients(
    tmp_path: Path, monkeypatch
) -> None:
    from immuknow import generate_qr_codes as qr_module

    real_generate = qr_module.generate_qr_code

    def fail_one(data: str, output_dir: Path, *, filename: str | None = None) -> Path:
        if "id=C001" in data:
            raise RuntimeError("QR image could not be created")
        return real_generate(data, output_dir, filename=filename)

    monkeypatch.setattr(qr_module, "generate_qr_code", fail_one)
    clients = [client("C001", "00001", "en"), client("C002", "00002", "fr")]
    updated, paths = generate_qr_codes(
        clients,
        tmp_path,
        {
            "qr": {
                "enabled": True,
                "payload_template": "https://example.ca/?id={client_id}",
            }
        },
    )
    assert updated[0].qr is None
    assert updated[1].qr is not None
    assert [path.name for path in paths] == ["qr_code_00002_C002.png"]
