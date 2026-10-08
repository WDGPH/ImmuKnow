"""Encryption contracts for compiled notices."""

from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from immuknow import encrypt_notice

pytestmark = pytest.mark.unit


def make_pdf(path: Path) -> None:
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.add_metadata({"/Title": "Test Notice"})
    with path.open("wb") as stream:
        writer.write(stream)


def test_password_from_client_birth_date_opens_pdf(tmp_path: Path) -> None:
    """The expected client password opens the encrypted output."""
    pdf = tmp_path / "notice.pdf"
    make_pdf(pdf)
    encrypted = Path(
        encrypt_notice.encrypt_pdf(
            str(pdf),
            {"date_of_birth_iso_compact": "20150315"},
            config={"password": {"template": "{date_of_birth_iso_compact}"}},
        )
    )
    assert pdf.exists()
    reader = PdfReader(encrypted)
    assert reader.is_encrypted
    assert reader.decrypt("20150315")
    assert len(reader.pages) == 1
    assert reader.metadata is not None
    assert reader.metadata.title == "Test Notice"


def test_default_password_remains_compact_iso_date(tmp_path: Path) -> None:
    pdf = tmp_path / "notice.pdf"
    make_pdf(pdf)
    encrypted = encrypt_notice.encrypt_pdf(
        str(pdf), {"date_of_birth_iso_compact": "20150315"}, config={}
    )
    assert PdfReader(encrypted).decrypt("20150315")


def test_custom_password_template_uses_client_context(tmp_path: Path) -> None:
    pdf = tmp_path / "notice.pdf"
    make_pdf(pdf)
    encrypted = encrypt_notice.encrypt_pdf(
        str(pdf),
        {"client_id": "12345", "date_of_birth_iso_compact": "20150315"},
        config={"password": {"template": "{client_id}_{date_of_birth_iso_compact}"}},
    )
    reader = PdfReader(encrypted)
    assert not reader.decrypt("20150315")
    assert reader.decrypt("12345_20150315")


@pytest.mark.parametrize("template", ["{unknown_field}", "{client_ID}"])
def test_invalid_password_field_fails_clearly(tmp_path: Path, template: str) -> None:
    pdf = tmp_path / "notice.pdf"
    make_pdf(pdf)
    with pytest.raises(ValueError, match="Invalid password template"):
        encrypt_notice.encrypt_pdf(
            str(pdf),
            {"client_id": "12345"},
            config={"password": {"template": template}},
        )
    assert not (tmp_path / "notice_encrypted.pdf").exists()


def test_ambiguous_password_placeholder_fails_before_pdf_write(tmp_path: Path) -> None:
    pdf = tmp_path / "notice.pdf"
    make_pdf(pdf)
    with pytest.raises(ValueError, match="date_of_birth_iso"):
        encrypt_notice.encrypt_pdf(
            str(pdf),
            {"date_of_birth": "March 15, 2015"},
            config={"password": {"template": "{date_of_birth}"}},
        )
    assert not (tmp_path / "notice_encrypted.pdf").exists()
