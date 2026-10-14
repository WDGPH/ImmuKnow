"""Read actual package metadata and PDFs with the pinned native compiler."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote

import pytest
from pypdf import PdfReader
from pypdf.generic import DictionaryObject

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


def compile_package(tmp_path: Path, body: str) -> tuple[dict, PdfReader]:
    shutil.copytree(ROOT / "immuknow/templates/lib", tmp_path / "lib")
    notice = {
        "schema_version": 1,
        "version_id": "test",
        "language": "en",
        "client_id": "1234567890",
        "row_key": "row-1",
        "template": "test.en.typ",
        "date_of_delivery": "2026-06-01",
        "date_as_of": "2026-06-01",
        "school": {},
        "board": {},
        "client_data": {
            "name": "Éloïse & 50% $(hello)",
            "first_name": "Éloïse",
            "last_name": "Example",
            "address": "42 Example Street",
            "city": "Montréal",
            "province": "Québec",
            "postal_code": "A1A 1A1",
            "school": "Example School",
            "date_of_birth_iso": "",
            "over_16": None,
            "age": None,
        },
        "overdue_diseases": [{"disease": "Measles", "dose": 2}],
        "overdue_agents": ["MMR"],
        "history": [
            {
                "date_given": "2020-01-01",
                "agent": "MMR",
                "display_name": "MMR",
                "diseases": ["Measles"],
                "validity": validity,
            }
            for validity in ("valid", "invalid", "unknown")
        ],
        "validity_coverage": "mixed",
    }
    (tmp_path / "data.json").write_text(json.dumps(notice))
    source = tmp_path / "notice.typ"
    source.write_text(
        '#import "lib/immuknow/lib.typ" as immuknow\n'
        '#let notice = json("data.json")\n'
        "#show: immuknow.notice-style.with(notice: notice)\n" + body
    )
    common = [
        os.environ.get("TYPST_BIN", "typst"),
        "--root",
        str(tmp_path),
        "--creation-timestamp",
        "1780272000",
    ]
    compiled = subprocess.run(
        [common[0], "compile", *common[1:], str(source), str(tmp_path / "notice.pdf")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert compiled.returncode == 0, compiled.stderr
    assert compiled.stderr == "", compiled.stderr
    evaluated = subprocess.run(
        [
            common[0],
            "eval",
            *common[1:],
            "--in",
            str(source),
            "query(<immuknow-report>).map(it => it.value)",
            "--format",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert evaluated.returncode == 0, evaluated.stderr
    assert evaluated.stderr == "", evaluated.stderr
    reports = json.loads(evaluated.stdout)
    assert len(reports) == 1
    reader = PdfReader(tmp_path / "notice.pdf")
    assert reports[0]["page_count"] == len(reader.pages)
    assert all(type(value) is bool for value in reports[0]["components"].values())
    assert all(check["stage"] == "render" for check in reports[0]["checks"])
    assert "MEASURE_" not in "".join(page.extract_text() for page in reader.pages)
    return reports[0], reader


def test_package_import_and_unused_history_require_no_facts(tmp_path: Path) -> None:
    shutil.copytree(ROOT / "immuknow/templates/lib", tmp_path / "lib")
    source = tmp_path / "import.typ"
    source.write_text('#import "lib/immuknow/lib.typ" as immuknow\nImported.')
    result = subprocess.run(
        [
            os.environ.get("TYPST_BIN", "typst"),
            "compile",
            str(source),
            str(tmp_path / "import.pdf"),
            "--creation-timestamp",
            "1780272000",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""


@pytest.mark.parametrize("show_history", [False, True])
def test_placed_history_and_qr_share_honest_evidence(
    tmp_path: Path,
    show_history: bool,
) -> None:
    body = """
#let history = [#immuknow.immunization-history(notice,
  diseases: ("Measles",), show-validity: true, labels: (en_diseases_chart: (:)))]
