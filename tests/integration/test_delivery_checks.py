"""Verify the final batch, current delivery tools and saved resource boundaries."""

from __future__ import annotations

from tests.fixtures.project import copy_project

import json
import shutil
from hashlib import sha256
from pathlib import Path

import pymupdf
import pytest
import yaml
from pypdf import PdfReader, PdfWriter

from immuknow import bundle_pdfs, run_report
from immuknow.orchestrator import run_pipeline
from tests.fixtures.sample_input import create_test_input_dataframe

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


@pytest.fixture
def saved_run(tmp_path):
    config = tmp_path / "config"
    templates = tmp_path / "templates"
    shutil.copytree(ROOT / "immuknow/config", config)
    copy_project(templates)
    settings = yaml.safe_load((config / "parameters.yaml").read_text())
    settings["bundling"] = {"bundle_size": 2}
    settings["validation"] = {
        "notice_length": {"enabled": True, "count": 2, "unit": "pages"}
    }
    settings["encryption"]["enabled"] = False
    (config / "parameters.yaml").write_text(yaml.safe_dump(settings))
    template = templates / "overdue_diseases_v1.en.typ"
    template.write_text(
        template.read_text().replace(
            'name: "Fixture signer",',
            'name: if notice.client_id == "0000000002" { '
            "[#for _ in range(120) [Signature line #linebreak()]] "
            '} else { "Fixture signer" },',
        )
    )
    frame = create_test_input_dataframe(num_clients=3)
    frame["overdue_disease"] = "Measles - 2"
    frame["overdue_agent"] = "M"
    source = tmp_path / "clients.csv"
    frame.to_csv(source, index=False)
    return run_pipeline(
        source, tmp_path / "runs", config_dir=config, notice_template=template
    ).parent


def record(run_dir):
    return json.loads((run_dir / "run.json").read_text())


def active_bundles(run_dir):
    return {
        str(path.relative_to(run_dir)): path.read_bytes()
        for path in (run_dir / "bundles").rglob("*.pdf")
    }


def test_fixed_page_count_checks_all_final_batches_and_cannot_be_waived(saved_run):
    before = record(saved_run)
    first, long, last = before["entries"]
    expected = first["original"]["pages"]
    assert expected == 2
    assert expected == last["original"]["pages"]
    assert long["original"]["pages"] > expected
    assert any(
        check["code"] == "layout.signature_page" and check["status"] == "warn"
        for check in long["checks"]
    )
    originals = {
        entry["row_key"]: (saved_run / entry["original"]["path"]).read_bytes()
        for entry in before["entries"]
    }
    active = active_bundles(saved_run)
    tokens = [
        token
        for evaluation in before["delivery_attempts"][-1]["evaluations"].values()
        for token in evaluation["warning_tokens"].values()
    ]
    policy = {"notice_length": {"enabled": True, "count": expected, "unit": "pages"}}
    failed = bundle_pdfs.bundle_run(
        saved_run, policy=policy, accept=tokens, reason="Inspected each original"
    )
    assert failed["status"] == "failed"
    checks = [
        check for check in failed["checks"] if check["code"] == "delivery.notice_length"
    ]
    assert [check["status"] for check in checks] == ["fail", "pass"]
    assert checks[0]["measurements"]["notices"] == [
        {"row_key": first["row_key"], "pages": expected},
        {"row_key": long["row_key"], "pages": long["original"]["pages"]},
    ]
    assert checks[1]["measurements"]["notices"] == [
        {"row_key": last["row_key"], "pages": expected}
    ]
    assert active_bundles(saved_run) == active
    after = record(saved_run)
    assert {item["token"] for item in after["warning_acceptances"]} == set(tokens)
    assert after["delivery_attempts"][:-1] == before["delivery_attempts"]
    assert [entry["bundle"] for entry in after["entries"]] == [
        entry["bundle"] for entry in before["entries"]
    ]

    # Withholding cannot exempt a notice from the configured page count.
    held = bundle_pdfs.bundle_run(saved_run, withhold=[long["row_key"]])
    assert held["status"] == "failed"
    assert any(
        check["code"] == "delivery.notice_length" and check["status"] == "fail"
        for check in held["checks"]
    )
    assert active_bundles(saved_run) == active

    disabled = bundle_pdfs.bundle_run(saved_run, policy={}, withhold=[long["row_key"]])
    assert disabled["status"] == "completed", disabled["checks"]
    after = record(saved_run)
    assert after["entries"][1]["routing"]["destination"] == "review"
    assert [bundle["row_keys"] for bundle in disabled["bundles"]] == [
        [first["row_key"], long["row_key"]],
        [last["row_key"]],
    ]
    assert all(bundle["destination"] == "bundle" for bundle in disabled["bundles"])
    assert any(
        check["code"] == "delivery.notice_length" and check["status"] == "not_run"
        for check in disabled["checks"]
    )
    for entry in after["entries"]:
        assert (saved_run / entry["original"]["path"]).read_bytes() == originals[
            entry["row_key"]
        ]
        with pymupdf.open(saved_run / entry["bundle"]["path"]) as combined:
            with pymupdf.open(
                stream=originals[entry["row_key"]], filetype="pdf"
            ) as original:
                start = entry["bundle"]["notice_start_page"] - 1
                for offset, page in enumerate(original):
                    assert (
                        combined[start + offset].get_pixmap().samples
                        == page.get_pixmap().samples
                    )


