"""Inspect actual Typst view projections and PDF contents using prepared facts."""

import json
import os
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path

import pytest
from pypdf import PdfReader

from tests.integration.test_typst_package import PACKAGE
from tests.unit.test_render_payload import prepared_payload

pytestmark = pytest.mark.integration


def compile_component(tmp_path: Path, notice, options="", *, body=None):
    shutil.copytree(PACKAGE, tmp_path / "lib")
    (tmp_path / "notice.json").write_text(json.dumps(notice, ensure_ascii=False))
    source = tmp_path / "main.typ"
    source.write_text(
        '#import "lib/lib.typ" as ik\n#import "lib/src/history.typ": history-view\n'
        '#let n = json("notice.json")\n#set text(font: "FreeSans", size: 10pt)\n'
        '#ik.check-notice(n, version: "overdue_agents_v1", language: "en")\n'
        + (
            body
            if body is not None
            else f"#metadata(history-view(n, {options})) <projection>\n#ik.immunization-history(n, {options})"
        )
    )
    compiler = os.environ.get("TYPST_BIN", "typst")
    output = tmp_path / "result.pdf"
    result = subprocess.run(
        [compiler, "compile", "--root", str(tmp_path), str(source), str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        return result, None, None
    text = "\n".join(page.extract_text() for page in PdfReader(output).pages)
    if body is not None:
        return result, None, text
    query = subprocess.run(
        [
            compiler,
            "query",
            "--root",
            str(tmp_path),
            str(source),
            "<projection>",
            "--field",
            "value",
            "--one",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return result, json.loads(query.stdout), text


def test_filtering_removes_only_selected_agent_contributions(tmp_path):
    notice = prepared_payload("May 1, 2020 - MMR - Valid; May 1, 2020 - Ig - Invalid")
    result, view, text = compile_component(
        tmp_path,
        notice,
        'diseases: ("Measles",), ignore-agents: ("MMR",), show-validity: true',
    )
    assert result.returncode == 0, result.stderr
    assert view["columns"] == ["Measles", "Other"]
    assert view["rows"] == [
        {
            "date": "2020-05-01",
            "rowspan": 1,
            "agents": ["Ig"],
            "marks": {"Other": "invalid"},
        }
    ]
    assert "MMR" not in text
    assert "Ig" in text


def test_combination_agent_contributes_to_named_and_other(tmp_path):
    notice = prepared_payload("May 1, 2020 - MMR - Valid")
    result, view, _ = compile_component(
        tmp_path,
        notice,
        'diseases: ("Mumps", "Measles"), ignore-agents: (), show-validity: false',
    )
    assert result.returncode == 0, result.stderr
    assert view["columns"] == ["Mumps", "Measles", "Other"]
    assert view["rows"][0]["marks"] == {
        "Measles": "recorded",
        "Mumps": "recorded",
        "Other": "recorded",
    }


@pytest.mark.parametrize("other", [True, False])
def test_zero_diseases_and_other_toggle_keep_agents_and_date(tmp_path, other):
    notice = prepared_payload("May 1, 2020 - Ig - Invalid")
    result, view, text = compile_component(
        tmp_path,
        notice,
        f"diseases: (), ignore-agents: (), include-other: {str(other).lower()}",
    )
    assert result.returncode == 0, result.stderr
    assert view["columns"] == (["Other"] if other else [])
    assert view["rows"][0]["agents"] == ["Ig"]
    assert "May 1, 2020" in " ".join(text.split()) and "Ig" in text


def test_inherited_exclusions_and_empty_override_differ(tmp_path):
    notice = prepared_payload("May 1, 2020 - Ig - Invalid")
    for folder, options, expected in [
        ("default", "", 0),
        ("override", "ignore-agents: ()", 1),
    ]:
        directory = tmp_path / folder
        directory.mkdir()
        result, view, _ = compile_component(directory, notice, options)
        assert result.returncode == 0, result.stderr
        assert len(view["rows"]) == expected


def test_conflicting_statuses_split_rows_and_recompute_date_span(tmp_path):
    notice = prepared_payload("May 1, 2020 - MMR - Valid; May 1, 2020 - Ig - Invalid")
    result, view, text = compile_component(
        tmp_path, notice, "diseases: (), ignore-agents: (), show-validity: true"
    )
    assert result.returncode == 0, result.stderr
    assert [row["rowspan"] for row in view["rows"]] == [2, 0]
    assert [row["marks"] for row in view["rows"]] == [
        {"Other": "valid"},
        {"Other": "invalid"},
    ]
    assert "Valid dose" in text and "Invalid dose" in text


def test_all_absent_stays_unknown_when_template_enables_markers(tmp_path):
    notice = prepared_payload("May 1, 2020 - MMR")
    result, view, text = compile_component(tmp_path, notice, "show-validity: true")
    assert result.returncode == 0, result.stderr
    assert set(view["rows"][0]["marks"].values()) == {"unknown"}
    assert "Validity unknown" in text


def test_template_cannot_enable_mixed_coverage_markers(tmp_path):
    notice = prepared_payload("May 1, 2020 - MMR - Valid; May 1, 2020 - Ig")
    result, _, _ = compile_component(tmp_path, notice, "show-validity: true")
    assert result.returncode != 0
    assert "mixed cohort validity coverage" in result.stderr


@pytest.mark.parametrize(
    "options,diagnostic",
    [
        ('diseases: ("Measles", "Mumps", "Measles")', "duplicate"),
        ('diseases: ("Other",)', "include-other"),
        ("include-other: 1", "boolean"),
        ('show-validity: "false"', "boolean"),
        ('ignore-agents: "Ig"', "array"),
        ("min-rows: -1", "nonnegative"),
    ],
)
def test_invalid_history_options_fail(tmp_path, options, diagnostic):
    result, _, _ = compile_component(
        tmp_path, prepared_payload(""), body=f"#ik.immunization-history(n, {options})"
    )
    assert result.returncode != 0
    assert diagnostic in result.stderr


@pytest.mark.parametrize("columns", [1, 2, 3])
def test_overdue_columns_preserve_items_and_dose_associations(tmp_path, columns):
    notice = prepared_payload("")
    notice["overdue_diseases"] = [
        {"disease": "Measles", "dose": 2},
        {"disease": "Mumps", "dose": 1},
        {"disease": "Uncatalogued #literal", "dose": None},
    ]
    result, _, text = compile_component(
        tmp_path,
        notice,
        body=f"#ik.overdue-diseases(n, columns: {columns}, include-dose: true)",
    )
    assert result.returncode == 0, result.stderr
    for label in ["Measles (2nd dose)", "Mumps (1st dose)", "Uncatalogued #literal"]:
        assert label in text


@pytest.mark.parametrize("columns", ["0", "-1", '"two"', "false"])
def test_overdue_invalid_column_counts_fail(tmp_path, columns):
    result, _, _ = compile_component(
        tmp_path,
        prepared_payload(""),
        body=f"#ik.overdue-agents(n, columns: {columns})",
    )
    assert result.returncode != 0
    assert "positive integer" in result.stderr


def test_history_continues_without_truncation_and_repeats_headers(tmp_path):
    source = "; ".join(
        f"{date(2020, 1, 1) + timedelta(days=i):%b %d, %Y} - MMR - Valid"
        for i in range(160)
    )
    result, view, text = compile_component(
        tmp_path,
        prepared_payload(source),
        'diseases: ("Measles",), show-validity: true',
    )
    assert result.returncode == 0, result.stderr
    assert len(view["rows"]) == 160
    assert text.count("MMR") == 160
    pdf = PdfReader(tmp_path / "result.pdf")
    assert len(pdf.pages) >= 3
    assert all(
        "Date Given" in " ".join(page.extract_text().split()) for page in pdf.pages
    )


def test_french_labels_dates_and_dose_wording(tmp_path):
    notice = prepared_payload("May 1, 2020 - MMR - Valid")
    notice["overdue_diseases"] = [{"disease": "Measles", "dose": 2}]
    result, _, text = compile_component(
        tmp_path,
        notice,
        body='#ik.overdue-diseases(n, language: "fr", include-dose: true)\n#ik.immunization-history(n, language: "fr", show-validity: true)',
    )
    assert result.returncode == 0, result.stderr
    compact = " ".join(text.split())
    for expected in (
        "Rougeole (2e dose)",
        "1 mai 2020",
        "Dose valide",
        "Dose non valide",
        "Validité inconnue",
    ):
        assert expected in compact


def test_empty_lists_do_not_invent_assessment_and_agent_view_is_separate(tmp_path):
    notice = prepared_payload("")
    notice["overdue_diseases"] = []
    notice["overdue_agents"] = ["MMR", "Literal #agent"]
    result, _, text = compile_component(
        tmp_path,
        notice,
        body="#ik.overdue-diseases(n)\n#ik.overdue-agents(n, columns: 3)",
    )
    assert result.returncode == 0, result.stderr
    assert "MMR" in text and "Literal #agent" in text
    assert "Measles" not in text


def test_many_overdue_agents_wrap_and_continue(tmp_path):
    notice = prepared_payload("")
    notice["overdue_agents"] = [
        f"Synthetic agent {index:03d} with a long literal description"
        for index in range(150)
    ]
    result, _, text = compile_component(
        tmp_path, notice, body="#ik.overdue-agents(n, columns: 3)"
    )
    assert result.returncode == 0, result.stderr
    compact = " ".join(text.split())
    for index in range(150):
        assert f"Synthetic agent {index:03d}" in compact
    assert len(PdfReader(tmp_path / "result.pdf").pages) >= 2


def test_case_sensitive_agent_exclusion_and_explicit_false_override(tmp_path):
    notice = prepared_payload("May 1, 2020 - Ig - Invalid")
    notice["rendering_defaults"]["show_validity"] = True
    result, view, text = compile_component(
        tmp_path, notice, 'ignore-agents: ("ig",), show-validity: false'
    )
    assert result.returncode == 0, result.stderr
    assert view["rows"][0]["agents"] == ["Ig"]
    assert set(view["rows"][0]["marks"].values()) == {"recorded"}
    assert "Administration recorded" in text


def test_narrow_page_has_actionable_width_diagnostic(tmp_path):
    result, _, _ = compile_component(
        tmp_path,
        prepared_payload("May 1, 2020 - MMR"),
        body="#set page(width: 200pt, margin: 10pt)\n#ik.immunization-history(n)",
    )
    assert result.returncode != 0
    assert "History columns exceed available width" in result.stderr


def test_reduced_columns_work_on_a_narrow_page(tmp_path):
    result, _, text = compile_component(
        tmp_path,
        prepared_payload("May 1, 2020 - MMR"),
        body="#set page(width: 250pt, margin: 10pt)\n#ik.immunization-history(n, diseases: (), include-other: false)",
    )
    assert result.returncode == 0, result.stderr
    assert "MMR" in text


def test_custom_labels_are_used_and_missing_required_translation_fails(tmp_path):
    notice = prepared_payload("")
    notice["overdue_diseases"] = [{"disease": "Measles", "dose": 1}]
    for name, override, succeeds in [
        ("approved", '(Measles: "Libellé approuvé",)', True),
        ("missing", "(:)", False),
    ]:
        directory = tmp_path / name
        directory.mkdir()
        result, _, text = compile_component(
            directory,
            notice,
            body=f'#ik.overdue-diseases(n, language: "fr", labels: (fr_diseases_overdue: {override}))',
        )
        if succeeds:
            assert result.returncode == 0, result.stderr
            assert "Libellé approuvé" in text
        else:
            assert result.returncode != 0
            assert "Missing fr diseases_overdue label for Measles" in result.stderr


def test_identical_translated_headings_keep_distinct_disease_cells(tmp_path):
    notice = prepared_payload("May 1, 2020 - MMR - Valid")
    result, _, text = compile_component(
        tmp_path,
        notice,
        body='#ik.immunization-history(n, diseases: ("Measles", "Mumps"), include-other: false, show-validity: false, labels: (en_diseases_chart: (Measles: "Same heading", Mumps: "Same heading")))',
    )
    assert result.returncode == 0, result.stderr
    assert text.count("Same heading") == 2
    # Two independent disease marks plus the recorded-administration legend.
    assert text.count("⬤") == 3
