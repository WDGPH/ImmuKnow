"""Delivery groups use the selected notice and keep every original once."""

import csv
import json

from pypdf import PdfWriter

from immuknow import bundle_pdfs


def test_combined_grouping_keeps_distinct_values_and_splits_large_groups(tmp_path):
    choices = [
        ("A", "en", 1),
        ("A", "en", 1),
        ("A", "en", 1),
        ("A", "fr", 1),
        ("A", "en", 2),
        ("B", "en", 1),
    ]
    routed = []
    for number, (board, language, pages) in enumerate(choices):
        writer = PdfWriter()
        for _ in range(pages):
            writer.add_blank_page(width=100, height=100)
        path = tmp_path / f"{number}.pdf"
        writer.write(path)
        entry = {
            "row_key": str(number),
            "path": path,
            "facts": {"prepared": {"board": {"id": board, "name": board}}},
            "assignment": {"language": language},
            "original": {"pages": pages, "path": path.name},
        }
        routed.append((entry, {"destination": "review" if number == 1 else "delivery"}))
    next_dir = tmp_path / "next"
    next_dir.mkdir()
    attempt = {
        "directory": "bundles/test",
        "bundles": [],
        "memberships": {},
        "notice_length": {"enabled": False},
        "checks": [],
    }
    bundle_pdfs._assemble(
        routed, next_dir, ("board", "language", "page_count"), 2, attempt, tmp_path
    )
    assert len(attempt["bundles"]) == 5
    assert {key for bundle in attempt["bundles"] for key in bundle["row_keys"]} == {
        str(n) for n in range(6)
    }
    assert [bundle["group_id"] for bundle in attempt["bundles"]] == [
        ["A", "en", "1"],
        ["A", "en", "1"],
        ["A", "en", "2"],
        ["A", "fr", "1"],
        ["B", "en", "1"],
    ]

    assert all(bundle["destination"] == "bundle" for bundle in attempt["bundles"])
    assert attempt["bundles"][0]["row_keys"] == ["0", "1"]
    assert attempt["bundles"][1]["row_keys"] == ["2"]


def test_findings_preserve_result_tokens_and_bundle_page_offsets(tmp_path):
    record = {
        "run_id": "test-run",
        "warning_acceptances": [{"token": "accepted", "reason": "Reviewed"}],
        "entries": [
            {
                "row_key": "row-1",
                "client_id": "1",
                "assignment": {},
                "original": {"pages": 3},
                "checks": [],
            },
            {
                "row_key": "row-2",
                "client_id": "2",
                "assignment": {},
                "original": {"pages": 1},
                "checks": [],
            },
        ],
    }
    attempt = {
        "number": 2,
        "bundles": [{"path": "bundles/a.pdf", "row_keys": ["row-1", "row-2"]}],
        "memberships": {
            "row-1": {
                "bundle": {
                    "path": "bundles/a.pdf",
                    "notice_start_page": 4,
                    "notice_end_page": 6,
                },
                "routing": {
                    "destination": "review",
                    "reason": "Warnings",
                    "withheld": False,
                },
            },
            "row-2": {
                "bundle": {
                    "path": "bundles/a.pdf",
                    "notice_start_page": 7,
                    "notice_end_page": 7,
                },
                "routing": {
                    "destination": "review",
                    "reason": "Withheld",
                    "withheld": True,
                },
            },
        },
        "evaluations": {
            "row-1": {
                "results": [
                    {
                        "code": "content.multiple_links",
                        "stage": "render",
                        "status": "pass",
                        "message": "ok",
                    },
                    {
                        "code": "content.multiple_links",
                        "stage": "render",
                        "status": "warn",
                        "message": "first",
                        "page": 2,
                        "measurements": {"width": 10},
                    },
                    {
                        "code": "content.multiple_links",
                        "stage": "render",
                        "status": "warn",
                        "message": "second",
                    },
                ],
                "warning_tokens": {
                    "content.multiple_links:1": "accepted",
                    "content.multiple_links:2": "unaccepted",
                },
            },
            "row-2": {"results": [], "warning_tokens": {}},
        },
    }
    record["entries"].append(
        {
            "row_key": "row-3",
            "client_id": "3",
            "assignment": {},
            "original": {"pages": 1},
            "checks": [],
        }
    )
    attempt["bundles"].append({"path": "bundles/b.pdf", "row_keys": ["row-3"]})
    attempt["memberships"]["row-3"] = {
        "bundle": {
            "path": "bundles/b.pdf",
            "notice_start_page": 1,
            "notice_end_page": 1,
        },
        "routing": {"destination": "delivery", "reason": "Passed", "withheld": False},
    }
    attempt["evaluations"]["row-3"] = {"results": [], "warning_tokens": {}}
    bundle_pdfs._write_findings(tmp_path, record, attempt)
    with (tmp_path / "b.csv").open(newline="") as stream:
        clean = csv.DictReader(stream)
        assert clean.fieldnames
        assert list(clean) == []
    clean_csv = attempt["bundles"][1]["findings_csv"]
    assert isinstance(clean_csv, dict)
    assert clean_csv["rows"] == 0
    with (tmp_path / "a.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    first, second, withheld = rows
    assert (first["original_page"], first["bundle_page"]) == ("2", "5")
    assert json.loads(first["measurements_json"]) == {"width": 10}
    assert (
        first["warning_token"],
        first["warning_accepted"],
        first["acceptance_reason"],
    ) == ("accepted", "true", "Reviewed")
    assert (
        second["warning_token"],
        second["warning_accepted"],
        second["bundle_page"],
    ) == ("unaccepted", "false", "")
    assert withheld["row_key"] == "row-2" and withheld["withheld"] == "true"
    assert withheld["code"] == withheld["effective_status"] == ""


def test_spreadsheet_cells_neutralize_formula_and_leading_controls():
    for value in ("=formula", "  +formula", "-formula", "@formula", "\ttext", "\ntext"):
        assert bundle_pdfs._spreadsheet_cell(value) == "'" + value
    assert (
        bundle_pdfs._spreadsheet_cell('Ordinary, "quoted" text')
        == 'Ordinary, "quoted" text'
    )
