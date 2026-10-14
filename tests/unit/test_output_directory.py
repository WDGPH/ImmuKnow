"""Run directories preserve previous results and original evidence."""

from pathlib import Path

import pytest

from immuknow.output_directory import cleanup_output, prepare_run_directory


def test_runs_do_not_clear_previous_results(tmp_path: Path) -> None:
    first = prepare_run_directory(tmp_path, "first")
    original = first / "originals" / "row-000001.pdf"
    original.write_bytes(b"original bytes")
    second = prepare_run_directory(tmp_path, "second")
    assert original.read_bytes() == b"original bytes"
    assert second != first
    with pytest.raises(FileExistsError):
        prepare_run_directory(tmp_path, "first")
    disposable = first / "work" / "temporary"
    disposable.write_text("discard")
    cleanup_output(
        first,
        {
            "pipeline": {
                "after_run": {"remove_artifacts": True, "remove_unencrypted_pdfs": True}
            },
            "bundling": {"bundle_size": 10},
        },
    )
    assert original.read_bytes() == b"original bytes"
    assert not (first / "work").exists()
    assert (first / "facts").is_dir()
