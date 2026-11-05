"""Check bundle contents, explicit page counts and independent publication."""

from __future__ import annotations

from tests.fixtures.project import copy_project

import json
import shutil
from pathlib import Path

import pymupdf
import pikepdf
import pytest
import yaml
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    NameObject,
    NumberObject,
    TextStringObject,
)

from immuknow import bundle_pdfs, run_report
from immuknow.orchestrator import run_pipeline
from tests.fixtures.sample_input import create_test_input_dataframe

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


@pytest.mark.parametrize("pdf_version", ["1.7", "2.0"])
def test_assembly_preserves_pdf_version_and_internal_link_targets(
    tmp_path: Path, pdf_version: str
) -> None:
    routed = []
    for index in range(2):
        source = tmp_path / f"source-{index}.pdf"
        writer = PdfWriter()
        writer.pdf_header = "%PDF-" + pdf_version
        writer.add_blank_page(width=300, height=400)
        writer.add_blank_page(width=300, height=400)
        writer.add_named_destination("target", 1)
        for top, destination in enumerate(
            [
                ArrayObject([writer.pages[1].indirect_reference, NameObject("/Fit")]),
                TextStringObject("target"),
            ]
        ):
            writer.add_annotation(
                0,
                DictionaryObject(
                    {
                        NameObject("/Type"): NameObject("/Annot"),
                        NameObject("/Subtype"): NameObject("/Link"),
                        NameObject("/Rect"): ArrayObject(
                            [
                                NumberObject(n)
                                for n in (20, 20 + top * 40, 120, 45 + top * 40)
                            ]
                        ),
                        NameObject("/A"): DictionaryObject(
                            {
                                NameObject("/S"): NameObject("/GoTo"),
                                NameObject("/D"): destination,
                            }
                        ),
                    }
                ),
            )
        with source.open("wb") as stream:
            writer.write(stream)
        routed.append(
            (
                {
                    "row_key": f"row-{index}",
                    "original": {"path": source.name, "pages": 2},
                },
                {"destination": "delivery"},
            )
        )
    output = tmp_path / "bundles"
    output.mkdir()
    attempt = {"directory": "bundles", "bundles": [], "memberships": {}}
    bundle_pdfs._assemble(routed, output, (), 100, attempt, tmp_path)
    combined = tmp_path / attempt["bundles"][0]["path"]
    assert PdfReader(combined).pdf_header == "%PDF-" + pdf_version
    with pymupdf.open(combined) as document:
        assert len(document) == 4
        for offset in (0, 2):
            links = document[offset].get_links()
            assert [link["kind"] for link in links] == [
                pymupdf.LINK_GOTO,
                pymupdf.LINK_NAMED,
            ]
            assert all(link["page"] == offset + 1 for link in links)


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
        entry["bundle"]["path"]: (run_dir / entry["bundle"]["path"]).read_bytes()
        for entry in record(run_dir)["entries"]
        if entry["bundle"]
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
    assert [check["status"] for check in checks] == ["fail"]
    assert checks[0]["measurements"]["notices"] == [
        {"row_key": first["row_key"], "pages": expected},
        {"row_key": long["row_key"], "pages": long["original"]["pages"]},
        {"row_key": last["row_key"], "pages": expected},
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


def test_written_bundle_count_is_checked_before_publication(saved_run, monkeypatch):
    before = record(saved_run)
    save = pikepdf.Pdf.save

    def extra_page(writer, destination, **kwargs):
        if ".incomplete" in str(destination):
            writer.add_blank_page(page_size=(100, 100))
        return save(writer, destination, **kwargs)

    monkeypatch.setattr(pikepdf.Pdf, "save", extra_page)
    result = bundle_pdfs.bundle_run(saved_run, policy={})
    assert result["status"] == "failed"
    assert "page count does not match memberships" in result["checks"][-1]["message"]
    assert [entry["bundle"] for entry in record(saved_run)["entries"]] == [
        entry["bundle"] for entry in before["entries"]
    ]


def test_review_reuses_pdf_bytes_and_keeps_previous_set(saved_run, monkeypatch):
    first = bundle_pdfs.bundle_run(saved_run, policy={})
    assert first["status"] == "completed", first["checks"]
    files = {
        artifact["path"]: (saved_run / artifact["path"]).read_bytes()
        for artifact in first["bundles"]
    }

    def unexpected_read(*args, **kwargs):
        raise AssertionError("Review should not assemble or parse any PDFs")

    monkeypatch.setattr(bundle_pdfs, "_assemble", unexpected_read)
    monkeypatch.setattr(bundle_pdfs, "PdfReader", unexpected_read)
    token = next(
        iter(next(iter(first["evaluations"].values()))["warning_tokens"].values())
    )
    reviewed = bundle_pdfs.bundle_run(
        saved_run, accept=[token], reason="Inspected notice"
    )
    assert reviewed["status"] == "completed", reviewed["checks"]
    assert reviewed["reused_from"] == first["number"]
    for old, new in zip(first["bundles"], reviewed["bundles"]):
        assert old["path"] != new["path"]
        assert old["sha256"] == new["sha256"]
        assert (saved_run / new["path"]).read_bytes() == files[old["path"]]
        assert (saved_run / old["path"]).read_bytes() == files[old["path"]]
    assert record(saved_run)["delivery_attempts"][-2] == first


@pytest.mark.parametrize(
    "settings, message",
    [
        ({"bundle_size": -1}, "nonnegative integer"),
        ({"bundle_size": 0}, "bundle_size above zero"),
    ],
)
def test_invalid_bundle_settings_are_reported(saved_run, settings, message):
    saved = record(saved_run)
    saved["configuration"]["effective"]["bundling"] = settings
    run_report.write_report(saved_run, saved)
    result = bundle_pdfs.bundle_run(saved_run)
    assert result["status"] == "failed"
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
