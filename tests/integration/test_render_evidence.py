"""Real PDFs survive invalid evidence and cannot be released by deleting findings."""

import json
import subprocess
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest
import pymupdf
import zxingcpp
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, StreamObject

from immuknow import bundle_pdfs, compile_notices, run_report
from immuknow.orchestrator import run_pipeline
from tests.fixtures.sample_input import create_test_input_dataframe
from tests.integration.test_native_project import prepare_case, compile_case
from tests.integration.test_run_accounting import prepare_inputs

pytestmark = pytest.mark.integration


def test_multiple_link_warning_can_be_reviewed_or_configured_on_saved_notices(tmp_path):
    source, config, templates, _ = prepare_inputs(tmp_path)
    frame = create_test_input_dataframe(num_clients=1)
    frame["overdue_disease"] = "Measles - 2"
    frame["overdue_agent"] = "M"
    frame.to_csv(source, index=False)
    saved = run_pipeline(
        source,
        tmp_path / "runs",
        config_dir=config,
        notice_template=templates / "overdue_agents_v1.en.typ",
    )
    record = json.loads(saved.read_text())
    entry = record["entries"][0]
    assert entry["routing"]["destination"] == "review"
    checks = {check["code"]: check for check in entry["checks"]}
    assert checks["content.multiple_links"]["status"] == "warn"
    assert checks["content.link_https"]["status"] == "pass"
    original = (saved.parent / entry["original"]["path"]).read_bytes()
    entry["checks"] = [
        check for check in entry["checks"] if check["code"] != "content.multiple_links"
    ]
    run_report.write_report(saved.parent, record)
    restored = bundle_pdfs.bundle_run(saved.parent)
    assert any(
        check["code"] == "content.multiple_links" and check["status"] == "warn"
        for check in restored["evaluations"][entry["row_key"]]["results"]
    )
    assert (
        json.loads(saved.read_text())["entries"][0]["routing"]["destination"]
        == "review"
    )
    attempt = bundle_pdfs.bundle_run(
        saved.parent,
        policy={
            "rules": {
                "content.multiple_links": {
                    "severity": "fail",
                    "reason": "Use one destination",
                }
            }
        },
    )
    assert (
        "content.multiple_links"
        in attempt["evaluations"][entry["row_key"]]["failed_checks"]
    )
    attempt = bundle_pdfs.bundle_run(
        saved.parent,
        policy={
            "rules": {
                "content.multiple_links": {
                    "enabled": False,
                    "reason": "These destinations are intentional",
                }
            }
        },
    )
    assert attempt["status"] == "completed"
    after = json.loads(saved.read_text())
    assert after["entries"][0]["routing"]["destination"] == "delivery"
    assert (saved.parent / entry["original"]["path"]).read_bytes() == original
    assert record["delivery_attempts"][0] == after["delivery_attempts"][0]


def test_saved_run_ignores_retired_pdf_checks_but_preserves_history(tmp_path):
    source, config, templates, _ = prepare_inputs(tmp_path)
    saved = run_pipeline(
        source,
        tmp_path / "runs",
        config_dir=config,
        notice_template=templates / "overdue_agents_v1.en.typ",
    )
    record = json.loads(saved.read_text())
    entry = record["entries"][0]
    retired = {
        "code": "output.evidence_matches",
        "stage": "output",
        "status": "fail",
        "message": "Historical PDF check failed",
    }
    entry["checks"].append(retired)
    run_report.write_report(saved.parent, record)
    attempt = bundle_pdfs.bundle_run(saved.parent)
    assert attempt["status"] == "completed"
    evaluation = attempt["evaluations"][entry["row_key"]]
    assert "output.evidence_matches" not in evaluation["failed_checks"]
    assert all(
        check["code"] != "output.evidence_matches" for check in evaluation["results"]
    )
    current = json.loads(saved.read_text())
    assert retired in current["entries"][0]["checks"]
    assert (
        current["entries"][0]["routing"]["destination"]
        == entry["routing"]["destination"]
    )
    assert current["delivery_attempts"][0] == record["delivery_attempts"][0]