@pytest.mark.parametrize("damage", ["reorder", "duplicate", "geometry"])
def test_written_bundle_must_match_each_selected_page_in_order(
    saved_run, monkeypatch, damage
):
    before = record(saved_run)
    active = active_bundles(saved_run)
    write = PdfWriter.write

    def changed_write(writer, stream):
        name = str(getattr(stream, "name", ""))
        if "bundles.next" in name:
            if damage == "geometry":
                writer.pages[0].mediabox.upper_right = (600, 800)
            else:
                page = writer.pages[0 if damage == "reorder" else -1]
                writer.remove_page(0)
                writer.add_page(page)
        return write(writer, stream)

    monkeypatch.setattr(PdfWriter, "write", changed_write)
    result = bundle_pdfs.bundle_run(saved_run)
    assert result["status"] == "failed"
    assert (
        "do not match the selected notices in order" in result["checks"][-1]["message"]
    )
    assert active_bundles(saved_run) == active
    assert [entry["bundle"] for entry in record(saved_run)["entries"]] == [
        entry["bundle"] for entry in before["entries"]
    ]


@pytest.mark.parametrize(
    ("source", "damage", "message"),
    [
        ("facts", "bytes", "Saved notice payload changed"),
        ("original", "bytes", "Original PDF hash changed"),
        ("facts", "escape", "Payload path is outside facts/"),
        ("original", "escape", "Original path is outside originals/"),
    ],
)
def test_delivery_rechecks_sources_after_routing(
    saved_run, tmp_path, monkeypatch, source, damage, message
):
    committed = bundle_pdfs.bundle_run(saved_run, policy={})
    assert committed["status"] == "completed", committed["checks"]
    before = record(saved_run)
    bundles = {
        path.relative_to(saved_run / "bundles"): path.read_bytes()
        for path in (saved_run / "bundles").rglob("*")
        if path.is_file()
    }
    assert any(path.suffix == ".pdf" for path in bundles)
    assert any(path.suffix == ".csv" for path in bundles)

    assemble = bundle_pdfs._assemble

    def change_source(routed, next_dir, group_by, size, attempt):
        entry = routed[0][0]
        path = saved_run / entry[source]["path"]
        content = path.read_bytes()
        if damage == "bytes":
            path.write_bytes(content + b" changed")
        else:
            outside = tmp_path / f"outside-{source}"
            outside.write_bytes(content)
            path.unlink()
            path.symlink_to(outside)
        return assemble(routed, next_dir, group_by, size, attempt)

    monkeypatch.setattr(bundle_pdfs, "_assemble", change_source)
    failed = bundle_pdfs.bundle_run(saved_run, policy={})
    assert failed["status"] == "failed"
    assert message in failed["checks"][-1]["message"]
    assert {
        path.relative_to(saved_run / "bundles"): path.read_bytes()
        for path in (saved_run / "bundles").rglob("*")
        if path.is_file()
    } == bundles
    after = record(saved_run)
    assert [(entry["bundle"], entry["routing"]) for entry in after["entries"]] == [
        (entry["bundle"], entry["routing"]) for entry in before["entries"]
    ]


def test_delivery_validates_each_saved_payload_once(saved_run, monkeypatch):
    validated = []
    validate = bundle_pdfs.validate_render_payload

    def count_validation(payload):
        validated.append(payload["row_key"])
        return validate(payload)

    monkeypatch.setattr(bundle_pdfs, "validate_render_payload", count_validation)
    result = bundle_pdfs.bundle_run(saved_run, policy={})
    assert result["status"] == "completed", result["checks"]
    assert sorted(validated) == sorted(
        entry["row_key"] for entry in record(saved_run)["entries"]
    )


@pytest.mark.parametrize("damage", ["resource", "library", "compiler", "payload"])
def test_saved_run_refuses_unsupported_resources_even_without_review(saved_run, damage):
    saved = record(saved_run)
    # The supported resource check happens before individual warning review.
    for entry in saved["entries"]:
        entry["checks"] = [
            check for check in entry["checks"] if check["status"] != "warn"
        ]
    if damage in {"resource", "library"}:
        name = (
            "assets/logo.svg"
            if damage == "resource"
            else "lib/immuknow/src/findings.typ"
        )
        (saved_run / "resources/templates" / name).write_bytes(b"Changed resource")
        if damage == "library":
            saved["resources"].update(
                run_report.resource_manifest(saved_run / "resources", saved_run)
            )
    elif damage == "compiler":
        saved["version"]["compiler"] = "0.14.0"
    else:
        entry = saved["entries"][0]
        path = saved_run / entry["facts"]["path"]
        payload = json.loads(path.read_text())
        payload["schema_version"] = 99
        path.write_text(json.dumps(payload))
        entry["facts"]["sha256"] = sha256(path.read_bytes()).hexdigest()
    run_report.write_report(saved_run, saved)
    active = active_bundles(saved_run)
    result = bundle_pdfs.bundle_run(saved_run)
    assert result["status"] == "failed"
    assert active_bundles(saved_run) == active
    assert result["checks"][-1]["status"] == "fail"


