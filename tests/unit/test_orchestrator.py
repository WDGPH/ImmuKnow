"""CLI selection, preflight safety, cancellation, and workflow exit status."""

from __future__ import annotations

import io
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from immuknow import orchestrator
from tests.fixtures.sample_input import create_test_input_dataframe


def logging_state() -> tuple[
    int, tuple[logging.Handler, ...], int, tuple[logging.Handler, ...]
]:
    root = logging.getLogger()
    package = logging.getLogger("immuknow")
    return root.level, tuple(root.handlers), package.level, tuple(package.handlers)


@pytest.mark.unit
def test_import_does_not_configure_host_logging(tmp_path: Path) -> None:
    script = """
import logging
root = logging.getLogger()
before = root.level, tuple(root.handlers)
import immuknow.orchestrator
assert (root.level, tuple(root.handlers)) == before
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.unit
class TestParseArgs:
    def test_parse_args_required_arguments(self) -> None:
        with patch(
            "sys.argv", ["immuknow", "students.csv", "--notice-assignments", "a.json"]
        ):
            args = orchestrator.parse_args()
            assert args.input_file == Path("students.csv")
            assert args.notice_assignments == Path("a.json")
            assert not hasattr(args, "language")

    @pytest.mark.parametrize("language", ["en", "fr"])
    def test_parse_args_rejects_positional_language(self, language: str) -> None:
        with patch(
            "sys.argv",
            ["immuknow", "students.csv", language, "--notice-assignments", "a.json"],
        ):
            with pytest.raises(SystemExit) as failure:
                orchestrator.parse_args()
            assert failure.value.code == 2

    def test_parse_args_optional_directories(self) -> None:
        with patch(
            "sys.argv",
            [
                "immuknow",
                "/tmp/input/test.csv",
                "--notice-assignments",
                "a.json",
                "--output",
                "/tmp/output",
                "--config",
                "/etc/config",
            ],
        ):
            args = orchestrator.parse_args()
            assert args.input_file == Path("/tmp/input/test.csv")
            assert args.output_dir == Path("/tmp/output")
            assert args.config_dir == Path("/etc/config")

    def test_parse_args_defaults(self) -> None:
        with patch(
            "sys.argv",
            ["immuknow", "file.csv", "--template", "overdue_agents_v1.fr.typ"],
        ):
            args = orchestrator.parse_args()
            # Defaults should exist
            assert args.output_dir is not None
            assert args.config_dir is not None
            assert args.notice_template == Path("overdue_agents_v1.fr.typ")
            assert args.notice_assignments is None


@pytest.mark.unit
class TestInputAndSelectionValidation:
    def test_missing_input_file(self, tmp_test_dir: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Input file not found"):
            orchestrator.run_pipeline(
                tmp_test_dir / "nonexistent.csv",
                tmp_test_dir / "output",
                notice_assignments=tmp_test_dir / "a.json",
            )

    def test_explicit_selection_is_required(self) -> None:
        with patch("sys.argv", ["immuknow", "students.csv"]):
            with pytest.raises(SystemExit) as failure:
                orchestrator.parse_args()
            assert failure.value.code == 2

    def test_selection_modes_are_mutually_exclusive(self) -> None:
        with patch(
            "sys.argv",
            [
                "immuknow",
                "students.csv",
                "--notice-assignments",
                "a.json",
                "--template",
                "v.fr.typ",
            ],
        ):
            with pytest.raises(SystemExit) as failure:
                orchestrator.parse_args()
            assert failure.value.code == 2

    def test_notice_assignments_missing_manifest_file(self, tmp_path: Path) -> None:
        source = tmp_path / "students.csv"
        source.write_text("test")

        with pytest.raises(FileNotFoundError, match="manifest"):
            orchestrator.run_pipeline(
                source,
                tmp_path / "output",
                notice_assignments=tmp_path / "missing_manifest.json",
            )

    def test_notice_assignments_missing_catalog_raises(self, tmp_path: Path) -> None:
        source = tmp_path / "students.csv"
        source.write_text("test")
        manifest = tmp_path / "assignments.json"
        manifest.write_text("[]")

        config = tmp_path / "config"
        config.mkdir()
        (config / "parameters.yaml").write_text("qr: {enabled: false}")
        with pytest.raises(FileNotFoundError, match="notice_versions.yaml"):
            orchestrator.run_pipeline(
                source,
                tmp_path / "output",
                notice_assignments=manifest,
                config_dir=config,
            )


@pytest.mark.unit
class TestWorkflowBoundaries:
    @pytest.mark.parametrize("both", [False, True])
    def test_callable_requires_exactly_one_selector(
        self, tmp_path: Path, both: bool
    ) -> None:
        selection = (
            {
                "notice_assignments": tmp_path / "a.json",
                "notice_template": tmp_path / "v.fr.typ",
            }
            if both
            else {}
        )
        with pytest.raises(ValueError, match="Choose exactly one"):
            orchestrator.run_pipeline(
                tmp_path / "students.csv", tmp_path / "output", **selection
            )
        assert not (tmp_path / "output").exists()

    @pytest.mark.parametrize(
        "filename",
        ["en.typ", "overdue_v1.typ", "overdue_v1.de.typ", "overdue_v1.en.txt"],
    )
    def test_template_filename_must_identify_version_and_language(
        self, tmp_path: Path, filename: str
    ) -> None:
        template = tmp_path / filename
        template.write_text("never compiled")
        with pytest.raises(ValueError, match="<version_id>.<language>.typ"):
            orchestrator.run_pipeline(
                tmp_path / "students.csv", tmp_path / "output", notice_template=template
            )
        assert not (tmp_path / "output").exists()

    def test_explicit_template_cannot_select_a_different_directory(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        with patch(
            "sys.argv",
            [
                "immuknow",
                "students.csv",
                "--template",
                "v.fr.typ",
                "--templates",
                "another-tree",
            ],
        ):
            assert orchestrator.main() == 1
        assert "supplies its own directory" in capsys.readouterr().err

    def test_removed_notice_template_option_is_rejected(self) -> None:
        with patch(
            "sys.argv",
            [
                "immuknow",
                "students.csv",
                "--notice-assignments",
                "a.json",
                "--notice-template",
                "my_phu",
            ],
        ):
            with pytest.raises(SystemExit) as failure:
                orchestrator.parse_args()
            assert failure.value.code == 2

    def test_output_cancellation_keeps_existing_files(self, tmp_path: Path) -> None:
        source = tmp_path / "students.csv"
        source.write_text("never read after cancellation")
        output = tmp_path / "output"
        output.mkdir()
        existing = output / "existing.pdf"
        existing.write_bytes(b"unchanged")
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        shutil.copyfile(
            orchestrator.DEFAULT_CONFIG_DIR / "notice_versions.yaml",
            config_dir / "notice_versions.yaml",
        )
        manifest = tmp_path / "assignments.json"
        manifest.write_text("[]")
        (config_dir / "parameters.yaml").write_text(
            "pipeline: {before_run: {clear_output_directory: false}}\nqr: {enabled: false}"
        )
        before_logging = logging_state()
        with patch("builtins.input", return_value="no"):
            assert (
                orchestrator.run_pipeline(
                    source, output, notice_assignments=manifest, config_dir=config_dir
                )
                is None
            )
        assert existing.read_bytes() == b"unchanged"
        assert logging_state() == before_logging
        assert not list((output / "logs").glob("run_*.log"))

    @pytest.mark.parametrize("source_kind", ["templates", "config", "input"])
    def test_output_cannot_delete_selected_source(
        self, tmp_path: Path, source_kind: str
    ) -> None:
        output = tmp_path / "output"
        output.mkdir()
        source = tmp_path / "students.csv"
        source.write_text("source")
        kwargs = {}
        if source_kind == "input":
            source = output / "students.csv"
            source.write_text("source")
        else:
            selected = output / source_kind
            selected.mkdir()
            (selected / "keep").write_text("source")
            kwargs["template_dir" if source_kind == "templates" else "config_dir"] = (
                selected
            )
        with pytest.raises(ValueError, match="overlap"):
            orchestrator.run_pipeline(
                source, output, notice_assignments=tmp_path / "a.json", **kwargs
            )
        assert source.read_text() == "source"
        if source_kind != "input":
            assert (selected / "keep").read_text() == "source"

    def test_missing_source_fails_before_creating_output(self, tmp_path: Path) -> None:
        before_logging = logging_state()
        with pytest.raises(FileNotFoundError, match="Input file not found"):
            orchestrator.run_pipeline(
                tmp_path / "missing.csv",
                tmp_path / "output",
                notice_assignments=tmp_path / "a.json",
            )
        assert not (tmp_path / "output").exists()
        assert logging_state() == before_logging

    def test_invalid_csv_restores_host_logging_after_accepted_run(
        self, tmp_path: Path
    ) -> None:
        source = tmp_path / "students.csv"
        frame = create_test_input_dataframe(num_clients=1)
        frame.loc[0, "date_of_birth"] = "2015-02-30"
        frame.to_csv(source, index=False)
        manifest = tmp_path / "assignments.json"
        manifest.write_text(
            json.dumps(
                [
                    {
                        "client_id": str(frame.loc[0, "client_id"]),
                        "template": "overdue_agents_v1.en.typ",
                    }
                ]
            )
        )
        output = tmp_path / "output"
        root = logging.getLogger()
        package = logging.getLogger("immuknow")
        original_root, original_package = root.level, package.level
        root_handler = logging.StreamHandler(io.StringIO())
        package_handler = logging.StreamHandler(io.StringIO())
        root.addHandler(root_handler)
        package.addHandler(package_handler)
        root.setLevel(logging.WARNING)
        package.setLevel(logging.ERROR)
        expected = logging_state()
        try:
            with pytest.raises(ValueError, match="date_of_birth"):
                orchestrator.run_pipeline(source, output, notice_assignments=manifest)
            assert logging_state() == expected
            logs = list((output / "logs").glob("run_*.log"))
            assert len(logs) == 1
            text = logs[0].read_text(encoding="utf-8")
            assert "Run started" in text
            assert "Run failed" in text and "date_of_birth" in text
            assert not list((output / "metadata").glob("completion_*.json"))
        finally:
            root.removeHandler(root_handler)
            root_handler.close()
            package.removeHandler(package_handler)
            package_handler.close()
            root.setLevel(original_root)
            package.setLevel(original_package)


@pytest.mark.unit
class TestErrorHandling:
    def test_pipeline_failure_returns_exit_code_1(self, tmp_path: Path) -> None:
        input_file = tmp_path / "test.csv"
        input_file.write_text("dummy")

        with (
            patch("immuknow.orchestrator.parse_args") as mock_args,
            patch(
                "immuknow.orchestrator.run_pipeline",
                side_effect=Exception("Test execution failure"),
            ) as run,
            patch("builtins.print"),
        ):
            mock_args.return_value = MagicMock(
                input_file=input_file,
                notice_template=None,
                notice_assignments=tmp_path / "assignments.json",
                output_dir=tmp_path / "output",
                config_dir=tmp_path / "config",
                template_dir=None,
            )

            # main() catches all exceptions and returns 1
            exit_code = orchestrator.main()
            assert exit_code == 1
            run.assert_called_once()

    def test_user_cancel_returns_exit_code_2(self, tmp_path: Path) -> None:
        input_file = tmp_path / "test.csv"
        input_file.write_text("dummy")

        with (
            patch("immuknow.orchestrator.parse_args") as mock_args,
            patch("immuknow.orchestrator.run_pipeline", return_value=None) as run,
            patch("builtins.print"),
        ):
            mock_args.return_value = MagicMock(
                input_file=input_file,
                notice_template=None,
                output_dir=tmp_path / "output",
                config_dir=tmp_path / "config",
                template_dir=None,
                notice_assignments=tmp_path / "assignments.json",
            )

            exit_code = orchestrator.main()
            assert exit_code == 2
            run.assert_called_once()