@pytest.mark.parametrize("language", ["en", "fr"])
def test_custom_labels_and_repeated_client_blocks_match_the_pdf(tmp_path, language):
    job, payload = prepare_case(tmp_path, language=language)
    payload["client_data"]["name"] = "Élodie O’Connor"
    payload["client_data"]["address"] = "123 Main Street\nApartment 20"
    payload["client_data"]["school"] = (
        "École des élèves de la vallée et du quartier nord"
    )
    job.data.write_text(json.dumps(payload))
    job.template.write_text(
        '#import "settings.typ": *\n#show: letter\n'
        '#immuknow.client-block(notice, id-label: "Record number", school-label: "Learning centre")\n'
        '#pagebreak()\n#immuknow.client-block(notice, id-label: "Dossier")\n'
        "#pagebreak()\n#immuknow.address-block(notice)"
    )
    summary, reader = compile_case(job)
    assert "Client ID:" not in reader.pages[0].extract_text()
    assert "Identifiant du client:" not in reader.pages[0].extract_text()
    assert len(summary["measurements"]["client"]) == 2
    assert len(summary["measurements"]["address"]) == 3
    assert [
        c["status"]
        for c in summary["checks"]
        if c["code"] == "layout.client_details_in_window"
    ] == ["pass", "not_applicable"]
    assert [
        c["status"]
        for c in summary["checks"]
        if c["code"] == "layout.envelope_window_missing"
    ] == ["pass"]


@pytest.mark.parametrize(
    "version,language",
    [
        ("overdue_diseases_v1", "en"),
        ("overdue_diseases_v1", "fr"),
        ("overdue_agents_v1", "en"),
        ("overdue_agents_v1", "fr"),
        ("affirmative_schedule_v1", "en"),
        ("suspension_order_v1", "en"),
    ],
)
def test_unspecified_window_warns_without_claiming_a_fit(tmp_path, version, language):
    job, _ = prepare_case(tmp_path, version=version, language=language)
    settings = job.template.parent / "settings.typ"
    settings.write_text(
        "\n".join(
            "#let envelope-window = none"
            if line.startswith("#let envelope-window =")
            else line
            for line in settings.read_text().splitlines()
        )
        + "\n"
    )
    summary, _ = compile_case(job)
    assert [
        c["status"]
        for c in summary["checks"]
        if c["code"] == "layout.envelope_window_missing"
    ] == ["warn"]
    for code in ("layout.address_outside_window", "layout.client_details_in_window"):
        assert [c["status"] for c in summary["checks"] if c["code"] == code] == [
            "not_applicable"
        ]
    assert all(
        not any(key.startswith("window_") for key in area)
        for area in summary["measurements"]["address"]
    )


@pytest.mark.parametrize(
    "body,warning",
    [("#immuknow.address-block(notice)", True), ("General information.", False)],
)
def test_window_warning_depends_on_placed_addresses(tmp_path, body, warning):
    job, _ = prepare_case(tmp_path)
    job.template.write_text('#import "settings.typ": *\n#show: letter\n' + body)
    summary, _ = compile_case(job)
    assert [
        c["status"]
        for c in summary["checks"]
        if c["code"] == "layout.envelope_window_missing"
    ] == (["warn"] if warning else [])


@pytest.mark.parametrize("language", ["en", "fr"])
@pytest.mark.parametrize(
    "placement,spacing", [("right", 0), ("right", -80), ("below", 0), ("below", -30)]
)
def test_client_details_overlap_is_reported_from_the_placed_pdf(
    tmp_path, language, placement, spacing
):
    job, payload = prepare_case(tmp_path, language=language)
    job.template.write_text(
        '#import "settings.typ": *\n#show: letter\n'
        f'#immuknow.client-block(notice, details: "{placement}", spacing: {spacing}pt, '
        "window: (x: 63pt, y: 120pt, width: 324pt, height: 81pt, padding: 11pt))"
    )
    summary, _ = compile_case(job)
    check = next(
        c for c in summary["checks"] if c["code"] == "layout.client_details_in_window"
    )
    assert check["status"] == ("warn" if spacing < 0 else "pass")
    assert (
        next(
            c for c in summary["checks"] if c["code"] == "layout.address_outside_window"
        )["status"]
        == "pass"
    )
    assert len(summary["measurements"]["client"]) == 1
    with pymupdf.open(job.pdf) as pdf:
        private_text = pdf[0].search_for(job.client_id) + pdf[0].search_for(
            payload["client_data"]["school"]
        )
        assert private_text
        assert any(
            pymupdf.Rect(63, 120, 387, 201).intersects(rect) for rect in private_text
        ) == (spacing < 0)


