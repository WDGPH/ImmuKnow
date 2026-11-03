"""Delivery groups use the selected notice and keep every original once."""

from pypdf import PdfReader, PdfWriter

from immuknow import bundle_pdfs


def test_combined_grouping_keeps_distinct_values_and_splits_large_groups(
    tmp_path, monkeypatch
):
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
            "original": {"pages": pages},
        }
        routed.append((entry, {"destination": "delivery"}))
    monkeypatch.setattr(
        bundle_pdfs, "_original_reader", lambda entry, _: PdfReader(entry["path"])
    )
    next_dir = tmp_path / "next"
    next_dir.mkdir()
    attempt = {
        "bundles": [],
        "memberships": {},
        "notice_length": {"enabled": False},
        "checks": [],
    }
    bundle_pdfs._assemble(
        routed, next_dir, tmp_path, ("board", "language", "page_count"), 2, {}, attempt
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

    assert attempt["bundles"][0]["row_keys"] == ["0", "1"]
    assert attempt["bundles"][1]["row_keys"] == ["2"]
