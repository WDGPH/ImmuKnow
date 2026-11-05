"""Audit a Rust experimental run with independent Python PDF libraries.

The runtime itself never invokes Python. Supply a Python reference run generated
from the identical cohort/config to compare every prepared payload and report.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import pikepdf
import pymupdf


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pixels(page) -> str:
    return hashlib.sha256(
        page.get_pixmap(colorspace=pymupdf.csGRAY, dpi=96).samples
    ).hexdigest()


def audit(path: Path, reference: Path) -> dict:
    run, baseline = path.parent, reference.parent
    record = json.loads(path.read_text())
    expected = json.loads(reference.read_text())
    expected_by_key = {e["row_key"]: e for e in expected["entries"]}
    entries = record["entries"]
    assert record["status"] == "completed", record.get("error")
    assert len(entries) <= len(expected_by_key)
    assert len({e["row_key"] for e in entries}) == len(entries)
    assert len({e["client_id"] for e in entries}) == len(entries)
    representative = set()
    raster_pages = 0
    for name, checksum in record["resources"].items():
        assert digest(run / name) == checksum, name
    for entry in entries:
        key = entry["row_key"]
        gold = expected_by_key[key]
        assert entry["source"] == gold["source"]["values"], (key, "source row")
        facts = json.loads((baseline / gold["facts"]["path"]).read_text())
        assert entry["notice"] == facts, (key, "facts", entry["notice"], facts)
        assert entry["render_report"] == gold["render_summary"], (key, "report")
        original = run / entry["original"]["path"]
        assert digest(original) == entry["original"]["sha256"]
        with pikepdf.open(original) as pdf:
            assert len(pdf.pages) == entry["original"]["pages"]
            assert not pdf.attachments
            assert "/StructTreeRoot" in pdf.Root  # Standalone original retains tags.
        password = facts["client_data"]["date_of_birth_iso"].replace("-", "")
        encrypted = run / entry["encryption"]["path"]
        assert digest(encrypted) == entry["encryption"]["sha256"]
        try:
            pikepdf.open(encrypted, password="")
        except pikepdf.PasswordError:
            pass
        else:
            raise AssertionError((key, "empty password accepted"))
        with pikepdf.open(encrypted, password=password) as pdf:
            settings = pdf.trailer.Encrypt
            assert settings.V == 5 and settings.R == 6 and settings.Length == 256
            assert settings.CF.StdCF.CFM == "/AESV3"
            assert len(pdf.pages) == entry["original"]["pages"]
            assert "/StructTreeRoot" in pdf.Root
        case = (
            entry["assignment"]["template"],
            json.dumps(facts["history"], sort_keys=True),
        )
        if case not in representative:
            representative.add(case)
            with (
                pymupdf.open(original) as got,
                pymupdf.open(baseline / gold["original"]["path"]) as want,
                pymupdf.open(encrypted) as protected,
            ):
                assert protected.authenticate(password)
                assert len(got) == len(want) == len(protected)
                for a, b, c in zip(got, want, protected):
                    assert pixels(a) == pixels(b) == pixels(c), (key, "raster")
                    assert a.get_links() == b.get_links() == c.get_links(), (
                        key,
                        "links",
                    )
                    raster_pages += 1
    members = []
    by_key = {e["row_key"]: e for e in entries}
    for bundle in record["bundles"]:
        output = run / bundle["path"]
        assert digest(output) == bundle["sha256"]
        cursor = 1
        with pikepdf.open(output) as pdf:
            assert len(pdf.pages) == bundle["pages"]
        with pymupdf.open(output) as merged:
            for key in bundle["members"]:
                entry = by_key[key]
                membership = entry["bundle"]
                assert membership["notice_start_page"] == cursor
                assert (
                    membership["notice_end_page"]
                    == cursor + entry["original"]["pages"] - 1
                )
                assert entry["routing"] == "review"  # This particular fictional cohort.
                if int(key.split("-")[-1]) <= 6:
                    with pymupdf.open(run / entry["original"]["path"]) as original:
                        for i, page in enumerate(original):
                            copied = merged[cursor - 1 + i]
                            assert pixels(copied) == pixels(page), (
                                key,
                                "bundle raster",
                            )
                            assert [
                                (x.get("uri"), x["from"]) for x in copied.get_links()
                            ] == [(x.get("uri"), x["from"]) for x in page.get_links()]
                cursor += entry["original"]["pages"]
                members.append(key)
        assert cursor - 1 == bundle["pages"]
        findings = output.with_suffix(".csv")
        with findings.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        assert {r["row_key"] for r in rows} == set(bundle["members"])
        for row in rows:
            m = by_key[row["row_key"]]["bundle"]
            assert int(row["notice_start_page"]) == m["notice_start_page"]
            assert int(row["notice_end_page"]) == m["notice_end_page"]
    assert members == [e["row_key"] for e in entries]
    return {
        "notices": len(entries),
        "pages": sum(e["original"]["pages"] for e in entries),
        "prepared_payload_and_complete_report_parity": True,
        "independently_verified_encrypted_notices": len(entries),
        "representative_cases": len(representative),
        "representative_original_encrypted_pixel_pages": raster_pages,
        "bundles": len(record["bundles"]),
        "membership_and_csv_spans": True,
        "bundle_tagging_preserved": False,
        "timings": record["timings"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.record, args.reference)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