@pytest.mark.parametrize("language", ["en", "fr"])
@pytest.mark.parametrize("show", [True, False])
def test_blank_or_hidden_client_details_match_the_pdf(tmp_path, language, show):
    job, payload = prepare_case(tmp_path, language=language)
    payload["client_data"]["date_of_birth_iso"] = ""
    payload["client_data"]["school"] = "" if show else "School should not appear"
    job.data.write_text(json.dumps(payload))
    job.template.write_text(
        '#import "settings.typ": *\n#show: letter\n'
        f"#immuknow.client-block(notice, show-birth-date: {str(show).lower()}, show-school: {str(show).lower()})"
    )
    _, reader = compile_case(job)
    assert "School should not appear" not in reader.pages[0].extract_text()


def test_component_for_another_row_cannot_repeat_the_same_external_id(tmp_path):
    job, _ = prepare_case(tmp_path)
    job.template.write_text(
        '#import "settings.typ": *\n#show: letter\n'
        "#immuknow.client-block(notice)\n#pagebreak()\n"
        '#immuknow.client-block((..notice, row_key: "row-000002"))'
    )
    with pytest.raises(ValueError, match="different source row"):
        compile_case(job)
    assert job.pdf.is_file()


@pytest.mark.parametrize("blank_id", [False, True])
@pytest.mark.parametrize("change_row", [False, True])
@pytest.mark.parametrize(
    "content",
    [
        "address-block(other)",
        "immunization-history(other)",
        "overdue-diseases(other)",
        "overdue-diseases(other, no-records: auto)",
        "overdue-agents(other)",
        "overdue-agents(other, no-records: auto)",
        'qr-code(other, url: "https://example.test/record")',
    ],
)
def test_placed_personal_content_must_use_the_prepared_notice(
    tmp_path, content, blank_id, change_row
):
    job, payload = prepare_case(tmp_path)
    if blank_id:
        payload["client_id"] = ""
        job.data.write_text(json.dumps(payload))
        job = replace(job, client_id="")
    job.template.write_text(
        '#import "settings.typ": *\n#show: letter\n'
        "#immuknow.client-block(notice)\n"
        f"#let other = (..notice, row_key: {json.dumps('row-000002' if change_row else job.sequence)},\n"
        '  client_data: (..notice.client_data, name: "Morgan Example", address: "88 Other Road"),\n'
        '  history_validity_coverage: "all_present", has_immunization_records: false,\n'
        '  history: ((date_given: "2018-03-04", agent: "IPV", display_name: "Other vaccine", diseases: ("Polio",), validity: "valid", mapping_known: true),),\n'
        '  overdue_diseases: ((disease: "Polio", dose: 1),), overdue_agents: ("Other vaccine",))\n'
        f"#immuknow.{content}"
    )
    reason = "different source row" if change_row else "changed notice data"
    with pytest.raises(ValueError, match=reason):
        compile_case(job)
    assert job.pdf.is_file()

    marker = {
        "address-block": "Morgan Example",
        "immunization-history": "Other vaccine",
        "overdue-diseases": "Polio",
        "overdue-agents": "Other vaccine",
        "qr-code": None,
    }[content.split("(")[0]]
    if "no-records: auto" in content:
        marker = "We have no immunization records on file"
    if marker:
        assert marker in "".join(
            page.extract_text() for page in PdfReader(job.pdf).pages
        )


def test_changing_both_the_report_and_components_cannot_replace_source_facts(tmp_path):
    job, _ = prepare_case(tmp_path)
    job.template.write_text(
        '#import "settings.typ": *\n'
        '#let changed = (..notice, client_data: (..notice.client_data, name: "Morgan Example"))\n'
        "#show: immuknow.letter.with(notice: changed)\n"
        "#immuknow.client-block(changed)"
    )
    with pytest.raises(ValueError, match="differs from the prepared notice"):
        compile_case(job)
    assert "Morgan Example" in PdfReader(job.pdf).pages[0].extract_text()


