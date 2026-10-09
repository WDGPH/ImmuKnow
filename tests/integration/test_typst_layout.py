"""Measure actual compiled layout, including overflow and missing evidence."""

import json
from pathlib import Path

import pytest
import pymupdf
from pypdf import PdfReader

from immuknow.validate_pdfs import validate_notices, validate_pdf_structure
from tests.integration.test_native_templates import compile_notice, prepare_case

pytestmark = pytest.mark.integration


def render(tmp_path: Path, case="overdue_agents_fr", replace=()):
    template, data, _ = prepare_case(tmp_path / "project", case)
    source = template.read_text()
    for before, after in replace:
        assert before in source
        source = source.replace(before, after)
    template.write_text(source)
    result = compile_notice(template, data, template.parents[1])
    assert result.returncode == 0, result.stderr
    assert "did not converge" not in result.stderr
    return template.parents[1] / "notice.pdf"


def validate(pdf, **rules):
    return validate_pdf_structure(
        pdf,
        enabled_rules={
            "exactly_two_pages": "disabled",
            "signature_overflow": "error",
            "envelope_window": "error",
            "client_id_presence": "error",
            **rules,
        },
        client_id_map={pdf.name: "0000000001"},
    )


def test_default_geometry_and_french_signature_fit(tmp_path):
    pdf = render(tmp_path)
    result = validate(pdf)
    assert result.passed, result.warnings
    m = result.measurements
    assert m["page_count"] == 2
    assert m["signature_page"] == 1
    assert m["window_x"] == pytest.approx(1.75 / 2.54 * 72)
    assert m["window_y"] == 165.1
    assert m["address_x"] == pytest.approx(m["window_x"] + 11)
    assert m["address_y"] == pytest.approx(m["window_y"] + 11)
    assert m["address_height"] > 40


def test_long_address_is_not_clipped_and_reports_overflow(tmp_path):
    pdf = render(tmp_path, "long_address")
    result = validate(pdf)
    assert not result.passed
    assert len(result.warnings) == 1
    assert "Address exceeds the window safety area" in result.warnings[0]
    assert result.measurements["address_height"] > 59
    text = PdfReader(pdf).pages[0].extract_text()
    assert "Building West" in " ".join(text.split())
    assert "N1H 2T2" in text
    # The selected severity controls delivery; the evidence is identical.
    with pytest.raises(RuntimeError, match="PDF validation failed with errors"):
        validate_notices([pdf], enabled_rules={"envelope_window": "error"})
    summary = validate_notices([pdf], enabled_rules={"envelope_window": "warn"})
    assert summary.warning_count == 1


def test_custom_window_repositions_content_and_fits_long_address(tmp_path):
    pdf = render(
        tmp_path,
        "long_address",
        [
            (
                "x: 1.75cm, y: 165.1pt, width: 202.28pt, height: 81pt, padding: 11pt",
                "x: 2cm, y: 170pt, width: 240pt, height: 90pt, padding: 8pt",
            )
        ],
    )
    result = validate(pdf)
    assert result.passed, result.warnings
    assert result.measurements["address_x"] == pytest.approx(2 / 2.54 * 72 + 8)
    assert result.measurements["address_y"] == 178
    assert result.measurements["window_height"] == 90
    original = render(tmp_path / "original", "long_address")

    def address_origin(path):
        with pymupdf.open(path) as document:
            words = document[0].get_text("words")
            return next(word[:2] for word in words if word[4] == "Au")

    original_x, original_y = address_origin(original)
    moved_x, moved_y = address_origin(pdf)
    assert moved_x - original_x == pytest.approx((2 - 1.75) / 2.54 * 72 - 3, abs=0.01)
    assert moved_y - original_y == pytest.approx(170 - 165.1 - 3, abs=0.01)
    # Geometry is independent of the historical fixed-height compatibility rule.
    legacy = validate(pdf, envelope_window_1_125="warn")
    assert any("envelope_window_1_125" in warning for warning in legacy.warnings)