#immuknow.notice-section("Immunization notice")[
  #immuknow.client-block(notice)
  #immuknow.overdue-diseases(notice, include-dose: true)
  #immuknow.signature-block(name: [Dr Example], title: [Medical officer])
  #immuknow.qr-code(notice, url: n => immuknow.query-url(
    "https://example.test/record", (id: n.client_id, name: n.client_data.name)))
]
"""
    if show_history:
        body += '#immuknow.notice-section("History")[#history]'
    report, reader = compile_package(tmp_path, body)
    expected_url = "https://example.test/record?id=1234567890&name=" + quote(
        "Éloïse & 50% $(hello)", safe=""
    )
    assert report["qr_urls"] == [expected_url]
    annotations = reader.pages[0].annotations
    assert annotations
    annotation = annotations[0].get_object()
    assert isinstance(annotation, DictionaryObject)
    action = annotation["/A"]
    assert isinstance(action, DictionaryObject)
    assert action["/URI"] == expected_url
    assert report["identity"] == {
        "client_id": "1234567890",
        "version_id": "test",
        "language": "en",
    }
    address = report["measurements"]["address"][0]
    assert address["x_pt"] == pytest.approx(74)
    assert address["y_pt"] == pytest.approx(191)
    assert report["components"]["history"] == show_history
    assert (
        "content.history_validity" in {check["code"] for check in report["checks"]}
    ) == show_history
    assert (
        "content.translation_missing" in {check["code"] for check in report["checks"]}
    ) == show_history
    text = " ".join(page.extract_text() for page in reader.pages)
    assert "Québec" in text and "Ontario" not in text
    assert "Éloïse & 50% $(hello)" in text
    # Check PDF text positions independently of Typst's invisible findings.
    positions = {}

    def record_position(text, cm, tm, font, size):
        for label in ("Measles (2nd dose)", "Dr Example"):
            if label in text:
                positions[label] = (tm[4] * cm[1] + tm[5] * cm[3] + cm[5], size)

    reader.pages[0].extract_text(visitor_text=record_position)
    bullet_y, bullet_size = positions["Measles (2nd dose)"]
    signature_y, signature_size = positions["Dr Example"]
    assert bullet_y - signature_y >= max(bullet_size, signature_size)
    if show_history:
        for expected in (
            "⬤",
            "○",
            "?",
            "Valid dose",
            "Invalid dose",
            "Validity unknown",
        ):
            assert expected in text
    else:
        assert any(
            check["component"] == "history" and check["status"] == "not_applicable"
            for check in report["checks"]
        )


def test_overflow_retains_pages_and_reports_real_bounds(tmp_path: Path) -> None:
    report, reader = compile_package(
        tmp_path,
        """
#immuknow.notice-section("Very long title " * 40)[
  #immuknow.client-block((..notice, client_data: (..notice.client_data,
    address: "123 Example Street " * 35)))
  #for _ in range(20) [A long paragraph continues visibly. #parbreak()]
  #immuknow.signature-block(name: [#for _ in range(120) [Signature line #linebreak()]],
    title: [Medical officer])
]
""",
    )
    warnings = {
        check["code"]: check for check in report["checks"] if check["status"] == "warn"
    }
    assert {
        "layout.header_title_lines",
        "layout.address_outside_window",
        "layout.signature_page",
        "layout.section_pages",
    } <= warnings.keys()
    assert warnings["layout.address_outside_window"]["measurements"]["bottom_pt"] > 100
    signature = warnings["layout.signature_page"]["measurements"]
    assert signature["last_page"] > signature["first_page"]
    assert report["page_count"] >= 3
    text = " ".join(page.extract_text() for page in reader.pages)
    assert text.count("Signature line") == 120
    assert "Medical officer" in reader.pages[-1].extract_text()
    assert (
        len(
            [
                check
                for check in report["checks"]
                if check["code"] == "layout.signature_page"
            ]
        )
        == 1
    )