@pytest.mark.parametrize(
    "level,capacity,version",
    [("l", 16, 1), ("m", 13, 1), ("q", 10, 1), ("h", 6, 1), ("l", 229, 9)],
)
@pytest.mark.parametrize("extra", [0, 1])
def test_unicode_qr_chooses_a_size_that_fits_its_encoding(
    tmp_path, level, capacity, version, extra
):
    value = "é" + "a" * (capacity + extra - 2)
    job, _ = prepare_case(tmp_path)
    job.template.write_text(
        '#import "settings.typ": *\n#show: letter\n'
        f'#immuknow.qr-code(notice, url: {json.dumps(value, ensure_ascii=False)}, error-correction: "{level}")'
    )
    compile_case(job)
    with pymupdf.open(job.pdf) as pdf:
        pixmap = pdf[0].get_pixmap(dpi=300, colorspace=pymupdf.csGRAY)
        pixels = memoryview(pixmap.samples).cast("B", [pixmap.height, pixmap.width])
        decoded = zxingcpp.read_barcodes(pixels)
    assert len(decoded) == 1
    assert decoded[0].bytes == value.encode("utf-8")
    assert decoded[0].text == value
    details = decoded[0].extra
    assert isinstance(details, dict)
    assert details["Version"] == str(version + extra)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.org/record#form",
        "https://exämple.org/élève?name=Élodie",
        "mailto:records@example.org?subject=Record",
        "tel:+18005550100",
    ],
)
def test_placed_link_report_records_destinations_without_a_qr_code(tmp_path, url):
    job, _ = prepare_case(tmp_path)
    job.template.write_text(
        '#import "settings.typ": *\n#show: letter\n'
        "#immuknow.client-block(notice)\n#pagebreak()\n"
        f"#immuknow.link({json.dumps(url, ensure_ascii=False)})\n\n"
        f"#immuknow.link({json.dumps(url, ensure_ascii=False)})[Read the record information and complete the requested information for the health unit.]"
    )
    summary, _ = compile_case(job)
    assert not summary["qr_urls"]
    assert summary["measurements"]["link"] == [{"page": 2, "url": url}] * 2


@pytest.mark.parametrize("keep_together", [None, False, True])
def test_link_evidence_follows_an_automatic_page_break(tmp_path, keep_together):
    job, _ = prepare_case(tmp_path)
    option = (
        ""
        if keep_together is None
        else f", keep-together: {str(keep_together).lower()}"
    )
    job.template.write_text(
        '#import "settings.typ": *\n#show: letter\n'
        '#let unused = immuknow.link("https://example.org/unused")\n'
        "#immuknow.client-block(notice)\n#v(500pt)\n"
        '#text(size: 40pt)[#immuknow.link("https://example.org/record"'
        f"{option})[Read the record]]"
    )
    summary, _ = compile_case(job)
    assert summary["measurements"]["link"] == [
        {"page": 2, "url": "https://example.org/record"}
    ]


def test_oversized_kept_link_records_a_reviewable_warning_in_native_evidence(tmp_path):
    job, _ = prepare_case(tmp_path)
    job.template.write_text(
        '#import "settings.typ": *\n#show: letter\n'
        "#immuknow.client-block(notice)\n"
        '#block(width: 65pt)[#immuknow.link("https://example.org/record")[Read the record information]]'
    )
    summary, reader = compile_case(job)
    checks = {check["code"]: check for check in summary["checks"]}
    assert checks["layout.link_width"]["status"] == "warn"
    assert checks["layout.link_width"]["component"] == "link"
    assert checks["layout.link_width"]["page"] == 1
    assert "Read the record information" in " ".join(
        reader.pages[0].extract_text().split()
    )


