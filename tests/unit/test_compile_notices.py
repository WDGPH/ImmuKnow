"""Compiler discovery and pinned-version diagnostics."""

from __future__ import annotations

import subprocess
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from immuknow import compile_notices
from immuknow.data_models import RenderJob
from immuknow.render_contract import report_schema
from immuknow.validate_pdfs import inspect_notice
from pypdf._page import PageObject


@pytest.mark.unit
def test_missing_compiler_has_installation_guidance() -> None:
    """An unavailable executable should explain the supported selection routes."""
    with pytest.raises(RuntimeError, match="Install Typst 0.15.1.*TYPST_BIN"):
        compile_notices.check_compiler("/missing/typst")


@pytest.mark.unit
@pytest.mark.parametrize("version", ["0.14.2", "0.15.0", "0.16.0-rc1"])
def test_unsupported_compiler_is_rejected(version: str) -> None:
    """Older compilers and untested prereleases must fail before notice compilation."""
    result = subprocess.CompletedProcess([], 0, stdout=f"typst {version} (test)")
    with (
        patch("immuknow.compile_notices.subprocess.run", return_value=result),
        pytest.raises(RuntimeError, match="Unsupported compiler"),
    ):
        compile_notices.check_compiler("typst")


@pytest.mark.integration
def test_pdf_and_required_evidence_share_one_compilation(
    tmp_path: Path, monkeypatch
) -> None:
    """Typst evidence is authoritative; artifact inspection does not parse its content."""
    data = tmp_path / "data.json"
    payload = json.loads(
        (Path(__file__).parents[1] / "fixtures/render-contract.json").read_text()
    )["payload"]
    payload.update(template="example.en.typ", version_id="example")
    data.write_text(json.dumps(payload))
    entry = tmp_path / "example.en.typ"
    summary = {
        "notice": payload,
        "schema_version": 2,
        "identity": {
            "row_key": "row-000001",
            "template": "example.en.typ",
            "client_id": "0000000001",
            "version_id": "example",
            "language": "en",
        },
        "page_count": 1,
        "components": {
            name: name == "client"
            for name in report_schema()["properties"]["components"]["properties"]
        },
        "checks": [
            {
                "code": "compiler.warning",
                "stage": "render",
                "status": "warn",
                "message": "Visible warning example.",
            }
        ],
        "qr_urls": [],
        "measurements": {
            "client": [
                {
                    "row_key": "row-000001",
                    "client_id": "0000000001",
                    "text": "Client ID: 0000000001",
                    "page": 1,
                    "x_pt": 0,
                    "y_pt": 0,
                    "width_pt": 60,
                    "height_pt": 10,
                    "source_matches": True,
                }
            ]
        },
    }
    summary["checks"] += [
        {
            "code": f"component.{name}.absent",
            "stage": "render",
            "status": "not_applicable",
            "message": "Component was not used.",
            "component": name,
        }
        for name, placed in summary["components"].items()
        if not placed
    ]
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps(summary))
    source = (
        '#set text(font: "Unavailable ImmuKnow Test Font")\n'
        "Phone: 0000000001\n\nClient ID: 9999999999\n"
        '#context { [#metadata(json("evidence.json")) <immuknow-report>] }'
    )
    entry.write_text(source)
    job = RenderJob(
        "row-000001",
        "0000000001",
        "en",
        "example",
        tmp_path,
        entry,
        data,
        tmp_path / "original.pdf",
        1735689600,
    )
    with patch(
        "immuknow.compile_notices.run_typst", wraps=compile_notices.run_typst
    ) as run:
        warnings, report, error = compile_notices.compile_render_job(job, "typst")
    assert run.call_count == 1
    assert error is None
    assert [warning.code for warning in warnings] == ["compiler.font_substitution"]

    def forbidden(*args, **kwargs):
        raise AssertionError("PDF content must not be inspected")

    monkeypatch.setattr(PageObject, "extract_text", forbidden)
    monkeypatch.setattr(PageObject, "annotations", property(forbidden))
    original, checks = inspect_notice(job, tmp_path)
    assert original["pages"] == 1
    assert original["sha256"]
    assert report is not None
    assert report["checks"][0]["code"] == "compiler.warning"
    assert [(check.code, check.status) for check in checks] == [
        ("output.readable", "pass")
    ]
    entry.write_text("Client ID: 0000000001")
    _, report, error = compile_notices.compile_render_job(job, "typst")
    assert report is None
    assert isinstance(error, ValueError)
    assert "exactly one" in str(error)
    assert job.pdf.is_file()
    entry.write_text('#panic("real compile failure")')
    with pytest.raises(subprocess.CalledProcessError) as failure:
        compile_notices.compile_render_job(job, "typst")
    assert "real compile failure" in failure.value.stderr
    assert not job.pdf.exists()


