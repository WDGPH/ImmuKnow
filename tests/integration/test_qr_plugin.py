"""Decode the shipped plugin independently, including exact UTF-8 capacity limits."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pymupdf
import pytest
import zxingcpp

from immuknow.resources import typst_library_root
from tests.integration.test_typst_package import compile_package

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "correction,capacity", [("l", 17), ("m", 14), ("q", 11), ("h", 7)]
)
@pytest.mark.parametrize("overflow", [False, True])
@pytest.mark.parametrize("encoding", ["encode", "encode_runs"])
def test_utf8_eci_accounts_for_capacity_and_decodes(
    tmp_path: Path, correction: str, capacity: int, overflow: bool, encoding: str
) -> None:
    # Version 1 byte capacities have four spare header bits. ECI 26 consumes
    # those bits plus one byte; the next byte must select version 2.
    text = "é" + "a" * (capacity - 3 + int(overflow))
    shutil.copyfile(typst_library_root() / "vendor/qr/qr.wasm", tmp_path / "qr.wasm")
    source = tmp_path / "probe.typ"
    source.write_text(
        '#let encoder = plugin("qr.wasm")\n'
        f'#metadata(array(encoder.{encoding}(bytes(sys.inputs.at("text")), '
        'bytes(sys.inputs.at("correction"))))) <matrix>\n'
    )
    result = subprocess.run(
        [
            os.environ.get("TYPST_BIN", "typst"),
            "query",
            "--root",
            str(tmp_path),
            "--input",
            "text=" + text,
            "--input",
            "correction=" + correction,
            str(source),
            "<matrix>",
            "--field",
            "value",
            "--one",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    encoded = json.loads(result.stdout)
    size, cells = encoded[0], encoded[1:]
    assert size == (25 if overflow else 21)
    if encoding == "encode_runs":
        runs = cells
        assert len(runs) % 3 == 0
        cells = [0] * (size * size)
        for row, start, end in zip(runs[::3], runs[1::3], runs[2::3]):
            assert 0 <= row < size and 0 <= start < end <= size
            cells[row * size + start : row * size + end] = [1] * (end - start)
    assert len(cells) == size * size
    scale = 6
    width = (size + 8) * scale
    border = bytes([255]) * width
    rows = [border] * (4 * scale)
    for offset in range(0, len(cells), size):
        row = bytes([255]) * (4 * scale)
        row += b"".join(
            bytes([0 if cell else 255]) * scale
            for cell in cells[offset : offset + size]
        )
        row += bytes([255]) * (4 * scale)
        rows.extend([row] * scale)
    rows.extend([border] * (4 * scale))
    pixels = memoryview(b"".join(rows)).cast("B", [width, width])
    plain = zxingcpp.read_barcodes(pixels)
    assert len(plain) == 1
    assert plain[0].text == text
    assert plain[0].bytes == text.encode()
    assert plain[0].ec_level == correction.upper()
    declared = zxingcpp.read_barcodes(pixels, text_mode=zxingcpp.TextMode.ECI)
    assert declared[0].text == "]Q2\\000026" + text


@pytest.mark.parametrize(
    "correction,suffix",
    [("l", "Éloïse"), ("m", "Алексей"), ("q", "李明"), ("h", "😀"), ("l", "e\u0301")],
)
@pytest.mark.parametrize("style", ["square", "rounded"])
def test_styled_pdf_preserves_unicode_destination_and_requested_correction(
    tmp_path: Path, correction: str, suffix: str, style: str
) -> None:
    url = "https://example.org/" + suffix
    report, _ = compile_package(
        tmp_path,
        f"#immuknow.qr-code(notice, url: {json.dumps(url, ensure_ascii=False)}, "
        f'error-correction: "{correction}", module-shape: "{style}", corner-style: "{style}")',
    )
    assert report["qr_urls"] == [url]
    with pymupdf.open(tmp_path / "notice.pdf") as document:
        pixmap = document[0].get_pixmap(dpi=250, colorspace=pymupdf.csGRAY)
        pixels = memoryview(pixmap.samples).cast("B", [pixmap.height, pixmap.width])
        decoded = zxingcpp.read_barcodes(pixels)
        assert len(decoded) == 1
        assert decoded[0].text == url
        assert decoded[0].ec_level == correction.upper()


def test_centre_logo_preserves_decodable_high_correction_symbol(tmp_path: Path) -> None:
    url = "https://example.org/update"
    compile_package(
        tmp_path,
        f'#immuknow.qr-code(notice, url: "{url}", '
        "logo: rect(width: 8pt, height: 8pt, fill: red), logo-size: 10%)",
    )
    with pymupdf.open(tmp_path / "notice.pdf") as document:
        pixmap = document[0].get_pixmap(dpi=250, colorspace=pymupdf.csGRAY)
        decoded = zxingcpp.read_barcodes(
            memoryview(pixmap.samples).cast("B", [pixmap.height, pixmap.width])
        )
        assert [code.text for code in decoded] == [url]
        assert decoded[0].ec_level == "H"