@pytest.mark.parametrize("damage", ["row", "stage", "page", "component", "history_row"])
def test_invalid_evidence_keeps_original_and_independent_row(
    tmp_path, monkeypatch, damage
):
    source, config, templates, _ = prepare_inputs(tmp_path)
    run_typst = compile_notices.run_typst

    def changed_report(command, **options):
        result = run_typst(command, **options)
        if command[1] == "compile" and any("row-000001" in part for part in command):
            raw_pdf = Path(command[-1])
            reader = PdfReader(raw_pdf)
            attachment = next(
                item
                for item in reader.attachment_list
                if item.name == compile_notices.EVIDENCE_ATTACHMENT
            )
            reports = json.loads(attachment.content)
            report = reports[0]
            if damage == "row":
                report["identity"]["row_key"] = "row-000002"
            elif damage == "stage":
                report["checks"][0]["stage"] = "output"
            elif damage == "page":
                report["measurements"]["client"][0]["page"] = report["page_count"] + 1
            elif damage == "history_row":
                report["measurements"]["history"][0]["row_key"] = "row-000002"
            else:
                report["components"]["unknown"] = True
            embedded = attachment.pdf_object["/EF"]
            assert isinstance(embedded, DictionaryObject)
            stream = embedded["/F"].get_object()
            assert isinstance(stream, StreamObject)
            stream.set_data(json.dumps(reports).encode("utf-8"))
            writer = PdfWriter()
            writer.clone_document_from_reader(reader)
            writer.write(raw_pdf)
        return result

    monkeypatch.setattr(compile_notices, "run_typst", changed_report)
    saved = run_pipeline(
        source,
        tmp_path / "runs",
        config_dir=config,
        notice_template=templates / "overdue_agents_v1.en.typ",
    )
    record = json.loads(saved.read_text())
    first, second = record["entries"]
    assert first["original"]["status"] == second["original"]["status"] == "completed"
    assert first.get("render_summary") is None
    assert second["render_summary"]["identity"]["row_key"] == second["row_key"]
    assert "render.evidence_failed" in first["routing"]["failed_checks"]
    assert first["routing"]["destination"] == "review"
    assert not second["routing"]["failed_checks"]
    original = (saved.parent / first["original"]["path"]).read_bytes()
    first["checks"] = [check for check in first["checks"] if check["status"] != "fail"]
    run_report.write_report(saved.parent, record)
    attempt = bundle_pdfs.bundle_run(saved.parent)
    assert attempt["status"] == "completed"
    current = json.loads(saved.read_text())["entries"][0]
    assert "render.evidence_failed" in current["routing"]["failed_checks"]
    assert current["routing"]["destination"] == "review"
    assert (saved.parent / first["original"]["path"]).read_bytes() == original


def test_saved_report_is_rechecked_before_replacing_bundles(tmp_path):
    source, config, templates, _ = prepare_inputs(tmp_path)
    saved = run_pipeline(
        source,
        tmp_path / "runs",
        config_dir=config,
        notice_template=templates / "overdue_agents_v1.en.typ",
    )
    record = json.loads(saved.read_text())
    for damage in ("swapped", "version", "pages", "facts", "component_facts"):
        changed = deepcopy(record)
        first, second = changed["entries"]
        if damage == "swapped":
            first["render_summary"] = deepcopy(second["render_summary"])
        elif damage == "version":
            first["render_summary"]["schema_version"] = 1
        elif damage == "facts":
            first["render_summary"]["notice"]["client_data"]["name"] = "Other Person"
        elif damage == "component_facts":
            first["render_summary"]["measurements"]["history"][0]["source_matches"] = (
                False
            )
        else:
            first["render_summary"]["page_count"] += 1
        run_report.write_report(saved.parent, changed)
        attempt = bundle_pdfs.bundle_run(saved.parent)
        assert attempt["status"] == "completed"
        current = json.loads(saved.read_text())["entries"][0]
        assert "render.evidence_failed" in current["routing"]["failed_checks"]
        assert current["routing"]["destination"] == "review"


