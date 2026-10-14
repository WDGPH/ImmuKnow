"""Real PDFs survive invalid evidence and cannot be released by deleting findings."""

import json
from copy import deepcopy
from dataclasses import replace

import pytest
import pymupdf
import zxingcpp
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject, NullObject, TextStringObject

from immuknow import bundle_pdfs, compile_notices, run_report
from immuknow.orchestrator import run_pipeline
from immuknow.validate_pdfs import inspect_notice
from tests.integration.test_native_templates import prepare_case, compile_case
from tests.integration.test_run_accounting import prepare_inputs

pytestmark = pytest.mark.integration


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
        '#import "settings.typ": *\n#show: notice-style\n'
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
    _, checks = inspect_notice(job, tmp_path, summary)
    assert all(check.status in ("pass", "not_applicable") for check in checks)


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
    original, checks = inspect_notice(job, tmp_path, summary)
    assert original["status"] == "completed"
    assert all(c.status in ("pass", "not_applicable") for c in checks)


@pytest.mark.parametrize(
    "body,warning",
    [("#immuknow.address-block(notice)", True), ("General information.", False)],
)
def test_window_warning_depends_on_placed_addresses(tmp_path, body, warning):
    job, _ = prepare_case(tmp_path)
    job.template.write_text('#import "settings.typ": *\n#show: notice-style\n' + body)
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
        '#import "settings.typ": *\n#show: notice-style\n'
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
    original, checks = inspect_notice(job, tmp_path, summary)
    assert original["status"] == "completed"
    assert all(c.status in ("pass", "not_applicable") for c in checks)


@pytest.mark.parametrize("replacement", ["", "9999999999", "00000000010"])
def test_correct_id_elsewhere_cannot_hide_a_missing_or_wrong_client_block(
    tmp_path, replacement
):
    job, _ = prepare_case(tmp_path)
    job.template.write_text(
        '#import "settings.typ": *\n#show: notice-style\n'
        "#immuknow.client-block(notice)\n"
        "#pagebreak()\n#immuknow.client-block(notice)"
    )
    summary, _ = compile_case(job)
    area = summary["measurements"]["client"][0]
    with pymupdf.open(job.pdf) as pdf:
        page = pdf[0]
        page.add_redact_annot(
            pymupdf.Rect(
                area["x_pt"] - 0.1,
                area["y_pt"] - 0.1,
                area["x_pt"] + area["width_pt"] + 0.1,
                area["y_pt"] + area["height_pt"] + 0.1,
            )
        )
        page.apply_redactions()
        if replacement:
            page.insert_text(
                (area["x_pt"], area["y_pt"] + area["height_pt"]),
                replacement,
                fontsize=10,
            )
        page.insert_text((50, 500), "Client ID: " + job.client_id)
        pdf.saveIncr()
    original, checks = inspect_notice(job, tmp_path, summary)
    assert original["status"] == "completed"
    assert (
        next(check for check in checks if check.code == "output.client_identity").status
        == "fail"
    )


@pytest.mark.parametrize("field", ["name", "address", "postal_code"])
def test_correct_address_elsewhere_cannot_hide_changed_mailing_details(tmp_path, field):
    job, payload = prepare_case(tmp_path)
    summary, _ = compile_case(job)
    expected = payload["client_data"][field]
    with pymupdf.open(job.pdf) as pdf:
        page = pdf[0]
        matches = page.search_for(expected)
        assert matches
        for rect in matches:
            page.add_redact_annot(rect)
        page.apply_redactions()
        page.insert_text((50, 500), expected)
        pdf.saveIncr()
    original, checks = inspect_notice(job, tmp_path, summary)
    assert original["status"] == "completed"
    assert (
        next(c for c in checks if c.code == "output.client_identity").status == "fail"
    )