def rehash_payload(run_dir, entry, **changes):
    path = run_dir / entry["facts"]["path"]
    payload = json.loads(path.read_text())
    payload.update(changes)
    path.write_text(json.dumps(payload))
    entry["facts"]["sha256"] = sha256(path.read_bytes()).hexdigest()


def replace_original_with_empty_pdf(run_dir, entry):
    path = run_dir / entry["original"]["path"]
    with path.open("wb") as stream:
        PdfWriter().write(stream)
    entry["original"]["sha256"] = sha256(path.read_bytes()).hexdigest()


def tamper(run_dir, saved, damage):
    entry = saved["entries"][0]
    bundling = saved["configuration"]["effective"]["bundling"]
    if damage == "payload outside facts":
        entry["facts"]["path"] = entry["original"]["path"]
    elif damage == "original outside originals":
        entry["original"]["path"] = entry["facts"]["path"]
    elif damage == "payload for another client":
        rehash_payload(run_dir, entry, client_id="0000000099")
    elif damage == "original without pages":
        replace_original_with_empty_pdf(run_dir, entry)
    elif damage == "original page count":
        entry["original"]["pages"] += 1
    elif damage == "negative bundle size":
        bundling["bundle_size"] = -1
    elif damage == "fixed length without bundling":
        bundling["bundle_size"] = 0
    else:
        saved["entries"][1]["row_key"] = entry["row_key"]


@pytest.mark.parametrize(
    ("damage", "message"),
    [
        ("payload outside facts", "outside facts/"),
        ("original outside originals", "outside originals/"),
        ("payload for another client", "does not belong to this source row"),
        ("original without pages", "readable and unencrypted"),
        ("original page count", "page count changed"),
        ("negative bundle size", "nonnegative integer"),
        ("fixed length without bundling", "bundle_size above zero"),
        ("repeated row key", "unique source row keys"),
    ],
)
def test_saved_run_refuses_tampered_entries_and_settings(saved_run, damage, message):
    saved = record(saved_run)
    tamper(saved_run, saved, damage)
    run_report.write_report(saved_run, saved)
    active = active_bundles(saved_run)
    result = bundle_pdfs.bundle_run(saved_run)
    assert result["status"] == "failed"
    assert active_bundles(saved_run) == active
    assert result["checks"][-1]["code"] == "delivery.failed"
    assert message in result["checks"][-1]["message"]


def test_withheld_rows_must_belong_to_the_run(saved_run):
    result = bundle_pdfs.bundle_run(saved_run, withhold=["row-999999"])
    assert result["status"] == "failed"
    assert "Withheld rows" in result["checks"][-1]["message"]


@pytest.mark.parametrize("content", ["[]", '{"format_version": 1}'])
def test_unsupported_run_formats_are_refused(saved_run, content):
    (saved_run / "run.json").write_text(content)
    with pytest.raises(ValueError, match="Unsupported run format"):
        bundle_pdfs.bundle_run(saved_run)


def test_missing_run_directory_is_refused(tmp_path):
    with pytest.raises(ValueError, match="does not exist"):
        bundle_pdfs.bundle_run(tmp_path / "missing")


def test_rebundling_groups_by_actual_page_count_and_combined_fields(saved_run):
    saved = record(saved_run)
    saved["configuration"]["effective"]["bundling"] = {
        "bundle_size": 1,
        "group_by": ["board", "language", "page_count"],
    }
    run_report.write_report(saved_run, saved)
    initial = bundle_pdfs.bundle_run(saved_run, policy={})
    assert initial["status"] == "completed", initial["checks"]
    tokens = [
        token
        for evaluation in initial["evaluations"].values()
        for token in evaluation["warning_tokens"].values()
    ]
    attempt = bundle_pdfs.bundle_run(
        saved_run, policy={}, accept=tokens, reason="Inspected each original"
    )
    assert attempt["status"] == "completed", attempt["checks"]
    entries = {entry["row_key"]: entry for entry in record(saved_run)["entries"]}
    batches = attempt["bundles"]
    assert len(batches) == len(entries)
    assert {key for batch in batches for key in batch["row_keys"]} == set(entries)
    for batch in batches:
        entry = entries[batch["row_keys"][0]]
        assert batch["group_by"] == ["board", "language", "page_count"]
        assert batch["group_id"] == [
            entry["facts"]["prepared"]["board"]["id"],
            entry["assignment"]["language"],
            str(len(PdfReader(saved_run / entry["original"]["path"]).pages)),
        ]
        assert (
            len(PdfReader(saved_run / batch["path"]).pages)
            == entry["original"]["pages"]
        )
