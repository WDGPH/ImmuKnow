"""Independent saved-PDF/page-range verification, always outside throughput timing.
Requires PyMuPDF. Compares actual decoded page streams, text and URI rectangles
from each original to its actual pages in each bundle. Uses no Core PDF parser.
"""

import argparse
import hashlib
import json
from pathlib import Path

import pymupdf as fitz


def fingerprint(document, page):
    streams = b"".join(document.xref_stream(xref) for xref in page.get_contents())
    links = sorted(
        (link["uri"], tuple(link["from"]))
        for link in page.get_links()
        if link.get("uri")
    )
    return {
        "streams_sha256": hashlib.sha256(streams).hexdigest(),
        "text_sha256": hashlib.sha256(page.get_text().encode()).hexdigest(),
        "rectangle": tuple(page.rect),
        "uri_rectangles": links,
    }


def verify(record_path):
    record = json.loads(record_path.read_text())
    root = record_path.parent
    rows = {}
    original_pages = 0
    bundled_pages = 0
    for entry in record["entries"]:
        original = entry["original"]
        assert original["status"] == "completed"
        with fitz.open(root / original["path"]) as document:
            assert len(document) == original["pages"], entry["row_key"]
            rows[entry["row_key"]] = [fingerprint(document, page) for page in document]
            original_pages += len(document)
    members = []
    by_key = {e["row_key"]: e for e in record["entries"]}
    for bundle in record["bundles"]:
        with fitz.open(root / bundle["path"]) as document:
            assert len(document) == bundle["pages"]
            cursor = 0
            for key in bundle["members"]:
                membership = by_key[key]["bundle"]
                assert membership["notice_start_page"] == cursor + 1
                for page_number, expected in enumerate(rows[key], cursor):
                    assert fingerprint(document, document[page_number]) == expected, (
                        bundle["path"],
                        key,
                        page_number + 1,
                    )
                cursor += len(rows[key])
                assert membership["notice_end_page"] == cursor
                members.append(key)
            assert cursor == len(document)
            bundled_pages += len(document)
    assert len(members) == len(rows) and set(members) == set(rows)
    return {
        "records": len(rows),
        "original_pages": original_pages,
        "bundled_pages": bundled_pages,
        "bundle_count": len(record["bundles"]),
        "each_record_bundled_exactly_once": True,
        "actual_page_counts_and_inclusive_ranges_match": True,
        "each_bundle_page_matches_original_decoded_streams_text_and_uri_rectangles": True,
        "engine": "PyMuPDF " + fitz.VersionBind,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("record", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = verify(args.record)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)