@pytest.mark.parametrize("language", ["en", "fr"])
@pytest.mark.parametrize("field", ["birth_date", "school"])
def test_correct_details_elsewhere_cannot_hide_changed_client_details(
    tmp_path, language, field
):
    job, payload = prepare_case(tmp_path, language=language)
    payload["client_data"]["date_of_birth_iso"] = "2014-07-08"
    job.data.write_text(json.dumps(payload))
    summary, _ = compile_case(job)
    _, checks = inspect_notice(job, tmp_path, summary)
    assert all(c.status in ("pass", "not_applicable") for c in checks)
    expected = (
        ("July 8, 2014" if language == "en" else "8 juillet 2014")
        if field == "birth_date"
        else payload["client_data"]["school"]
    )
    with pymupdf.open(job.pdf) as pdf:
        page = pdf[0]
        matches = page.search_for(expected)
        assert matches
        for rect in matches:
            page.add_redact_annot(rect)
        page.apply_redactions()
        page.insert_text((50, 500), expected)
        pdf.saveIncr()
    original, checks = inspect_notice(job, tmp_path, summary)
    assert original["status"] == "completed"
    assert (
        next(c for c in checks if c.code == "output.client_identity").status == "fail"
    )


@pytest.mark.parametrize("language", ["en", "fr"])
@pytest.mark.parametrize("show", [True, False])
def test_blank_or_hidden_client_details_match_the_pdf(tmp_path, language, show):
    job, payload = prepare_case(tmp_path, language=language)
    payload["client_data"]["date_of_birth_iso"] = ""
    payload["client_data"]["school"] = "" if show else "School should not appear"
    job.data.write_text(json.dumps(payload))
    job.template.write_text(
        '#import "settings.typ": *\n#show: notice-style\n'
        f"#immuknow.client-block(notice, show-birth-date: {str(show).lower()}, show-school: {str(show).lower()})"
    )
    summary, reader = compile_case(job)
    assert "School should not appear" not in reader.pages[0].extract_text()
    _, checks = inspect_notice(job, tmp_path, summary)
    assert all(c.status in ("pass", "not_applicable") for c in checks)


