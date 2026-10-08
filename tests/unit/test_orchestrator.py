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

from pipeline import orchestrator


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
        args.template_dir = None

        with pytest.raises(ValueError, match="notice_versions.yaml"):
            orchestrator.validate_args(args)


@pytest.mark.unit
class TestPipelineSteps:
    def test_run_step_1_prepare_output_success(
        self, tmp_output_structure: dict, config_file: Path
    ) -> None:
        with patch("pipeline.orchestrator.prepare_output") as mock_prep:
            mock_prep.prepare_output_directory.return_value = True
            result = orchestrator.run_step_1_prepare_output(
                output_dir=tmp_output_structure["root"],
                log_dir=tmp_output_structure["logs"],
                config_dir=config_file.parent,
            )
            assert result is True

    def test_run_step_1_prepare_output_user_cancels(
        self, tmp_output_structure: dict, config_file: Path
    ) -> None:
        with patch("pipeline.orchestrator.prepare_output") as mock_prep:
            mock_prep.prepare_output_directory.return_value = False
            result = orchestrator.run_step_1_prepare_output(
                output_dir=tmp_output_structure["root"],
                log_dir=tmp_output_structure["logs"],
                config_dir=config_file.parent,
            )
            assert result is False

    def test_run_step_2_passes_selected_config_path(self, tmp_path: Path) -> None:
        preprocess_result = MagicMock(clients=[], warnings=[])
        config_dir = tmp_path / "selected-config"
        config_dir.mkdir()
        (config_dir / "parameters.yaml").write_text(
            "phix_validation:\n  enabled: false\n"
        )

        with (
            patch(
                "pipeline.orchestrator.preprocess.configure_logging",
                return_value=tmp_path / "preprocess.log",
            ),
            patch(
                "pipeline.orchestrator.preprocess.read_input",
                return_value=MagicMock(),
            ),
            patch("pipeline.orchestrator.preprocess.validate_input"),
            patch(
                "pipeline.orchestrator.preprocess.normalize_dataframe",
                return_value=MagicMock(),
            ),
            patch(
                "pipeline.orchestrator.preprocess.check_addresses_complete",
                return_value=MagicMock(),
            ),
            patch(
                "pipeline.orchestrator.preprocess.check_client_info_complete",
                return_value=MagicMock(),
            ) as mock_check_client_info,
            patch(
                "pipeline.orchestrator.preprocess.build_preprocess_result",
                # build_preprocess_result now returns (PreprocessResult, Optional[ReconciliationResult])
                return_value=(preprocess_result, None),
            ) as mock_build_result,
            patch(
                "pipeline.orchestrator.preprocess.write_artifact",
                return_value=tmp_path / "artifact.json",
            ),
            patch("builtins.print"),
        ):
            total_clients, reconciliation_result = orchestrator.run_step_2_preprocess(
                input_dir=tmp_path,
                input_file="students.xlsx",
                output_dir=tmp_path / "output",
                language="en",
                run_id="test_run",
                config_dir=config_dir,
            )

        assert total_clients == 0
        assert reconciliation_result is None
        assert (
            mock_build_result.call_args.args[0] is mock_check_client_info.return_value
        )

        assert mock_build_result.call_args.kwargs["config_path"] == (
            config_dir / "parameters.yaml"
        )

    def test_run_step_4_passes_selected_config_path(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "output"
        template_dir = tmp_path / "templates"
        config_dir = tmp_path / "selected-config"

        with (
            patch(
                "pipeline.orchestrator.generate_notices.prepare_render_jobs",
                return_value=[],
            ) as mock_generate,
            patch("builtins.print"),
        ):
            orchestrator.run_step_4_generate_notices(
                output_dir=output_dir,
                run_id="test_run",
                template_dir=template_dir,
                config_dir=config_dir,
            )

        mock_generate.assert_called_once_with(
            output_dir / "artifacts" / "preprocessed_clients_test_run.json",
            output_dir / "artifacts",
            template_dir,
            config_path=config_dir / "parameters.yaml",
        )

    def test_run_step_3_generate_qr_codes_disabled(
        self, tmp_output_structure: dict, config_file: Path
    ) -> None:
        # Create config with qr disabled
        config_file.write_text("qr:\n  enabled: false\n")

        with (
            patch(
                "pipeline.orchestrator.load_config",
                return_value={"qr": {"enabled": False}},
            ),
            patch("builtins.print"),
        ):
            result = orchestrator.run_step_3_generate_qr_codes(
                output_dir=tmp_output_structure["root"],
                run_id="test_run",
                config_dir=config_file.parent,
            )

        assert result == 0


@pytest.mark.unit
class TestErrorHandling:
    def test_pipeline_failure_returns_exit_code_1(self, tmp_path: Path) -> None:
        # Mock dependencies to reach the step execution
        input_file = tmp_path / "test.xlsx"
        input_file.write_text("dummy")

        with (
            patch("pipeline.orchestrator.parse_args") as mock_args,
            patch("pipeline.orchestrator.load_config", return_value={}),
            patch(
                "pipeline.orchestrator.run_step_1_prepare_output",
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
            )

            # main() catches all exceptions and returns 1
            exit_code = orchestrator.main()
            assert exit_code == 1

    def test_user_cancel_returns_exit_code_2(self, tmp_path: Path) -> None:
        input_file = tmp_path / "test.xlsx"
        input_file.write_text("dummy")

        with (
            patch("pipeline.orchestrator.parse_args") as mock_args,
            patch("pipeline.orchestrator.load_config", return_value={}),
            patch(
                "pipeline.orchestrator.run_step_1_prepare_output", return_value=False
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
                notice_assignments=None,
            )

            exit_code = orchestrator.main()
            assert exit_code == 2
