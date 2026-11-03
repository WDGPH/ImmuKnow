"""Read actual package metadata and PDFs with the pinned native compiler."""

from __future__ import annotations

from immuknow.preprocess import (
    CONFIG_DIR,
    build_history_items,
    classify_dataset_validity,
    parse_history,
)
from immuknow.resources import typst_library_root

import json
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import quote

import pytest
import pymupdf
import zxingcpp
from pypdf import PdfReader
from pypdf.generic import DictionaryObject

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


def compile_package(
    tmp_path: Path, body: str, notice_overrides: dict | None = None
) -> tuple[dict, PdfReader]:
    shutil.copytree(typst_library_root(), tmp_path / "lib/immuknow")
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
            "first_initial": "É",
            "last_initial": "E",
            "address": "42 Example Street",
            "city": "Montréal",
            "province": "Québec",
            "postal_code": "A1A 1A1",
            "school": "Example School",
            "date_of_birth_iso": "",
            "age": None,
        },
        "overdue_diseases": [{"disease": "Measles", "dose": 2}],
        "overdue_agents": ["MMR"],
        "history": [
            {
                "date_given": "2020-01-01",
                "agent": "MMR",
                "display_name": "MMR",
                "mapping_known": True,
                "diseases": ["Measles"],
                "validity": validity,
            }
            for validity in ("valid", "invalid")
        ],
        "validity_coverage": "all_present",
        "history_validity_coverage": "all_present",
        "has_immunization_records": True,
    }
    overrides = dict(notice_overrides or {})
    notice["client_data"].update(overrides.pop("client_data", {}))
    notice.update(overrides)
    (tmp_path / "data.json").write_text(json.dumps(notice))
    source = tmp_path / "notice.typ"
    source.write_text(
        '#import "lib/immuknow/lib.typ" as immuknow\n'
        '#let notice = json("data.json")\n'
        "#show: immuknow.letter.with(notice: notice)\n" + body
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


def history_data(raw: str) -> dict:
    """Prepare source facts alongside normalized history for rendering tests."""
    parsed = parse_history(raw)
    return {
        "history": build_history_items(
            parsed.doses,
            json.loads((CONFIG_DIR / "vaccine_reference.json").read_text()),
        ),
        "has_immunization_records": bool(parsed.doses),
        "history_validity_coverage": classify_dataset_validity([parsed]),
        "validity_coverage": classify_dataset_validity([parsed]),
    }


def history_facts(raw: str) -> str:
    """Inject prepared history facts into an individual component call."""
    return f"#let notice = (: ..notice, ..json(bytes({json.dumps(json.dumps(history_data(raw)))})))\n"


@pytest.mark.parametrize(
    "options,expected",
    [
        ("", "fail"),
        ('ignore-agents: ("Unknown agent",),', "pass"),
        ("include-other: false,", "fail"),
        ("omit-invalid: true,", "fail"),
        ('ignore-agents: ("Unknown agent",), include-other: false,', "pass"),
    ],
)
def test_history_mapping_respects_explicit_exclusions_only(tmp_path, options, expected):
    report, _ = compile_package(
        tmp_path,
        history_facts("2020-01-01 - MMR - Valid; 2020-02-01 - Unknown agent - Invalid;")
        + f"#immuknow.immunization-history(notice, {options})",
    )
    (check,) = [
        item for item in report["checks"] if item["code"] == "content.history_mapping"
    ]
    assert check["status"] == expected
    assert check["measurements"]["unmapped_agents"] == (
        ["Unknown agent"] if expected == "fail" else []
    )


@pytest.mark.parametrize("language,expected", [("en", "pass"), ("fr", "fail")])
def test_history_mapping_uses_evaluated_typst_options(tmp_path, language, expected):
    report, _ = compile_package(
        tmp_path,
        history_facts("2020-01-01 - Unknown agent - Valid;")
        + '#immuknow.immunization-history(notice, ignore-agents: if notice.language == "en" { ("Unknown agent",) } else { () })',
        notice_overrides={"language": language},
    )
    (check,) = [
        item for item in report["checks"] if item["code"] == "content.history_mapping"
    ]
    assert check["status"] == expected


def test_ignoring_an_agent_in_one_history_does_not_waive_another_table(tmp_path):
    report, _ = compile_package(
        tmp_path,
        history_facts("2020-01-01 - Unknown agent - Valid;")
        + '#immuknow.immunization-history(notice, ignore-agents: ("Unknown agent",))\n'
        + "#immuknow.immunization-history(notice)",
    )
    checks = [
        item for item in report["checks"] if item["code"] == "content.history_mapping"
    ]
    assert [item["status"] for item in checks] == ["pass", "fail"]


@pytest.mark.parametrize(
    "helper,word", [("overdue-diseases", "Measles"), ("overdue-agents", "MMR")]
)
def test_overdue_list_indent_is_local_and_can_be_overridden(tmp_path, helper, word):
    compile_package(
        tmp_path,
        "#set list(indent: 3cm)\n"
        f"#immuknow.{helper}(notice, columns: 1)\n"
        f"#immuknow.{helper}(notice, columns: 1, indent: 1.6cm)\n"
        "#set list(indent: 0pt)\n"
        f"#immuknow.{helper}(notice, columns: 1)",
    )
    with pymupdf.open(tmp_path / "notice.pdf") as document:
        starts = [w[0] for w in document[0].get_text("words") if w[4] == word]
    assert len(starts) == 3
    assert starts[1] - starts[0] == pytest.approx(0.8 * 72 / 2.54, abs=0.01)
    assert starts[2] == pytest.approx(starts[0], abs=0.01)


@pytest.mark.parametrize("helper", ["overdue-diseases", "overdue-agents"])
@pytest.mark.parametrize("language", ["en", "fr"])
@pytest.mark.parametrize("has_records", [False, True])
def test_no_records_option_replaces_only_the_overdue_list(
    tmp_path: Path, helper: str, language: str, has_records: bool
) -> None:
    raw = "2020-01-01 - MMR;" if has_records else ""
    report, reader = compile_package(
        tmp_path,
        "Introduction stays visible.\n"
        + f'#immuknow.{helper}(notice, no-records: auto, language: "{language}")',
        notice_overrides=history_data(raw),
    )
    text = " ".join(" ".join(page.extract_text().split()) for page in reader.pages)
    message = (
        "We have no immunization records on file"
        if language == "en"
        else "Aucune vaccination n’est consignée au dossier"
    )
    assert "Introduction stays visible." in text
    assert (message in text) == (not has_records)
    assert ("MMR" in text or "Measles" in text or "Rougeole" in text) == has_records
    component = helper.replace("-", "_")
    assert report["components"][component]
    assert all(item["source_matches"] for item in report["measurements"][component])


@pytest.mark.parametrize("helper", ["overdue-diseases", "overdue-agents"])
@pytest.mark.parametrize("language", ["en", "fr"])
def test_no_records_replacement_accepts_custom_content(
    tmp_path: Path, helper: str, language: str
) -> None:
    options = (
        ", labels: (en_diseases_overdue: (:), fr_diseases_overdue: (:))"
        if helper == "overdue-diseases"
        else ""
    )
    report, reader = compile_package(
        tmp_path,
        f"#immuknow.{helper}(notice, no-records: [Please #emph[send] your records.], "
        f'language: "{language}"{options})',
        notice_overrides=history_data(""),
    )
    text = " ".join(" ".join(page.extract_text().split()) for page in reader.pages)
    assert "Please send your records." in text
    assert "MMR" not in text and "Measles" not in text
    assert not any(
        check["code"] == "content.translation_missing" for check in report["checks"]
    )


@pytest.mark.parametrize("helper", ["overdue-diseases", "overdue-agents"])
def test_no_records_replacement_is_opt_in(tmp_path: Path, helper: str) -> None:
    _, reader = compile_package(
        tmp_path, f"#immuknow.{helper}(notice)", notice_overrides=history_data("")
    )
    text = " ".join(page.extract_text() for page in reader.pages)
    assert ("Measles" if helper == "overdue-diseases" else "MMR") in text
    assert "We have no immunization records on file" not in text


@pytest.mark.parametrize(
    "has_records,diseases,agents,reader,up_to_date",
    [
        (False, [{"disease": "Measles", "dose": 2}], ["MMR"], "guardian", False),
        (True, [{"disease": "Measles", "dose": 2}], [], "student", False),
        (True, [], ["MMR"], "student", True),
        (False, [], [], "guardian", True),
        (True, [], [], None, True),
    ],
    ids=[
        "no-records",
        "overdue-disease",
        "agents-only",
        "independent-flags",
        "neutral",
    ],
)
def test_notice_flags_can_toggle_an_entire_overdue_section(
    tmp_path: Path,
    has_records: bool,
    diseases: list,
    agents: list,
    reader: str | None,
    up_to_date: bool,
) -> None:
    overrides = history_data("2020-01-01 - MMR;" if has_records else "")
    overrides.update(
        overdue_diseases=diseases,
        overdue_agents=agents,
        intended_reader=reader,
    )
    overrides["client_data"] = {
        "date_of_birth_iso": "",
    }
    body = f"""
#let flags = immuknow.notice-flags(notice)
#let to_student = flags.to_student
#let to_guardian = flags.to_guardian
#let no_records = flags.no_records
#let up_to_date = flags.up_to_date
#assert(type(to_student) == bool and type(to_guardian) == bool)
#assert(type(no_records) == bool and type(up_to_date) == bool)
#assert(to_student == {str(reader == "student").lower()})
#assert(to_guardian == {str(reader == "guardian").lower()})
#assert(no_records == {str(not has_records).lower()})
#assert(up_to_date == {str(up_to_date).lower()})
#if not no_records and not up_to_date [
  Overdue introduction.
  #immuknow.overdue-diseases(notice)
] else [Section omitted.]
"""
    report, pdf = compile_package(tmp_path, body, notice_overrides=overrides)
    text = " ".join(page.extract_text() for page in pdf.pages)
    shown = has_records and not up_to_date
    assert ("Overdue introduction." in text) == shown
    assert report["components"]["overdue_diseases"] == shown
    assert any(
        check["code"] == "component.overdue_diseases.absent"
        for check in report["checks"]
    ) == (not shown)


@pytest.mark.parametrize("has_overdue_diseases", [False, True])
def test_affirmative_template_can_assert_up_to_date(
    tmp_path: Path, has_overdue_diseases: bool
) -> None:
    body = """
#let up_to_date = immuknow.notice-flags(notice).up_to_date
#assert(up_to_date, message: "Affirmative notice requires no overdue diseases.")
Affirmative branch.
"""
    overrides = {
        "overdue_diseases": [{"disease": "Measles", "dose": 2}]
        if has_overdue_diseases
        else [],
        "overdue_agents": ["MMR"],
    }
    if has_overdue_diseases:
        with pytest.raises(
            AssertionError, match="Affirmative notice requires no overdue diseases"
        ):
            compile_package(tmp_path, body, notice_overrides=overrides)
        assert not (tmp_path / "notice.pdf").exists()
    else:
        _, pdf = compile_package(tmp_path, body, notice_overrides=overrides)
        assert "Affirmative branch." in pdf.pages[0].extract_text()


@pytest.mark.parametrize(
    "birth,as_of,diseases,expected",
    [
        ("2009-12-31", "2026-06-01", ["HPV", "Varicella"], []),
        ("2010-01-01", "2026-06-01", ["HPV", "Varicella"], ["Varicella"]),
        ("2009-12-31", "2026-06-01", ["Measles", "Varicella"], ["Measles"]),
        ("", "2026-06-01", ["Measles", "HPV"], ["Measles"]),
        ("", "", ["HPV", "Hepatitis B"], []),
        ("1996-12-31", "2026-06-01", ["Meningococcal"], []),
        ("2004-08-31", "2016-08-30", ["Meningococcal"], []),
        ("2004-08-31", "2016-08-31", ["Meningococcal"], ["Meningococcal"]),
        ("2004-09-01", "2015-01-01", ["Meningococcal"], ["Meningococcal"]),
    ],
    ids=[
        "varicella-2009",
        "varicella-2010",
        "mixed-cohorts",
        "birth-not-needed",
        "non-ispa",
        "meningococcal-before-cohort",
        "before-age-12",
        "at-age-12",
        "meningococcal-younger-cohort",
    ],
)
def test_ispa_list_and_flag_use_the_same_birth_cohort_selection(
    tmp_path: Path, birth: str, as_of: str, diseases: list[str], expected: list[str]
) -> None:
    entries = [{"disease": disease, "dose": 2} for disease in diseases]
    labels = {disease: disease for disease in diseases}
    body = (
        "#let flags = immuknow.notice-flags(notice, include-ispa: true)\n"
        f"#assert(flags.up_to_date == {str(not diseases).lower()})\n"
        f"#assert(flags.ispa_up_to_date == {str(not expected).lower()})\n"
        f"#let labels = (en_diseases_overdue: json(bytes({json.dumps(json.dumps(labels))})))\n"
        'Full list: #immuknow.overdue-diseases(notice, style: "comma-separated", labels: labels)\n'
        "Filtered: #immuknow.overdue-diseases(notice, ispa-only: true, "
        'include-dose: true, style: "comma-separated", labels: labels) End filtered.'
    )
    report, pdf = compile_package(
        tmp_path,
        body,
        notice_overrides={
            "client_data": {"date_of_birth_iso": birth},
            "date_as_of": as_of,
            "overdue_diseases": entries,
        },
    )
    text = " ".join(" ".join(page.extract_text().split()) for page in pdf.pages)
    filtered = text.split("Filtered:")[1].split("End filtered.")[0]
    for disease in diseases:
        assert (disease in filtered) == (disease in expected)
    assert ("2nd dose" in filtered) == bool(expected)
    assert report["notice"]["overdue_diseases"] == entries
    assert all(
        item["source_matches"] for item in report["measurements"]["overdue_diseases"]
    )


@pytest.mark.parametrize(
    "body",
    [
        "#immuknow.overdue-diseases(notice, ispa-only: true)",
        "#let flags = immuknow.notice-flags(notice, include-ispa: true)\n#flags.ispa_up_to_date",
    ],
)
def test_ispa_operations_reject_missing_required_birth_date(
    tmp_path: Path, body: str
) -> None:
    with pytest.raises(
        AssertionError, match="ISPA disease selection requires a valid birth date"
    ):
        compile_package(
            tmp_path,
            body,
            notice_overrides={
                "client_data": {"date_of_birth_iso": ""},
                "overdue_diseases": [{"disease": "Varicella", "dose": 2}],
            },
        )


def test_non_ispa_notices_do_not_require_birth_cohort_data(tmp_path: Path) -> None:
    _, pdf = compile_package(
        tmp_path,
        "#let flags = immuknow.notice-flags(notice)\n"
        "#assert(not flags.up_to_date)\n"
        '#assert("ispa_up_to_date" not in flags)\n'
        "#immuknow.overdue-diseases(notice)",
        notice_overrides={
            "client_data": {"date_of_birth_iso": ""},
            "overdue_diseases": [{"disease": "Varicella", "dose": 2}],
        },
    )
    assert "Varicella" in pdf.pages[0].extract_text()


def test_ispa_requires_as_of_date_for_an_age_dependent_cohort(tmp_path: Path) -> None:
    with pytest.raises(
        AssertionError, match="requires date_as_of for this birth cohort"
    ):
        compile_package(
            tmp_path,
            "#immuknow.overdue-diseases(notice, ispa-only: true)",
            notice_overrides={
                "client_data": {"date_of_birth_iso": "2000-01-01"},
                "date_as_of": "",
                "overdue_diseases": [{"disease": "Meningococcal", "dose": 1}],
            },
        )


@pytest.mark.parametrize("has_records", [False, True])
def test_ispa_only_agents_error_even_when_no_records_message_is_enabled(
    tmp_path: Path, has_records: bool
) -> None:
    with pytest.raises(
        AssertionError, match="ispa-only is not supported for overdue-agents"
    ):
        compile_package(
            tmp_path,
            "#immuknow.overdue-agents(notice, ispa-only: true, no-records: auto)",
            notice_overrides=history_data("2020-01-01 - MMR;" if has_records else ""),
        )


@pytest.mark.parametrize(
    "birth,diseases,should_render",
    [
        ("2009-12-31", ["Varicella"], False),
        ("2010-01-01", ["Varicella"], True),
        ("2010-01-01", ["HPV"], False),
        ("2010-01-01", ["HPV", "Measles"], True),
    ],
)
def test_suspension_assertion_requires_an_applicable_ispa_disease(
    tmp_path: Path, birth: str, diseases: list[str], should_render: bool
) -> None:
    body = """
#let ispa_up_to_date = immuknow.notice-flags(notice, include-ispa: true).ispa_up_to_date
#assert(not ispa_up_to_date, message: "Suspension notice requires an applicable overdue ISPA disease.")
#immuknow.overdue-diseases(notice, ispa-only: true)
"""
    overrides = {
        "client_data": {"date_of_birth_iso": birth},
        "overdue_diseases": [{"disease": disease, "dose": 2} for disease in diseases],
    }
    if should_render:
        _, pdf = compile_package(tmp_path, body, notice_overrides=overrides)
        text = " ".join(page.extract_text() for page in pdf.pages)
        assert "HPV" not in text
    else:
        with pytest.raises(
            AssertionError,
            match="Suspension notice requires an applicable overdue ISPA disease",
        ):
            compile_package(tmp_path, body, notice_overrides=overrides)
        assert not (tmp_path / "notice.pdf").exists()


@pytest.mark.parametrize(
    "body,https,multiple",
    [
        ("No links", "not_applicable", "not_applicable"),
        (
            '#immuknow.link("https://example.org/records")[Records]',
            "pass",
            "pass",
        ),
        (
            '#immuknow.link("https://example.org/records")[Records] ' * 2,
            "pass",
            "pass",
        ),
        (
            '#immuknow.link("https://example.org/records")[Records] '
            '#immuknow.qr-code(notice, url: "https://example.org/records")',
            "pass",
            "pass",
        ),
        (
            '#immuknow.link("https://example.org/records")[Records] '
            '#immuknow.qr-code(notice, url: "https://example.org/update")',
            "pass",
            "warn",
        ),
        (
            '#immuknow.link("https://example.org/records")[Records] '
            '#immuknow.link("mailto:records@example.org")[Email] '
            '#immuknow.link("tel:+15555550100")[Call]',
            "pass",
            "warn",
        ),
        (
            '#immuknow.link("mailto:records@example.org")[Email]',
            "not_applicable",
            "pass",
        ),
        (
            '#immuknow.link("http://example.org/records")[Records]',
            "warn",
            "pass",
        ),
        ('#immuknow.link("https:///records")[Records]', "warn", "pass"),
        (
            '#immuknow.link("https://example.org/has space")[Records]',
            "warn",
            "pass",
        ),
        ('#immuknow.link("https://exämple.org/élève")[Records]', "pass", "pass"),
    ],
)
def test_placed_links_get_basic_https_and_multiple_destination_findings(
    tmp_path, body, https, multiple
):
    report, _ = compile_package(tmp_path, body)
    checks = {check["code"]: check for check in report["checks"]}
    assert checks["content.link_https"]["status"] == https
    assert checks["content.multiple_links"]["status"] == multiple
    if multiple == "warn":
        assert (
            "different link destinations" in checks["content.multiple_links"]["message"]
        )


@pytest.mark.parametrize("label", ["Read the record", "Consultez votre dossier"])
@pytest.mark.parametrize(
    "option", ["", ", keep-together: true", ", keep-together: false"]
)
def test_link_labels_stay_together_by_default_with_a_wrapping_opt_out(
    tmp_path, label, option
):
    report, reader = compile_package(
        tmp_path,
        "#set page(width: 200pt, height: 150pt, margin: 20pt, footer: none)\n"
        '#set text(font: "FreeSans", size: 10pt)\n'
        "#box(width: 110pt)[Before] "
        f'#immuknow.link("https://example.org/records"{option})[{label}] After',
    )
    checks = [
        check for check in report["checks"] if check["code"] == "layout.link_width"
    ]
    keep_together = "false" not in option
    assert [check["status"] for check in checks] == (["pass"] if keep_together else [])
    with pymupdf.open(tmp_path / "notice.pdf") as pdf:
        words = pdf[0].get_text("words")
    before = next(word for word in words if word[4] == "Before")
    linked = [word for word in words if word[4] in label.split()]
    after = next(word for word in words if word[4] == "After")
    assert len(linked) == len(label.split())
    if keep_together:
        assert len({(word[5], word[6]) for word in linked}) == 1
        assert linked[0][1] > before[1]
        assert after[1] == pytest.approx(linked[0][1])
    else:
        assert len({(word[5], word[6]) for word in linked}) > 1
        assert linked[0][1] == pytest.approx(before[1])
    assert reader.pages[0].annotations
    assert (
        reader.pages[0].annotations[0].get_object()["/A"]["/URI"]
        == "https://example.org/records"
    )


@pytest.mark.parametrize(
    "option", ["", ", keep-together: false", ", keep-together: true"]
)
def test_oversized_link_wraps_with_its_complete_text_and_destination(tmp_path, option):
    label = "Read the record information"
    report, reader = compile_package(
        tmp_path,
        "#set page(width: 200pt, height: 150pt, margin: 20pt, footer: none)\n"
        '#set text(font: "FreeSans", size: 10pt)\n'
        f'#block(width: 65pt)[#immuknow.link("https://example.org/records"{option})[{label}]]',
    )
    checks = [
        check for check in report["checks"] if check["code"] == "layout.link_width"
    ]
    assert [check["status"] for check in checks] == (
        [] if "false" in option else ["warn"]
    )
    with pymupdf.open(tmp_path / "notice.pdf") as pdf:
        words = pdf[0].get_text("words")
    assert [word[4] for word in words] == label.split()
    assert len({(word[5], word[6]) for word in words}) > 1
    assert all(word[2] <= 85.1 for word in words)
    assert reader.pages[0].annotations
    assert all(
        annotation.get_object()["/A"]["/URI"] == "https://example.org/records"
        for annotation in reader.pages[0].annotations
    )


@pytest.mark.parametrize("explicit_breaks", [False, True])
def test_long_kept_labels_can_continue_across_pages_without_losing_text(
    tmp_path, explicit_breaks
):
    phrase = (
        "Read record" if explicit_breaks else "Read the vaccination record information"
    )
    label = (phrase + ("#linebreak()" if explicit_breaks else " ")) * 20
    report, reader = compile_package(
        tmp_path,
        "#set page(width: 200pt, height: 150pt, margin: 20pt, footer: none)\n"
        '#set text(font: "FreeSans", size: 10pt)\n'
        f'#immuknow.link("https://example.org/records", keep-together: true)[{label}]',
    )
    assert len(reader.pages) > 1
    words = " ".join(" ".join(page.extract_text().split()) for page in reader.pages)
    assert words == " ".join([phrase] * 20)
    assert any(
        check["code"] == "layout.link_width"
        and check["status"] == ("pass" if explicit_breaks else "warn")
        for check in report["checks"]
    )


def test_reused_kept_link_checks_each_enclosing_width_independently(tmp_path):
    report, _ = compile_package(
        tmp_path,
        '#let kept = immuknow.link("https://example.org/records", keep-together: true)[Read the record information]\n'
        "#block(width: 160pt)[#kept]\n#block(width: 65pt)[#kept]",
    )
    checks = [
        check for check in report["checks"] if check["code"] == "layout.link_width"
    ]
    assert [check["status"] for check in checks] == ["pass", "warn"]
    assert len(report["measurements"]["link"]) == 2


def test_package_import_and_unused_history_require_no_facts(tmp_path: Path) -> None:
    shutil.copytree(typst_library_root(), tmp_path / "lib/immuknow")
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


@pytest.mark.parametrize("language", ["en", "fr"])
@pytest.mark.parametrize(
    "raw,options,marker",
    [
        ("", "", None),
        ("2020-01-01 - MMR;", "", None),
        ("2020-01-01 - HB-unspecified;", "", "HB*"),
        ("2020-01-01 - men-AC unspecified;", "", "men-AC*"),
        (
            "2020-01-01 - HB-unspecified; 2020-01-01 - MMR;",
            'ignore-agents: ("HB-unspecified",),',
            None,
        ),
        (
            "2020-01-01 - HB-unspecified - Invalid; 2020-01-01 - MMR - Valid;",
            "show-validity: true, omit-invalid: true,",
            None,
        ),
        (
            "2020-01-01 - HB-unspecified - Invalid; 2020-01-01 - MMR - Valid;",
            "show-validity: true,",
            "HB*",
        ),
    ],
    ids=["empty", "specified", "hyphen", "space", "ignored", "omitted", "mixed"],
)
def test_history_unspecified_footnote_follows_displayed_agents(
    tmp_path: Path, language: str, raw: str, options: str, marker: str | None
) -> None:
    _, reader = compile_package(
        tmp_path,
        history_facts(raw)
        + f'#immuknow.immunization-history(notice, language: "{language}", {options})',
    )
    text = " ".join(page.extract_text() for page in reader.pages)
    footnote = (
        "*Vaccine formulation not specified"
        if language == "en"
        else "*Formulation du vaccin non précisée"
    )
    assert (footnote in text) == (marker is not None)
    if marker is not None:
        assert marker in text
    else:
        assert "HB*" not in text and "men-AC*" not in text


@pytest.mark.parametrize("language", ["en", "fr"])
@pytest.mark.parametrize(
    "raw,options,valid,invalid",
    [
        ("", "", False, False),
        ("2020-01-01 - MMR - Valid;", "", True, False),
        ("2020-01-01 - MMR - Invalid;", "", False, True),
        (
            "2020-01-01 - MMR - Valid; 2020-02-01 - HB - Invalid;",
            "",
            True,
            True,
        ),
        (
            "2020-01-01 - MMR - Valid; 2020-02-01 - HB - Invalid;",
            "omit-invalid: true,",
            True,
            False,
        ),
        (
            "2020-01-01 - MMR - Valid; 2020-02-01 - HB - Invalid;",
            'ignore-agents: ("MMR",),',
            False,
            True,
        ),
        ("2020-01-01 - MMR - Valid;", "include-other: false,", False, False),
    ],
    ids=["empty", "valid", "invalid", "both", "omitted", "ignored", "no-marks"],
)
def test_history_validity_legend_follows_visible_marks(
    tmp_path: Path, language: str, raw: str, options: str, valid: bool, invalid: bool
) -> None:
    _, reader = compile_package(
        tmp_path,
        history_facts(raw)
        + f'#immuknow.immunization-history(notice, language: "{language}", '
        f"{options})",
    )
    text = " ".join(" ".join(page.extract_text().split()) for page in reader.pages)
    valid_label, invalid_label = (
        (
            "Dose counts toward vaccination requirements",
            "Dose does not count toward vaccination requirements",
        )
        if language == "en"
        else (
            "Dose prise en compte dans les exigences de vaccination",
            "Dose non prise en compte dans les exigences de vaccination",
        )
    )
    assert (valid_label in text) == valid
    assert (invalid_label in text) == invalid


@pytest.mark.parametrize(
    "options", ["", 'ignore-agents: ("MMR",),', "omit-invalid: true,"]
)
def test_validity_display_rejects_missing_values_before_filtering(
    tmp_path: Path, options: str
) -> None:
    raw = "2020-01-01 - MMR; 2020-02-01 - HB - Valid;"
    with pytest.raises(
        AssertionError, match="Validity display requires Valid or Invalid"
    ):
        compile_package(
            tmp_path,
            history_facts(raw)
            + f"#immuknow.immunization-history(notice, show-validity: true, {options})",
        )
    assert not (tmp_path / "notice.pdf").exists()


@pytest.mark.parametrize("language", ["en", "fr"])
def test_partial_history_can_explicitly_disable_validity(
    tmp_path: Path, language: str
) -> None:
    _, reader = compile_package(
        tmp_path,
        history_facts("2020-01-01 - MMR; 2020-02-01 - HB - Invalid;")
        + f'#immuknow.immunization-history(notice, language: "{language}", show-validity: false)',
    )
    text = " ".join(page.extract_text() for page in reader.pages)
    assert "MMR" in text and "HB" in text and "⬤" in text
    assert "?" not in text and "○" not in text
    assert "vaccination requirements" not in text
    assert "exigences de vaccination" not in text


@pytest.mark.parametrize("show_validity", [None, False, True])
@pytest.mark.parametrize("language", ["en", "fr"])
def test_unflagged_history_is_displayed_as_recorded_doses(
    tmp_path: Path, show_validity: bool | None, language: str
) -> None:
    raw = "2020-01-01 - MMR;"
    options = (
        "" if show_validity is None else f"show-validity: {str(show_validity).lower()},"
    )
    report, reader = compile_package(
        tmp_path,
        history_facts(raw)
        + f'#immuknow.immunization-history(notice, language: "{language}", '
        f"{options})",
    )
    text = " ".join(page.extract_text() for page in reader.pages)
    assert "MMR" in text and "⬤" in text
    assert "?" not in text and "○" not in text
    assert "vaccination requirements" not in text
    assert "exigences de vaccination" not in text
    assert not any(
        check["code"] == "content.history_validity" and check["status"] != "pass"
        for check in report["checks"]
    )


@pytest.mark.parametrize("language", ["en", "fr"])
def test_history_legend_labels_can_be_overridden(tmp_path: Path, language: str) -> None:
    raw = "2020-01-01 - HB-unspecified - Valid; 2020-02-01 - MMR - Invalid;"
    _, reader = compile_package(
        tmp_path,
        history_facts(raw)
        + f'#immuknow.immunization-history(notice, language: "{language}", '
        'show-validity: true, legend-labels: (valid: "Counts for this notice", '
        'invalid: [Does #emph[not] count], unspecified: "*Formulation not specified"))',
    )
    text = " ".join(" ".join(page.extract_text().split()) for page in reader.pages)
    for label in (
        "Counts for this notice",
        "Does not count",
        "*Formulation not specified",
    ):
        assert label in text
    assert "vaccination requirements" not in text
    assert "exigences de vaccination" not in text
    assert "Vaccine formulation not specified" not in text
    assert "Formulation du vaccin non précisée" not in text


@pytest.mark.parametrize("show_history", [False, True])
@pytest.mark.parametrize(
    "base,query_start,fragment",
    [
        ("https://example.test/record", "?", ""),
        ("https://example.test/record#details", "?", "#details"),
        ("https://example.test/record?lang=fr#details", "?lang=fr&", "#details"),
    ],
)
def test_placed_history_and_qr_share_honest_evidence(
    tmp_path: Path,
    show_history: bool,
    base: str,
    query_start: str,
    fragment: str,
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
    body = body.replace('"https://example.test/record"', json.dumps(base))
    report, reader = compile_package(tmp_path, body)
    expected_url = (
        "https://example.test/record"
        + query_start
        + "id=1234567890&name="
        + quote("Éloïse & 50% $(hello)", safe="")
        + fragment
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
        "row_key": "row-1",
        "template": "test.en.typ",
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
            "Dose counts toward vaccination requirements",
            "Dose does not count toward vaccination requirements",
        ):
            assert expected in text
        assert "?" not in text
        assert "Validity unknown" not in text
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


@pytest.mark.parametrize(
    "destination,expected",
    [
        ("https://example.org/records", "pass"),
        ("HTTPS://example.org:8443/records?name=Jane%20Doe#info", "pass"),
        ("https://exämple.org/élève", "pass"),
        ("mailto:privacy@example.org", "pass"),
        ("mailto:privacy@example.org?subject=My%20record", "pass"),
        ("tel:1-800-555-0100", "pass"),
        ("tel:+18005550100;ext=1234", "pass"),
        ("http://example.org", "warn"),
        ("ftp://example.org", "warn"),
        ("javascript:alert(1)", "warn"),
        ("example.org", "warn"),
        ("https:///records", "warn"),
        ("https://example.org/has space", "warn"),
        ("mailto:", "warn"),
        ("mailto:privacy", "warn"),
        ("mailto:privacy@@example.org", "warn"),
        ("mailto:privacy@example.org extra", "warn"),
        ("tel:", "warn"),
        ("tel:call-me", "warn"),
        ("tel:1-800-555-0100 ext. 1234", "warn"),
        ("tel:+18005550100;ext=", "warn"),
    ],
)
def test_link_destination_formats(tmp_path, destination, expected):
    report, _ = compile_package(
        tmp_path, f"#immuknow.link({json.dumps(destination)})[Contact]"
    )
    check = next(c for c in report["checks"] if c["code"] == "content.link_destination")
    assert check["status"] == expected


def test_link_and_privacy_contacts_keep_pdf_evidence(tmp_path):
    report, reader = compile_package(
        tmp_path,
        '#immuknow.link("https://example.org")[Record]\n'
        "#immuknow.privacy-notice[Call "
        '#immuknow.link("tel:+18005550100;ext=1234")[1-800-555-0100 ext. 1234] or '
        '#immuknow.link("mailto:privacy@example.org").]',
    )
    urls = {m["url"] for m in report["measurements"]["link"]}
    assert urls == {
        "https://example.org",
        "tel:+18005550100;ext=1234",
        "mailto:privacy@example.org",
    }
    pdf_urls = {
        a.get_object().get("/A", {}).get("/URI")
        for a in reader.pages[0].get("/Annots", [])
    }
    assert urls <= pdf_urls


def test_qr_destination_uses_initials(tmp_path: Path) -> None:
    report, reader = compile_package(
        tmp_path,
        """
#immuknow.qr-code(notice, url: n => immuknow.query-url(
  "https://example.test/record",
  (first: n.client_data.first_initial, last: n.client_data.last_initial)))
""",
    )
    expected = "https://example.test/record?first=%C3%89&last=E"
    assert report["qr_urls"] == [expected]
    annotations = reader.pages[0].annotations
    assert annotations
    assert annotations[0].get_object()["/A"]["/URI"] == expected
    with pymupdf.open(tmp_path / "notice.pdf") as pdf:
        pixmap = pdf[0].get_pixmap(dpi=200, colorspace=pymupdf.csGRAY)
        pixels = memoryview(pixmap.samples).cast("B", [pixmap.height, pixmap.width])
        assert [code.text for code in zxingcpp.read_barcodes(pixels)] == [expected]