@pytest.mark.parametrize("missing", ["signature", "geometry"])
def test_missing_required_measurement_is_a_failure(tmp_path, missing):
    template, data, _ = prepare_case(tmp_path / "project", "overdue_agents_en")
    layout = template.parent / "lib/immuknow/src/layout.typ"
    text = layout.read_text()
    if missing == "signature":
        text = text.replace("MARK_END_SIGNATURE_BLOCK", "REMOVED_SIGNATURE_EVIDENCE")
    else:
        text = text.replace('"MEASURE_"', '"REMOVED_"')
    layout.write_text(text)
    result = compile_notice(template, data, template.parents[1])
    assert result.returncode == 0, result.stderr
    assert "did not converge" not in result.stderr
    checked = validate(template.parents[1] / "notice.pdf")
    assert not checked.passed
    assert any(
        (
            "signature_overflow"
            if missing == "signature"
            else "Missing geometry evidence"
        )
        in warning
        for warning in checked.warnings
    )


def test_signature_overflow_remains_detectable(tmp_path):
    pdf = render(
        tmp_path,
        replace=[("#ik.signature-block(", "#v(100pt)\n#ik.signature-block(")],
    )
    result = validate(pdf)
    assert result.measurements["signature_page"] == 2
    assert any(
        "Signature block ends on page 2" in warning for warning in result.warnings
    )


def test_page_numbers_can_be_disabled(tmp_path):
    pdf = render(
        tmp_path,
        replace=[
            ("font-size: body-size)", "font-size: body-size, page-numbers: false)")
        ],
    )
    pages = [page.extract_text() for page in PdfReader(pdf).pages]
    assert "1 / 2" not in pages[0]
    assert "2 / 2" not in pages[1]
    assert validate(pdf).passed


@pytest.mark.parametrize(
    ("before", "after", "diagnostic"),
    [
        ("padding: 11pt", "padding: 100pt", "padding leaves no usable area"),
        ("y: 165.1pt", "y: 50pt", "overlaps preceding content"),
        ("x: 1.75cm", 'x: "left"', "must be an absolute physical length"),
        (
            "#let client-font-size = 10pt",
            "#let client-font-size = 8pt",
            "below the declared readable minimum",
        ),
    ],
)
def test_invalid_layout_options_are_actionable(tmp_path, before, after, diagnostic):
    template, data, _ = prepare_case(tmp_path / "project", "overdue_agents_en")
    template.write_text(template.read_text().replace(before, after))
    result = compile_notice(template, data, template.parents[1])
    assert result.returncode != 0
    assert diagnostic in result.stderr


def test_address_at_safety_boundary_and_one_point_over(tmp_path):
    original = render(tmp_path / "measured", "long_address")
    height = validate(original).measurements["address_height"] + 22
    for delta in (0, -1):
        pdf = render(
            tmp_path / str(delta),
            "long_address",
            [("height: 81pt", f"height: {height + delta}pt")],
        )
        checked = validate(pdf, signature_overflow="disabled")
        assert checked.passed is (delta == 0), checked.warnings


def test_window_outside_page_is_not_valid_geometry(tmp_path):
    pdf = render(tmp_path, replace=[("width: 202.28pt", "width: 600pt")])
    checked = validate(pdf, signature_overflow="disabled")
    assert any(
        "Invalid window or page geometry" in warning for warning in checked.warnings
    )


def test_optional_client_fields_and_adult_addressee(tmp_path):
    template, data, notice = prepare_case(tmp_path / "project", "affirmative_en")
    notice["client_data"]["over_16"] = True
    data.write_text(json.dumps(notice))
    template.write_text(
        template.read_text().replace(
            "details: client-details,",
            'details: "below", show-birth-date: false, show-school: false,',
        )
    )
    result = compile_notice(template, data, template.parents[1])
    assert result.returncode == 0, result.stderr
    assert not result.stderr
    pdf = template.parents[1] / "notice.pdf"
    text = PdfReader(pdf).pages[0].extract_text()
    assert "To:" in text
    assert "Parent/Guardian" not in text
    assert "Date of Birth:" not in text
    assert "Childcare Centre:" not in text
    assert "0000000001" in text
    assert validate(pdf).passed
