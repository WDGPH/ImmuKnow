"""Verify the final batch, current delivery tools and saved resource boundaries."""

from __future__ import annotations

import json
import shutil
from copy import deepcopy
from hashlib import sha256
from importlib.metadata import version
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
    shutil.copytree(ROOT / "immuknow/templates", templates)
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
            "name: signature-name,",
            'name: if notice.client_id == "0000000002" { '
            "[#for _ in range(120) [Signature line #linebreak()]] "
            "} else { signature-name },",
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

    # Holding the long notice is explicit: it stays in review and in the saved accounting.
    succeeded = bundle_pdfs.bundle_run(saved_run, withhold=[long["row_key"]])
    assert succeeded["status"] == "completed", succeeded["checks"]
    after = record(saved_run)
    assert [entry["routing"]["destination"] for entry in after["entries"]] == [
        "delivery",
        "review",
        "delivery",
    ]
    batch = next(
        item for item in succeeded["bundles"] if item["destination"] == "delivery"
    )
    assert batch["row_keys"] == [first["row_key"], last["row_key"]]
    assert batch["pages"] == 2 * expected
    with pymupdf.open(saved_run / batch["path"]) as combined:
        for entry in (after["entries"][0], after["entries"][2]):
            with pymupdf.open(
                stream=originals[entry["row_key"]], filetype="pdf"
            ) as original:
                start = entry["bundle"]["notice_start_page"] - 1
                for offset, page in enumerate(original):
                    assert (
                        combined[start + offset].get_pixmap().samples
                        == page.get_pixmap().samples
                    )
    held = bundle_pdfs.bundle_run(
        saved_run, withhold=[entry["row_key"] for entry in after["entries"]]
    )
    assert held["status"] == "completed"
    assert any(
        check["code"] == "delivery.notice_length"
        and check["status"] == "not_applicable"
        for check in held["checks"]
    )
    # An explicit policy change disables the count; it is never guessed from the majority.
    disabled = bundle_pdfs.bundle_run(saved_run, policy={}, withhold=[])
    assert disabled["status"] == "completed"
    assert disabled["review_tools"] is None
    assert any(
        check["code"] == "delivery.notice_length" and check["status"] == "not_run"
        for check in disabled["checks"]
    )
    for entry in record(saved_run)["entries"]:
        assert (saved_run / entry["original"]["path"]).read_bytes() == originals[
            entry["row_key"]
        ]


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


def test_attempt_records_current_tools_and_keeps_previous_evidence(
    saved_run, tmp_path, monkeypatch
):
    before = record(saved_run)
    previous = deepcopy(before["delivery_attempts"][-1])
    tools = previous["review_tools"]
    assert tools["compiler"]["version_output"].startswith("typst 0.15.1 ")
    assert (
        sha256(Path(tools["compiler"]["path"]).read_bytes()).hexdigest()
        == tools["compiler"]["sha256"]
    )
    assert previous["engine"]["pdf_library_version"] == version("pypdf")
    assert previous["engine"]["code"]
    assert previous["resources_sha256"] == before["resources"]["sha256"]
    assert "fonts" not in previous
    alternate = tmp_path / "updated-package"
    shutil.copytree(ROOT / "immuknow/review_templates", alternate / "review_templates")
    sheet = alternate / "review_templates/review_sheet.typ"
    sheet.write_text(sheet.read_text() + "\nUpdated review footer\n")
    monkeypatch.setattr(bundle_pdfs, "files", lambda _: alternate)
    attempt = bundle_pdfs.bundle_run(saved_run)
    assert attempt["status"] == "completed", attempt["checks"]
    changed = next(
        item
        for item in attempt["review_tools"]["templates"]
        if item["path"] == "review_sheet.typ"
    )
    assert changed["sha256"] == sha256(sheet.read_bytes()).hexdigest()
    assert attempt["review_tools"]["templates"] != tools["templates"]
    assert record(saved_run)["delivery_attempts"][-2] == previous
    review = next(
        item for item in attempt["bundles"] if item["destination"] == "review"
    )
    assert "Updated review footer" in " ".join(
        page.extract_text() for page in PdfReader(saved_run / review["path"]).pages
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
            "assets/logo.png"
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
    assert result["review_tools"] is None
    assert active_bundles(saved_run) == active
    assert result["checks"][-1]["status"] == "fail"


def test_interrupted_review_keeps_the_tools_record_before_compilation(
    saved_run, monkeypatch
):
    before = active_bundles(saved_run)

    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt("Interrupted before the review compiler starts")

    with monkeypatch.context() as replacement:
        replacement.setattr(bundle_pdfs, "run_typst", interrupt)
        with pytest.raises(KeyboardInterrupt):
            bundle_pdfs.bundle_run(saved_run)
    interrupted = record(saved_run)["delivery_attempts"][-1]
    assert interrupted["status"] == "running"
    assert interrupted["engine"]["code"]
    assert "fonts" not in interrupted
    assert interrupted["review_tools"]["compiler"]["version_output"].startswith(
        "typst 0.15.1 "
    )
    assert len(interrupted["review_tools"]["templates"]) == 2
    assert active_bundles(saved_run) == before
    resumed = bundle_pdfs.bundle_run(saved_run)
    assert resumed["status"] == "completed", resumed["checks"]
    earlier = record(saved_run)["delivery_attempts"][-2]
    assert earlier["status"] == "failed"
    assert earlier["review_tools"] == interrupted["review_tools"]