def test_compiler_warnings_are_classified():
    stderr = (
        "warning: unknown font family: missing\n"
        "warning: layout did not converge within 5 attempts\n"
        "warning: something else\n"
    )
    assert [check.code for check in compile_notices.compiler_warnings(stderr)] == [
        "compiler.font_substitution",
        "compiler.layout_nonconvergent",
        "compiler.warning",
    ]


def test_evidence_attachment_is_scrubbed_even_when_aliased():
    """Private report streams are removed before cloning the published PDF."""
    from io import BytesIO

    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import ArrayObject, NameObject, StreamObject

    secret = b"fictional-private-evidence-sentinel"
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    reserved = writer.add_attachment(compile_notices.EVIDENCE_ATTACHMENT, secret)
    writer.add_attachment("unrelated.txt", b"public attachment")
    writer.root_object[NameObject("/AF")] = ArrayObject(
        [reserved.pdf_object.indirect_reference]
    )
    page[NameObject("/AF")] = ArrayObject([reserved.pdf_object.indirect_reference])
    raw = BytesIO()
    writer.write(raw)

    cleaned, payloads, unreadable = compile_notices._strip_evidence(raw.getvalue())
    assert payloads == [secret]
    assert not unreadable
    assert secret not in cleaned
    result = PdfReader(BytesIO(cleaned))
    assert result.attachments["unrelated.txt"] == [b"public attachment"]
    assert compile_notices.EVIDENCE_ATTACHMENT not in result.attachments
    assert not result.root_object["/AF"]
    assert not result.pages[0]["/AF"]
    size = result.trailer["/Size"]
    assert isinstance(size, int)
    for number in range(1, size):
        obj = result.get_object(number)
        if isinstance(obj, StreamObject):
            assert secret not in obj.get_data()


def test_duplicate_reserved_attachments_are_all_scrubbed():
    from io import BytesIO

    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import StreamObject

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.add_attachment(compile_notices.EVIDENCE_ATTACHMENT, b"private-first")
    writer.add_attachment(compile_notices.EVIDENCE_ATTACHMENT, b"private-second")
    raw = BytesIO()
    writer.write(raw)
    cleaned, payloads, unreadable = compile_notices._strip_evidence(raw.getvalue())
    assert payloads == [b"private-first", b"private-second"]
    assert not unreadable
    result = PdfReader(BytesIO(cleaned))
    assert not list(result.attachment_list)
    size = result.trailer["/Size"]
    assert isinstance(size, int)
    for number in range(1, size):
        obj = result.get_object(number)
        if isinstance(obj, StreamObject):
            assert b"private-first" not in obj.get_data()
            assert b"private-second" not in obj.get_data()


def test_malformed_attachment_tree_never_releases_evidence():
    from io import BytesIO

    from pypdf import PdfWriter
    from pypdf.generic import (
        ArrayObject,
        DictionaryObject,
        NameObject,
        TextStringObject,
    )

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    evidence = writer.add_attachment(
        compile_notices.EVIDENCE_ATTACHMENT, b"fictional-private-sentinel"
    )
    writer.root_object[NameObject("/AF")] = ArrayObject(
        [evidence.pdf_object.indirect_reference]
    )
    names = writer.root_object["/Names"]
    assert isinstance(names, DictionaryObject)
    embedded = names["/EmbeddedFiles"]
    assert isinstance(embedded, DictionaryObject)
    embedded[NameObject("/Names")] = ArrayObject(
        [TextStringObject(compile_notices.EVIDENCE_ATTACHMENT), TextStringObject("bad")]
    )
    raw = BytesIO()
    writer.write(raw)
    with pytest.raises(ValueError, match="name tree"):
        compile_notices._strip_evidence(raw.getvalue())