@pytest.mark.parametrize("language", ["en", "fr"])
@pytest.mark.parametrize(
    "age,override,selected",
    [
        (16, None, "student"),
        (15, None, "guardian"),
        (None, None, None),
        (16, "guardian", "guardian"),
        (15, "student", "student"),
        (None, "guardian", "guardian"),
        (None, "student", "student"),
    ],
)
def test_reader_selection_matches_both_address_components(
    tmp_path, language, age, override, selected
):
    job, payload = prepare_case(tmp_path, language=language)
    payload["client_data"]["age"] = age
    payload["intended_reader"] = override
    job.data.write_text(json.dumps(payload))
    expected = "none" if selected is None else json.dumps(selected)
    job.template.write_text(
        '#import "settings.typ": *\n#show: letter\n'
        f"#assert(immuknow.intended-reader(notice) == {expected})\n"
        "#immuknow.client-block(notice, window: none)\n"
        "#immuknow.address-block(notice)\n"
    )
    report, _ = compile_case(job)
    label = (
        ("To Parent/Guardian of:" if language == "en" else "Au parent ou tuteur de:")
        if selected == "guardian"
        else ("To:" if language == "en" else "À:")
    )
    assert len(report["measurements"]["address"]) == 2
    assert all(
        item["text"].startswith(label) and item["source_matches"]
        for item in report["measurements"]["address"]
    )
    unknown = [
        check
        for check in report["checks"]
        if check["code"] == "content.address_reader_unknown"
    ]
    assert len(unknown) == (2 if selected is None else 0)


@pytest.mark.parametrize("language", ["en", "fr"])
@pytest.mark.parametrize(
    "show_client_id,show_oiid",
    [(True, False), (False, True), (True, True), (False, False)],
)
def test_client_block_identifier_choices_keep_pdf_evidence(
    tmp_path, language, show_client_id, show_oiid
):
    job, payload = prepare_case(tmp_path, language=language)
    payload.update(oiid="0000987654", oiid_coverage="all_present")
    payload["client_data"]["address"] = "123 Main Street\nApartment 20"
    payload["client_data"]["school"] = (
        "École des élèves de la vallée et du quartier nord"
    )
    job.data.write_text(json.dumps(payload))
    job.template.write_text(
        '#import "settings.typ": *\n#show: letter\n'
        f"#immuknow.client-block(notice, show-client-id: {str(show_client_id).lower()}, show-oiid: {str(show_oiid).lower()})"
    )
    summary, reader = compile_case(job)
    text = reader.pages[0].extract_text()
    assert (job.client_id in text) == show_client_id
    assert (payload["oiid"] in text) == show_oiid
    if show_oiid:
        assert (
            "Ontario Immunization ID"
            if language == "en"
            else "Identifiant d’immunisation de l’Ontario"
        ) in " ".join(text.split())


@pytest.mark.parametrize(
    "oiid,coverage", [("0000987654", "mixed"), ("", "mixed"), ("", "all_absent")]
)
@pytest.mark.parametrize("missing", ["none", "auto", '""'])
def test_oiid_display_requires_cohort_availability_and_skips_missing_rows(
    tmp_path, oiid, coverage, missing
):
    job, payload = prepare_case(tmp_path)
    payload.update(oiid=oiid, oiid_coverage=coverage)
    job.data.write_text(json.dumps(payload))
    job.template.write_text(
        '#import "settings.typ": *\n#show: letter\n'
        "#immuknow.client-block(notice, show-client-id: false, show-oiid: true, "
        f'missing-oiid: {missing}, oiid-label: "Record key", show-birth-date: false, show-school: false)'
    )
    if coverage == "all_absent":
        with pytest.raises(subprocess.CalledProcessError) as failure:
            compile_case(job)
        assert "OIID display requires at least one OIID" in failure.value.stderr
        return
    summary, reader = compile_case(job)
    text = reader.pages[0].extract_text()
    displayed = bool(oiid) or missing != "none"
    assert ("Record key:" in text) == displayed
    assert summary["components"]["client"] == displayed


def test_changed_oiid_cannot_be_rendered_as_source_data(tmp_path):
    job, payload = prepare_case(tmp_path)
    payload.update(oiid="0000987654", oiid_coverage="all_present")
    job.data.write_text(json.dumps(payload))
    job.template.write_text(
        '#import "settings.typ": *\n#show: letter\n'
        '#immuknow.client-block((..notice, oiid: "0000000099"), show-oiid: true)'
    )
    with pytest.raises(ValueError, match="changed notice data"):
        compile_case(job)
    assert job.pdf.is_file()