def test_component_for_another_row_cannot_repeat_the_same_external_id(tmp_path):
    job, _ = prepare_case(tmp_path)
    job.template.write_text(
        '#import "settings.typ": *\n#show: notice-style\n'
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
        "overdue-agents(other)",
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
        '#import "settings.typ": *\n#show: notice-style\n'
        "#immuknow.client-block(notice)\n"
        f"#let other = (..notice, row_key: {json.dumps('row-000002' if change_row else job.sequence)},\n"
        '  client_data: (..notice.client_data, name: "Morgan Example", address: "88 Other Road"),\n'
        '  history: ((date_given: "2018-03-04", agent: "IPV", display_name: "Other vaccine", diseases: ("Polio",), validity: "valid"),),\n'
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
    if marker:
        assert marker in "".join(
            page.extract_text() for page in PdfReader(job.pdf).pages
        )


def test_changing_both_the_report_and_components_cannot_replace_source_facts(tmp_path):
    job, _ = prepare_case(tmp_path)
    job.template.write_text(
        '#import "settings.typ": *\n'
        '#let changed = (..notice, client_data: (..notice.client_data, name: "Morgan Example"))\n'
        "#show: immuknow.notice-style.with(notice: changed)\n"
        "#immuknow.client-block(changed)"
    )
    with pytest.raises(ValueError, match="differs from the prepared notice"):
        compile_case(job)
    assert "Morgan Example" in PdfReader(job.pdf).pages[0].extract_text()


@pytest.mark.parametrize("component", ["client", "address"])
def test_saved_personal_area_is_checked_again_before_delivery(tmp_path, component):
    source, config, templates, _ = prepare_inputs(tmp_path)
    saved = run_pipeline(
        source,
        tmp_path / "runs",
        config_dir=config,
        notice_template=templates / "overdue_agents_v1.en.typ",
    )
    record = json.loads(saved.read_text())
    first, _ = record["entries"]
    assert not first["routing"]["failed_checks"]
    first["render_summary"]["measurements"][component][0]["y_pt"] += 100
    run_report.write_report(saved.parent, record)
    attempt = bundle_pdfs.bundle_run(saved.parent)
    assert attempt["status"] == "completed"
    first, second = json.loads(saved.read_text())["entries"]
    assert "output.client_identity" in first["routing"]["failed_checks"]
    assert first["routing"]["destination"] == "review"
    assert not second["routing"]["failed_checks"]


def test_unreadable_text_on_a_page_without_a_client_block_still_fails(tmp_path):
    job, _ = prepare_case(tmp_path)
    summary, reader = compile_case(job)
    assert len(reader.pages) == 2
    assert all(area["page"] == 1 for area in summary["measurements"]["client"])
    writer = PdfWriter(clone_from=reader)
    contents = DecodedStreamObject()
    contents.set_data(b"BT (unterminated")
    writer.pages[1].replace_contents(contents.flate_encode())
    writer.write(job.pdf)
    original, checks = inspect_notice(job, tmp_path, summary)
    assert original["status"] == "completed"
    assert any(
        check.status == "fail" and "PDF text" in check.message for check in checks
    )


@pytest.mark.parametrize(
    "url,status",
    [
        ("https://example.org/update?name=%C3%89lodie#form", "pass"),
        ("HTTP://localhost:8080/record", "pass"),
        ("https://[2001:db8::1]:443/", "pass"),
        ("https://xn--exmple-cua.org/", "pass"),
        ("https://exämple.org/élève?name=Élodie&city=東京", "pass"),
        ("https://example.org/record?mark=🙂", "pass"),
        ("https:///record", "warn"),
        ("example.org/record", "warn"),
        ("https://example.org:99999/", "warn"),
        ("https://example.org/a b", "warn"),
        ("https://example.org/%zz", "warn"),
        ("https://-example.org/", "warn"),
        ("https://[not-an-address]/", "warn"),
        ("javascript:alert(1)", "warn"),
    ],
)
def test_qr_destination_quality_is_checked_without_discarding_the_pdf(
    tmp_path, url, status
):
    job, _ = prepare_case(tmp_path)
    job.template.write_text(
        '#import "settings.typ": *\n#show: notice-style\n'
        "#immuknow.client-block(notice)\n"
        f"#immuknow.qr-code(notice, url: {json.dumps(url, ensure_ascii=False)})"
    )
    summary, _ = compile_case(job)
    original, checks = inspect_notice(job, tmp_path, summary)
    assert original["status"] == "completed"
    assert (
        next(c for c in checks if c.code == "output.evidence_matches").status == "pass"
    )
    assert next(c for c in checks if c.code == "output.qr_destination").status == status
    with pymupdf.open(job.pdf) as pdf:
        decoded = zxingcpp.read_barcodes(pdf[0].get_pixmap(dpi=200).pil_image())
    assert [code.bytes for code in decoded] == [url.encode("utf-8")]
    assert [code.text for code in decoded] == [url]


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
        '#import "settings.typ": *\n#show: notice-style\n'
        f'#immuknow.qr-code(notice, url: {json.dumps(value, ensure_ascii=False)}, error-correction: "{level}")'
    )
    compile_case(job)
    with pymupdf.open(job.pdf) as pdf:
        decoded = zxingcpp.read_barcodes(pdf[0].get_pixmap(dpi=300).pil_image())
    assert len(decoded) == 1
    assert decoded[0].bytes == value.encode("utf-8")
    assert decoded[0].text == value
    details = decoded[0].extra
    assert isinstance(details, dict)
    assert details["Version"] == str(version + extra)


def test_saved_delivery_restores_a_deleted_qr_destination_warning(tmp_path):
    source, config, templates, _ = prepare_inputs(tmp_path)
    settings = templates / "settings.typ"
    settings.write_text(
        settings.read_text().replace("https://example.org/update", "https:///update")
    )
    saved = run_pipeline(
        source,
        tmp_path / "runs",
        config_dir=config,
        notice_template=templates / "overdue_agents_v1.en.typ",
    )
    record = json.loads(saved.read_text())
    first = record["entries"][0]
    assert any(
        c["code"] == "output.qr_destination" and c["status"] == "warn"
        for c in first["checks"]
    )
    first["checks"] = [
        c for c in first["checks"] if c["code"] != "output.qr_destination"
    ]
    run_report.write_report(saved.parent, record)
    attempt = bundle_pdfs.bundle_run(saved.parent)
    results = attempt["evaluations"][first["row_key"]]["results"]
    assert any(
        c["code"] == "output.qr_destination" and c["status"] == "warn" for c in results
    )
    assert (
        json.loads(saved.read_text())["entries"][0]["routing"]["destination"]
        == "review"
    )


