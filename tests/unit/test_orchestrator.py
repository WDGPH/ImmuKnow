"""Unit tests for orchestrator module - Pipeline orchestration and argument handling.

Tests cover:
- Command-line argument parsing and validation
- Argument validation (file exists, language is valid)
- Pipeline step orchestration (steps 1-9 sequencing)
- Configuration loading
- Error handling and logging
- Return codes and exit status

Real-world significance:
- Entry point for entire pipeline (orchestrator.main())
- Argument validation prevents downstream errors
- Orchestration order ensures correct data flow (Step N output → Step N+1 input)
- Error handling must gracefully report problems to users
- Run ID generation enables comparing multiple pipeline runs
- Used by both CLI (viper command) and programmatic callers
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from immuknow import orchestrator


@pytest.mark.unit
class TestParseArgs:
    def test_parse_args_required_arguments(self) -> None:
        with patch("sys.argv", ["viper", "students.xlsx", "en"]):
            args = orchestrator.parse_args()
            assert args.input_file == "students.xlsx"
            assert args.language == "en"

    def test_parse_args_language_choices(self) -> None:
        # Valid language
        with patch("sys.argv", ["viper", "file.xlsx", "fr"]):
            args = orchestrator.parse_args()
            assert args.language == "fr"

    def test_parse_args_optional_directories(self) -> None:
        with patch(
            "sys.argv",
            [
                "viper",
                "test.xlsx",
                "en",
                "--input",
                "/tmp/input",
                "--output",
                "/tmp/output",
                "--config",
                "/etc/config",
            ],
        ):
            args = orchestrator.parse_args()
            assert args.input_dir == Path("/tmp/input")
            assert args.output_dir == Path("/tmp/output")
            assert args.config_dir == Path("/etc/config")

    def test_parse_args_defaults(self) -> None:
        with patch("sys.argv", ["viper", "file.xlsx", "en"]):
            args = orchestrator.parse_args()
            # Defaults should exist
            assert args.input_dir is not None
            assert args.output_dir is not None
            assert args.config_dir is not None


@pytest.mark.unit
class TestValidateArgs:
    def test_validate_args_missing_input_file(self, tmp_test_dir: Path) -> None:
        args = MagicMock()
        args.input_file = "nonexistent.xlsx"
        args.input_dir = tmp_test_dir

        with pytest.raises(FileNotFoundError, match="Input file not found"):
            orchestrator.validate_args(args)

    def test_validate_args_existing_input_file(self, tmp_test_dir: Path) -> None:
        test_file = tmp_test_dir / "students.xlsx"
        test_file.write_text("test")

        args = MagicMock()
        args.input_file = "students.xlsx"
        args.input_dir = tmp_test_dir
        args.notice_assignments = None
        args.language = "en"
        args.custom_templates = None
        args.template_dir = None  # Use default templates

        # Should not raise
        orchestrator.validate_args(args)

    def test_language_required_in_fixed_mode(self, tmp_test_dir: Path) -> None:
        test_file = tmp_test_dir / "students.xlsx"
        test_file.write_text("test")

        args = MagicMock()
        args.input_file = "students.xlsx"
        args.input_dir = tmp_test_dir
        args.notice_assignments = None
        args.language = None

        with pytest.raises(ValueError, match="language is required"):
            orchestrator.validate_args(args)

    def test_language_warned_and_cleared_in_manifest_mode(self, tmp_path: Path) -> None:
        xlsx = tmp_path / "students.xlsx"
        xlsx.write_text("test")
        manifest = tmp_path / "assignments.json"
        manifest.write_text("[]")
        catalog = tmp_path / "notice_versions.yaml"
        catalog.write_text("schema_version: 1\n")

        args = MagicMock()
        args.input_file = "students.xlsx"
        args.input_dir = tmp_path
        args.notice_assignments = manifest
        args.language = "en"
        args.config_dir = tmp_path
        args.custom_templates = None
        args.template_dir = None

        with patch("builtins.print") as mock_print:
            orchestrator.validate_args(args)

        assert args.language is None
        # Warning must have been printed
        printed = " ".join(
            str(c) for call in mock_print.call_args_list for c in call.args
        )
        assert "Warning" in printed or "ignored" in printed.lower()

    def test_notice_assignments_missing_manifest_file(self, tmp_path: Path) -> None:
        xlsx = tmp_path / "students.xlsx"
        xlsx.write_text("test")
        (tmp_path / "notice_versions.yaml").write_text("schema_version: 1\n")

        args = MagicMock()
        args.input_file = "students.xlsx"
        args.input_dir = tmp_path
        args.notice_assignments = tmp_path / "missing_manifest.json"
        args.language = None
        args.config_dir = tmp_path
        args.custom_templates = None
        args.template_dir = None

        with pytest.raises(FileNotFoundError, match="manifest"):
            orchestrator.validate_args(args)

    def test_notice_assignments_missing_catalog_raises(self, tmp_path: Path) -> None:
        xlsx = tmp_path / "students.xlsx"
        xlsx.write_text("test")
        manifest = tmp_path / "assignments.json"
        manifest.write_text("[]")

        args = MagicMock()
        args.input_file = "students.xlsx"
        args.input_dir = tmp_path
        args.notice_assignments = manifest
        args.language = None
        args.config_dir = tmp_path  # no notice_versions.yaml here
        args.custom_templates = None
        args.template_dir = None

        with pytest.raises(ValueError, match="notice_versions.yaml"):
            orchestrator.validate_args(args)


@pytest.mark.unit
class TestWorkflowBoundaries:
    def test_output_cancellation_keeps_existing_files(self, tmp_path: Path) -> None:
        source = tmp_path / "students.xlsx"
        source.write_text("never read after cancellation")
        output = tmp_path / "output"
        output.mkdir()
        existing = output / "existing.pdf"
        existing.write_bytes(b"unchanged")
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        (config_dir / "parameters.yaml").write_text(
            "pipeline: {before_run: {clear_output_directory: false}}\nqr: {enabled: false}"
        )
        with patch("builtins.input", return_value="no"):
            assert (
                orchestrator.run_pipeline(source, output, "en", config_dir=config_dir)
                is None
            )
        assert existing.read_bytes() == b"unchanged"

    @pytest.mark.parametrize("source_kind", ["templates", "config", "input"])
    def test_output_cannot_delete_selected_source(
        self, tmp_path: Path, source_kind: str
    ) -> None:
        output = tmp_path / "output"
        output.mkdir()
        source = tmp_path / "students.xlsx"
        source.write_text("source")
        kwargs = {}
        if source_kind == "input":
            source = output / "students.xlsx"
            source.write_text("source")
        else:
            selected = output / source_kind
            selected.mkdir()
            (selected / "keep").write_text("source")
            kwargs["template_dir" if source_kind == "templates" else "config_dir"] = (
                selected
            )
        with pytest.raises(ValueError, match="overlap"):
            orchestrator.run_pipeline(source, output, "en", **kwargs)
        assert source.read_text() == "source"
        if source_kind != "input":
            assert (selected / "keep").read_text() == "source"

    def test_missing_source_fails_before_creating_output(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Input file not found"):
            orchestrator.run_pipeline(
                tmp_path / "missing.xlsx", tmp_path / "output", "en"
            )
        assert not (tmp_path / "output").exists()


@pytest.mark.unit
class TestErrorHandling:
    def test_pipeline_failure_returns_exit_code_1(self, tmp_path: Path) -> None:
        # Mock dependencies to reach the step execution
        input_file = tmp_path / "test.xlsx"
        input_file.write_text("dummy")

        with (
            patch("immuknow.orchestrator.parse_args") as mock_args,
            patch("immuknow.orchestrator.load_config", return_value={}),
            patch(
                "immuknow.orchestrator.run_pipeline",
                side_effect=Exception("Test execution failure"),
            ),
            patch("builtins.print"),
        ):
            mock_args.return_value = MagicMock(
                input_file="test.xlsx",
                language="en",
                input_dir=tmp_path,
                output_dir=tmp_path / "output",
                config_dir=tmp_path / "config",
                template_dir=None,
                custom_templates=None,
            )

            # main() catches all exceptions and returns 1
            exit_code = orchestrator.main()
            assert exit_code == 1

    def test_user_cancel_returns_exit_code_2(self, tmp_path: Path) -> None:
        input_file = tmp_path / "test.xlsx"
        input_file.write_text("dummy")

        with (
            patch("immuknow.orchestrator.parse_args") as mock_args,
            patch("immuknow.orchestrator.load_config", return_value={}),
            patch("immuknow.orchestrator.run_pipeline", return_value=None),
            patch("builtins.print"),
        ):
            mock_args.return_value = MagicMock(
                input_file="test.xlsx",
                language="en",
                input_dir=tmp_path,
                output_dir=tmp_path / "output",
                config_dir=tmp_path / "config",
                template_dir=None,
                custom_templates=None,
                notice_assignments=None,
            )

            exit_code = orchestrator.main()
            assert exit_code == 2
