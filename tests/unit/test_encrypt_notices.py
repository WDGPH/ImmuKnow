"""Individual encrypted copies preserve originals and require known password facts."""

from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from immuknow.encrypt_notices import encrypt_notice
from tests.fixtures.sample_input import create_test_client_record


def test_encryption_verifies_password_and_preserves_original(tmp_path: Path) -> None:
    original, encrypted = tmp_path / "original.pdf", tmp_path / "encrypted.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_metadata({"/Title": "Original notice"})
    with original.open("wb") as stream:
        writer.write(stream)
    content = original.read_bytes()
    client = create_test_client_record()
    encrypt_notice(
        client,
        original,
        encrypted,
        {"password": {"template": "{client_id}_{date_of_birth_iso_compact}"}},
    )
    reader = PdfReader(encrypted)
    assert reader.is_encrypted
    assert not reader.decrypt("20150102")
    assert reader.decrypt("0000000001_20150102")
    assert len(reader.pages) == 1
    assert reader.metadata is not None
    assert reader.metadata.title == "Original notice"
    assert original.read_bytes() == content
    with pytest.raises(ValueError, match="unavailable"):
        encrypt_notice(
            create_test_client_record(date_of_birth=""),
            original,
            tmp_path / "missing.pdf",
            {"password": {"template": "Prefix-{date_of_birth_iso_compact}"}},
        )
    assert not (tmp_path / "missing.pdf").exists()
    with pytest.raises(ValueError, match="must not be empty"):
        encrypt_notice(
            client, original, tmp_path / "empty.pdf", {"password": {"template": " "}}
        )
    assert not (tmp_path / "empty.pdf").exists()
    with pytest.raises(ValueError, match="Invalid password template"):
        encrypt_notice(
            client,
            original,
            tmp_path / "typo.pdf",
            {"password": {"template": "{client_ID}"}},
        )
    assert not (tmp_path / "typo.pdf").exists()

    with pytest.raises(ValueError) as invalid_spec:
        encrypt_notice(
            client,
            original,
            tmp_path / "specifier.pdf",
            {"password": {"template": "{client_id:synthetic-secret}"}},
        )
    assert "synthetic-secret" not in str(invalid_spec.value)
    assert not (tmp_path / "specifier.pdf").exists()
