"""Individual encrypted copies preserve originals and require known password facts."""

from pathlib import Path

import pytest
import pikepdf
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject

from immuknow.encrypt_notices import encrypt_notice
from immuknow.load_config import validate_config
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
    details = encrypt_notice(
        client,
        original,
        encrypted,
        {"password": {"template": "{client_id}_{date_of_birth_iso_compact}"}},
    )
    reader = PdfReader(encrypted)
    assert details == {"algorithm": "AES-256", "revision": 6, "key_bits": 256}
    assert reader.is_encrypted
    profile = reader.trailer["/Encrypt"]
    assert isinstance(profile, DictionaryObject)
    assert (profile["/V"], profile["/R"], profile["/Length"]) == (5, 6, 256)
    assert profile.get("/CF", {}).get("/StdCF", {}).get("/CFM") == "/AESV3"
    assert not reader.decrypt("")
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
            {"password": {"template": "{client_id:private-test-value}"}},
        )
    assert "private-test-value" not in str(invalid_spec.value)
    assert not (tmp_path / "specifier.pdf").exists()


@pytest.mark.parametrize(
    "failure", ["write", "algorithm", "password", "page_count", "encrypted_source"]
)
def test_encryption_failure_preserves_original_and_existing_copy(
    tmp_path, monkeypatch, failure
):
    original, encrypted = tmp_path / "original.pdf", tmp_path / "encrypted.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    if failure == "encrypted_source":
        writer.encrypt("source-password", algorithm="AES-256")
    writer.write(original)
    content = original.read_bytes()
    encrypted.write_bytes(b"previous encrypted copy")
    save = pikepdf.Pdf.save

    def unavailable(self, *args, **kwargs):
        if failure == "write":
            Path(args[0]).write_bytes(b"partial output")
            raise OSError("Cannot write encrypted output")
        if failure == "password":
            raise ValueError("private-test-password")
        if failure == "algorithm":
            kwargs["encryption"] = pikepdf.Encryption(
                owner="private-test-password", user="private-test-password", R=4
            )
        if failure == "page_count":
            self.add_blank_page()
        return save(self, *args, **kwargs)

    monkeypatch.setattr(pikepdf.Pdf, "save", unavailable)
    with pytest.raises((OSError, ValueError)) as error:
        encrypt_notice(
            create_test_client_record(),
            original,
            encrypted,
            {"password": {"template": "private-test-password"}},
        )
    assert "private-test-password" not in str(error.value)
    assert original.read_bytes() == content
    assert encrypted.read_bytes() == b"previous encrypted copy"
    assert not list(tmp_path.glob("*.partial.pdf"))


def test_initials_in_password_and_missing_name(tmp_path: Path) -> None:
    original = tmp_path / "original.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(original)
    settings = {"password": {"template": "{first_initial}{last_initial}-123"}}
    validate_config({"encryption": {"enabled": True, **settings}})
    encrypted = tmp_path / "encrypted.pdf"
    encrypt_notice(
        create_test_client_record(first_name="  Élodie ", last_name=" o’Connor "),
        original,
        encrypted,
        settings,
    )
    assert PdfReader(encrypted).decrypt("Éo-123")
    with pytest.raises(ValueError, match="first_initial"):
        encrypt_notice(
            create_test_client_record(first_name="  ", last_name="Example"),
            original,
            tmp_path / "missing.pdf",
            settings,
        )
    assert not (tmp_path / "missing.pdf").exists()
