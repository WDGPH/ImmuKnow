"""A separate PDF implementation opens password-protected copies and preserves content."""

from pathlib import Path

import pymupdf
import pytest

from immuknow.encrypt_notices import encrypt_notice
from tests.fixtures.sample_input import create_test_client_record

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("password", ["Example-2026", "Été-2026-Чтение"])
def test_separate_reader_opens_aes_copy_with_correct_password(
    tmp_path: Path, password: str
) -> None:
    original, encrypted = tmp_path / "original.pdf", tmp_path / "encrypted.pdf"
    with pymupdf.open() as document:
        page = document.new_page()
        page.insert_text((72, 72), "Example notice 0000000001")
        document.save(original)
        expected_pixels = page.get_pixmap().samples
    content = original.read_bytes()
    encrypt_notice(
        create_test_client_record(),
        original,
        encrypted,
        {"password": {"template": password}},
    )
    with pymupdf.open(encrypted) as opened:
        assert opened.needs_pass
        assert not opened.authenticate("")
        assert not opened.authenticate("wrong-password")
        assert opened.authenticate(password)
        assert "0000000001" in opened[0].get_text()
        assert opened[0].get_pixmap().samples == expected_pixels
        assert opened.metadata["encryption"] == "Standard V5 R6 256-bit AES"
    assert original.read_bytes() == content


def test_password_that_becomes_empty_is_not_published(tmp_path: Path) -> None:
    original, encrypted = tmp_path / "original.pdf", tmp_path / "encrypted.pdf"
    with pymupdf.open() as document:
        document.new_page()
        document.save(original)
    # PDF password preparation removes the soft hyphen. Nonblank source text
    # must not turn into a file that opens without a password.
    with pytest.raises(ValueError, match="could not be verified"):
        encrypt_notice(
            create_test_client_record(),
            original,
            encrypted,
            {"password": {"template": "\u00ad"}},
        )
    assert not encrypted.exists()
    assert not list(tmp_path.glob("*.partial.pdf"))