@pytest.mark.parametrize("damage", ["missing", "other_client", "unreadable"])
def test_qr_link_failure_keeps_original_and_is_rechecked_on_delivery(
    tmp_path, monkeypatch, damage
):
    source, config, templates, _ = prepare_inputs(tmp_path)
    compile_original = compile_notices.compile_render_job

    def changed_pdf(job, *args, **kwargs):
        warnings = compile_original(job, *args, **kwargs)
        if job.sequence != "row-000001":
            return warnings
        writer = PdfWriter(clone_from=PdfReader(job.pdf))
        changed = 0
        for page in writer.pages:
            for reference in page.annotations or []:
                annotation = reference.get_object()
                action = annotation.get("/A", {})
                destination = action.get("/URI", "")
                if job.client_id not in destination:
                    continue
                if damage == "missing":
                    del annotation["/A"]
                elif damage == "other_client":
                    action[NameObject("/URI")] = TextStringObject(
                        destination.replace(job.client_id, "0000000002")
                    )
                else:
                    action[NameObject("/URI")] = NullObject()
                changed += 1
        assert changed
        writer.write(job.pdf)
        return warnings

    monkeypatch.setattr(compile_notices, "compile_render_job", changed_pdf)
    saved = run_pipeline(
        source,
        tmp_path / "runs",
        config_dir=config,
        notice_template=templates / "overdue_agents_v1.en.typ",
    )
    record = json.loads(saved.read_text())
    first, second = record["entries"]
    assert first["original"]["status"] == second["original"]["status"] == "completed"
    assert first["render_summary"]["qr_urls"]
    assert any(
        check["code"] == "output.evidence_matches" and check["status"] == "fail"
        for check in first["checks"]
    )
    assert first["routing"]["destination"] == "review"
    assert not second["routing"]["failed_checks"]
    original = saved.parent / first["original"]["path"]
    before = original.read_bytes()
    first["checks"] = [
        check for check in first["checks"] if check["code"] != "output.evidence_matches"
    ]
    run_report.write_report(saved.parent, record)
    attempt = bundle_pdfs.bundle_run(saved.parent)
    assert attempt["status"] == "completed"
    current = json.loads(saved.read_text())["entries"][0]
    assert "output.evidence_matches" in current["routing"]["failed_checks"]
    assert current["routing"]["destination"] == "review"
    assert original.read_bytes() == before


def test_saved_qr_destinations_cannot_be_swapped_between_clients(tmp_path):
    source, config, templates, _ = prepare_inputs(tmp_path)
    saved = run_pipeline(
        source,
        tmp_path / "runs",
        config_dir=config,
        notice_template=templates / "overdue_agents_v1.en.typ",
    )
    record = json.loads(saved.read_text())
    first, second = record["entries"]
    assert not first["routing"]["failed_checks"]
    assert first["render_summary"]["qr_urls"] != second["render_summary"]["qr_urls"]
    first["render_summary"]["qr_urls"] = second["render_summary"]["qr_urls"]
    run_report.write_report(saved.parent, record)
    attempt = bundle_pdfs.bundle_run(saved.parent)
    assert attempt["status"] == "completed"
    first, second = json.loads(saved.read_text())["entries"]
    assert "output.evidence_matches" in first["routing"]["failed_checks"]
    assert first["routing"]["destination"] == "review"
    assert not second["routing"]["failed_checks"]


@pytest.mark.parametrize("damage", ["row", "stage", "page", "component", "history_row"])
def test_invalid_evidence_keeps_original_and_independent_row(
    tmp_path, monkeypatch, damage
):
    source, config, templates, _ = prepare_inputs(tmp_path)
    run_typst = compile_notices.run_typst

    def changed_report(command, **options):
        result = run_typst(command, **options)
        if command[1] == "eval" and any("row-000001" in part for part in command):
            reports = json.loads(result.stdout)
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
            result.stdout = json.dumps(reports)
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
    active = {
        path: path.read_bytes() for path in (saved.parent / "bundles").rglob("*.pdf")
    }
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
        assert attempt["status"] == "failed"
        assert {
            path: path.read_bytes()
            for path in (saved.parent / "bundles").rglob("*.pdf")
        } == active
