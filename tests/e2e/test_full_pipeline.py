"""The CLI delivers an explicit multilingual cohort with decryptable copies."""

import csv
import json
from pathlib import Path

import pytest
from pypdf import PdfReader

from tests.integration.test_native_pipeline import prepare_cohort, run_cli

pytestmark = pytest.mark.e2e


def test_full_cli_cohort_preserves_selected_languages_and_encryption(tmp_path: Path):
    command, output, _ = prepare_cohort(tmp_path, ("en", "fr"), encrypted=True)
    result = run_cli(command, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    record_path = next(output.glob("*/run.json"))
    record = json.loads(record_path.read_text())
    assert record["status"] in {"completed", "completed_with_warnings"}
    assert len(record["entries"]) == 2
    assert {e["assignment"]["language"] for e in record["entries"]} == {"en", "fr"}
    with Path(command[3]).open(newline="", encoding="utf-8") as source:
        passwords = {
            row["client_id"]: row["date_of_birth"].replace("-", "")
            for row in csv.DictReader(source)
        }
    for entry in record["entries"]:
        assert entry["original"]["status"] == "completed"
        original = PdfReader(record_path.parent / entry["original"]["path"])
        assert original.root_object["/Lang"] == entry["assignment"]["language"] + "-CA"
        assert entry["client_id"] in original.pages[0].extract_text()
        assert len(original.pages) == 2
        assert entry["encryption"]["status"] == "completed"
        encrypted = PdfReader(record_path.parent / entry["encryption"]["path"])
        assert encrypted.is_encrypted and encrypted.decrypt(
            passwords[entry["client_id"]]
        )
        assert entry["bundle"] is not None
    attempt = record["delivery_attempts"][0]
    assert attempt["status"] == "completed"
    assert [key for bundle in attempt["bundles"] for key in bundle["row_keys"]] == [
        "row-000001",
        "row-000002",
    ]
    assert (record_path.parent / "report.html").is_file()
