"""Run directories become visible as complete only after successful work."""

from pathlib import Path

import pytest

from immuknow.output_directory import prepare_run_directory, publish_run_directory


def test_success_publishes_after_inner_context_closes(tmp_path: Path) -> None:
    run_dir = prepare_run_directory(tmp_path, "run")
    assert run_dir.name == "run.incomplete"
    (run_dir / "run.json").write_text("{}")
    with publish_run_directory(run_dir, "run"):
        assert not (tmp_path / "run").exists()
    assert (tmp_path / "run" / "run.json").read_text() == "{}"
    assert not run_dir.exists()


@pytest.mark.parametrize("error", [RuntimeError, KeyboardInterrupt])
def test_interruption_retains_incomplete_run(
    tmp_path: Path, error: type[BaseException]
) -> None:
    run_dir = prepare_run_directory(tmp_path, "run")
    with pytest.raises(error), publish_run_directory(run_dir, "run"):
        raise error()
    assert run_dir.is_dir()
    assert not (tmp_path / "run").exists()


def test_existing_final_run_is_preserved(tmp_path: Path) -> None:
    (tmp_path / "run").mkdir()
    with pytest.raises(FileExistsError):
        prepare_run_directory(tmp_path, "run")