def test_unlisted_associated_evidence_fails_closed():
    from io import BytesIO

    from pypdf import PdfWriter
    from pypdf.generic import ArrayObject, DictionaryObject, NameObject

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    evidence = writer.add_attachment(
        compile_notices.EVIDENCE_ATTACHMENT, b"fictional-private-sentinel"
    )
    writer.root_object[NameObject("/AF")] = ArrayObject(
        [evidence.pdf_object.indirect_reference]
    )
    names = writer.root_object["/Names"]
    assert isinstance(names, DictionaryObject)
    embedded = names["/EmbeddedFiles"]
    assert isinstance(embedded, DictionaryObject)
    del embedded["/Names"]
    raw = BytesIO()
    writer.write(raw)
    with pytest.raises(ValueError, match="unlisted"):
        compile_notices._strip_evidence(raw.getvalue())


def test_sanitization_failure_never_publishes_raw_pdf(tmp_path: Path, monkeypatch):
    from io import BytesIO

    from pypdf import PdfWriter
    from pypdf.generic import (
        ArrayObject,
        DictionaryObject,
        NameObject,
        TextStringObject,
    )

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    evidence = writer.add_attachment(
        compile_notices.EVIDENCE_ATTACHMENT, b"fictional-private-sentinel"
    )
    writer.root_object[NameObject("/AF")] = ArrayObject(
        [evidence.pdf_object.indirect_reference]
    )
    names = writer.root_object["/Names"]
    assert isinstance(names, DictionaryObject)
    embedded = names["/EmbeddedFiles"]
    assert isinstance(embedded, DictionaryObject)
    embedded[NameObject("/Names")] = ArrayObject(
        [TextStringObject(compile_notices.EVIDENCE_ATTACHMENT), TextStringObject("bad")]
    )
    raw = BytesIO()
    writer.write(raw)
    template = tmp_path / "example.en.typ"
    template.write_text("Example")
    data = tmp_path / "facts.json"
    data.write_text("{}")
    job = RenderJob(
        "row-1",
        "client",
        "en",
        "example",
        tmp_path,
        template,
        data,
        tmp_path / "originals" / "notice.pdf",
        1735689600,
    )

    def fake_compile(command, **_kwargs):
        Path(command[-1]).write_bytes(raw.getvalue())
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(compile_notices, "run_typst", fake_compile)
    with pytest.raises(ValueError, match="name tree"):
        compile_notices.compile_render_job(job, "typst")
    assert not job.pdf.exists()
    assert not list((tmp_path / "work").rglob("*.pdf"))


def test_unexpected_evidence_failure_keeps_the_sanitized_original(
    tmp_path: Path, monkeypatch
):
    template = tmp_path / "example.en.typ"
    template.write_text("Example")
    data = tmp_path / "facts.json"
    data.write_text("{}")
    job = RenderJob(
        "row-1",
        "client",
        "en",
        "example",
        tmp_path,
        template,
        data,
        tmp_path / "originals" / "notice.pdf",
        1735689600,
    )

    def fake_compile(command, **_kwargs):
        Path(command[-1]).write_bytes(b"temporary raw PDF")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    def unexpected(*_args):
        raise RuntimeError("unexpected evidence validator failure")

    monkeypatch.setattr(compile_notices, "run_typst", fake_compile)
    monkeypatch.setattr(
        compile_notices,
        "_strip_evidence",
        lambda _data: (b"sanitized PDF", [b"[]"], False),
    )
    monkeypatch.setattr(compile_notices, "parse_json", lambda *_a, **_kw: [{}])
    monkeypatch.setattr(
        compile_notices,
        "read_json",
        lambda _path: {
            "row_key": job.sequence,
            "template": job.template.name,
            "client_id": job.client_id,
            "version_id": job.version_id,
            "language": job.language,
        },
    )
    monkeypatch.setattr(compile_notices, "validate_render_report", unexpected)
    _, summary, error = compile_notices.compile_render_job(job, "typst")
    assert summary is None
    assert isinstance(error, RuntimeError)
    assert job.pdf.read_bytes() == b"sanitized PDF"
