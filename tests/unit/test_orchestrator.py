"""CLI selection, preflight safety, cancellation, and workflow exit status."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from immuknow import orchestrator


@pytest.mark.unit
class TestParseArgs:
    def test_parse_args_required_arguments(self) -> None:
        with patch(
            "sys.argv", ["immuknow", "students.csv", "--notice-assignments", "a.json"]
        ):
            args = orchestrator.parse_args()
            assert args.input_file == "students.csv"
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
                "test.csv",
                "--notice-assignments",
                "a.json",
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
        with patch(
            "sys.argv",
            ["immuknow", "file.csv", "--notice-template", "overdue_agents_v1.fr.typ"],
        ):
            args = orchestrator.parse_args()
            # Defaults should exist
            assert args.input_dir is not None
            assert args.output_dir is not None
            assert args.config_dir is not None
            assert args.notice_template == Path("overdue_agents_v1.fr.typ")
            assert args.notice_assignments is None


@pytest.mark.unit
class TestValidateArgs:
    def test_validate_args_missing_input_file(self, tmp_test_dir: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Input file not found"):
            orchestrator.run_pipeline(
                tmp_test_dir / "nonexistent.csv",
                tmp_test_dir / "output",
                notice_assignments=tmp_test_dir / "a.json",
            )

    def test_validate_args_existing_input_file(self, tmp_test_dir: Path) -> None:
        test_file = tmp_test_dir / "students.csv"
        test_file.write_text("test")

        args = MagicMock()
        args.input_file = "students.csv"
        args.input_dir = tmp_test_dir
        args.notice_assignments = tmp_test_dir / "a.json"
        args.notice_template = None
        args.custom_templates = None
        args.template_dir = None  # Use default templates

        # Should not raise
        orchestrator.validate_args(args)

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
                "--notice-template",
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

    @pytest.mark.parametrize("option", ["--template", "--templates"])
    def test_explicit_template_cannot_select_a_different_directory(
        self, option: str
    ) -> None:
        with patch(
            "sys.argv",
            [
                "immuknow",
                "students.csv",
                "--notice-template",
                "v.fr.typ",
                option,
                "another-tree",
            ],
        ):
            args = orchestrator.parse_args()
        with pytest.raises(ValueError, match="supplies its own directory"):
            orchestrator.validate_args(args)

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
        with patch("builtins.input", return_value="no"):
            assert (
                orchestrator.run_pipeline(
                    source, output, notice_assignments=manifest, config_dir=config_dir
                )
                is None
            )
        assert existing.read_bytes() == b"unchanged"

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
        with pytest.raises(FileNotFoundError, match="Input file not found"):
            orchestrator.run_pipeline(
                tmp_path / "missing.csv",
                tmp_path / "output",
                notice_assignments=tmp_path / "a.json",
            )
        assert not (tmp_path / "output").exists()


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
                input_file="test.csv",
                notice_template=None,
                notice_assignments=tmp_path / "assignments.json",
                input_dir=tmp_path,
                output_dir=tmp_path / "output",
                config_dir=tmp_path / "config",
                template_dir=None,
                custom_templates=None,
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
                input_file="test.csv",
                notice_template=None,
                input_dir=tmp_path,
                output_dir=tmp_path / "output",
                config_dir=tmp_path / "config",
                template_dir=None,
                custom_templates=None,
                notice_assignments=tmp_path / "assignments.json",
            )

            exit_code = orchestrator.main()
            assert exit_code == 2
            run.assert_called_once()