@pytest.mark.parametrize("with_oiid", [False, True])
def test_native_oiid_availability_controls_rendering_for_the_complete_cohort(
    tmp_path, with_oiid
):
    source, config, templates, assignments = prepare_inputs(tmp_path)
    frame = create_test_input_dataframe(num_clients=2)
    frame["oiid"] = ["0000987654" if with_oiid else "", ""]
    frame.to_csv(source, index=False)
    for language in ("en", "fr"):
        (templates / f"overdue_agents_v1.{language}.typ").write_text(
            '#import "settings.typ": *\n#show: letter\n'
            "#immuknow.client-block(notice, show-client-id: false, show-oiid: true, "
            "show-birth-date: false, show-school: false)"
        )
    saved = run_pipeline(
        source,
        tmp_path / "runs",
        config_dir=config,
        template_dir=templates,
        notice_assignments=assignments,
    )
    record = json.loads(saved.read_text())
    assert len(record["entries"]) == 2
    for index, entry in enumerate(record["entries"]):
        assert entry["client_id"] == frame.iloc[index]["client_id"]
        assert entry["source"]["values"]["oiid"] == frame.iloc[index]["oiid"]
        if not with_oiid:
            assert entry["original"]["status"] == "failed"
            assert any(
                "OIID display requires at least one OIID" in check["message"]
                for check in entry["checks"]
            )
            continue
        assert entry["routing"]["destination"] == "delivery"
        text = (
            PdfReader(saved.parent / entry["original"]["path"]).pages[0].extract_text()
        )
        assert ("0000987654" in text) == (index == 0)
        assert entry["client_id"] not in text
    if with_oiid:
        attempt = bundle_pdfs.bundle_run(saved.parent)
        assert attempt["status"] == "completed"


@pytest.mark.parametrize(
    "change",
    [
        'row_key: "row-000002"',
        'client_data: (..notice.client_data, address: "88 Other Road")',
    ],
)
def test_address_only_client_block_remains_bound_to_source(tmp_path, change):
    job, _ = prepare_case(tmp_path)
    job.template.write_text(
        '#import "settings.typ": *\n#show: letter\n'
        f"#immuknow.client-block((..notice, {change}), show-client-id: false, "
        "show-birth-date: false, show-school: false)"
    )
    with pytest.raises(ValueError, match="different source row|changed notice data"):
        compile_case(job)


@pytest.mark.parametrize("language", ["en", "fr"])
@pytest.mark.parametrize("missing", ["none", '""', "auto", '"Ask us for your ID"'])
def test_missing_oiid_presentation_keeps_source_facts_and_pdf_evidence(
    tmp_path, language, missing
):
    job, payload = prepare_case(tmp_path, language=language)
    payload.update(oiid="", oiid_coverage="mixed")
    job.data.write_text(json.dumps(payload))
    job.template.write_text(
        '#import "settings.typ": *\n#show: letter\n'
        "#immuknow.client-block(notice, show-client-id: false, show-oiid: true, "
        f'missing-oiid: {missing}, oiid-label: "OIID", show-birth-date: false, show-school: false)'
    )
    summary, reader = compile_case(job)
    assert summary["notice"]["oiid"] == ""
    text = " ".join(reader.pages[0].extract_text().split())
    expected = {
        "none": None,
        '""': "",
        "auto": "Not available" if language == "en" else "Non disponible",
        '"Ask us for your ID"': "Ask us for your ID",
    }[missing]
    assert summary["components"]["client"] == (expected is not None)
    if expected is None:
        assert "OIID:" not in text
    else:
        assert ("OIID: " + expected).strip() in text
        assert summary["measurements"]["client"][0]["text"] == "OIID: " + expected


def test_available_oiid_overrides_missing_placeholder(tmp_path):
    job, payload = prepare_case(tmp_path)
    payload.update(oiid="0000987654", oiid_coverage="mixed")
    job.data.write_text(json.dumps(payload))
    job.template.write_text(
        '#import "settings.typ": *\n#show: letter\n'
        '#immuknow.client-block(notice, show-oiid: true, missing-oiid: "Unavailable")'
    )
    _, reader = compile_case(job)
    text = reader.pages[0].extract_text()
    assert payload["oiid"] in text
    assert "Unavailable" not in text
