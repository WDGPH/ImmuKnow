"""Output preparation, log preservation, and configured cleanup after delivery."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from immuknow import output_files


@pytest.mark.unit
class TestPurgeOutputDirectory:
    """Unit tests for directory purging logic."""

    def test_purge_removes_all_files_except_logs(
        self, tmp_output_structure: dict
    ) -> None:
        """Verify purge removes files but preserves log directory.

        Real-world significance:
        - Pipeline can be re-run without losing historical logs
        - Logs are kept in output/logs/ and should never be deleted
        - Other artifacts should be removed for fresh run
        """
        output_dir = tmp_output_structure["root"]
        log_dir = tmp_output_structure["logs"]

        # Create test files in various directories
        (tmp_output_structure["artifacts"] / "test.json").write_text("test")
        (tmp_output_structure["pdf_individual"] / "test.pdf").write_text("test")
        (tmp_output_structure["metadata"] / "metadata.json").write_text("test")
        log_file = log_dir / "immuknow.log"
        log_file.write_text("important log data")

        output_files.purge_output_directory(output_dir, log_dir)

        # Verify non-log files removed
        assert not (tmp_output_structure["artifacts"] / "test.json").exists()
        assert not (tmp_output_structure["pdf_individual"] / "test.pdf").exists()
        assert not (tmp_output_structure["metadata"] / "metadata.json").exists()

        # Verify log directory and files preserved
        assert log_dir.exists()
        assert log_file.exists()
        assert log_file.read_text() == "important log data"

    def test_purge_removes_entire_directories(self, tmp_output_structure: dict) -> None:
        """Verify purge removes entire directories except logs.

        Real-world significance:
        - Should clean up nested directory structures (e.g., artifacts/)
        - Ensures no stale files interfere with new pipeline run
        """
        output_dir = tmp_output_structure["root"]
        log_dir = tmp_output_structure["logs"]

        # Create nested structure in artifacts
        nested = tmp_output_structure["artifacts"] / "qr_codes" / "nested"
        nested.mkdir(parents=True, exist_ok=True)
        (nested / "code.png").write_text("image")

        output_files.purge_output_directory(output_dir, log_dir)

        # Verify entire artifacts directory is removed
        assert not tmp_output_structure["artifacts"].exists()

    def test_purge_with_symlink_to_logs_preserves_it(
        self, tmp_output_structure: dict
    ) -> None:
        """Verify purge doesn't remove symlinks to log directory.

        Real-world significance:
        - Some setups might use symlinks for log redirection
        - Should handle symlinks correctly without breaking logs
        """
        output_dir = tmp_output_structure["root"]
        log_dir = tmp_output_structure["logs"]

        # Create a symlink to logs directory
        symlink = output_dir / "logs_link"
        symlink.symlink_to(log_dir)

        output_files.purge_output_directory(output_dir, log_dir)

        assert symlink.is_symlink()
        assert symlink.resolve() == log_dir.resolve()


@pytest.mark.unit
class TestPrepareOutputDirectory:
    """Unit tests for prepare_output_directory function."""

    def test_prepare_creates_new_directory(self, tmp_test_dir: Path) -> None:
        """Verify directory is created if it doesn't exist.

        Real-world significance:
        - First-time pipeline run: output directory doesn't exist yet
        - Must create directory structure for subsequent steps
        """
        output_dir = tmp_test_dir / "new_output"
        log_dir = output_dir / "logs"

        result = output_files.prepare_output_directory(
            output_dir, log_dir, auto_remove=False
        )

        assert result is True
        assert output_dir.exists()
        assert log_dir.exists()

    def test_prepare_with_auto_remove_true_cleans_existing(
        self, tmp_output_structure: dict
    ) -> None:
        """Verify auto_remove=True cleans existing directory without prompting.

        Real-world significance:
        - Automated pipeline runs: auto_remove=True prevents user prompts
        - Removes old artifacts and reuses same output directory
        - Logs directory is preserved
        """
        output_dir = tmp_output_structure["root"]
        log_dir = tmp_output_structure["logs"]

        # Create test files
        (tmp_output_structure["artifacts"] / "old.json").write_text("old")
        (log_dir / "important.log").write_text("logs")

        result = output_files.prepare_output_directory(
            output_dir, log_dir, auto_remove=True
        )

        assert result is True
        assert not (tmp_output_structure["artifacts"] / "old.json").exists()
        assert (log_dir / "important.log").exists()

    def test_prepare_with_auto_remove_false_prompts_user(
        self, tmp_output_structure: dict
    ) -> None:
        """Verify auto_remove=False prompts user before cleaning.

        Real-world significance:
        - Interactive mode: user should confirm before deleting existing output
        - Prevents accidental data loss in manual pipeline runs
        """
        output_dir = tmp_output_structure["root"]
        log_dir = tmp_output_structure["logs"]

        # Mock prompt to return True (user confirms)
        def mock_prompt(path: Path) -> bool:
            return True

        result = output_files.prepare_output_directory(
            output_dir, log_dir, auto_remove=False, prompt=mock_prompt
        )

        assert result is True

    def test_prepare_aborts_when_user_declines(
        self, tmp_output_structure: dict
    ) -> None:
        """Verify cleanup is skipped when user declines prompt.

        Real-world significance:
        - User can cancel pipeline if directory exists
        - Files are not deleted if user says No
        """
        output_dir = tmp_output_structure["root"]
        log_dir = tmp_output_structure["logs"]

        (tmp_output_structure["artifacts"] / "preserve_me.json").write_text("precious")

        def mock_prompt(path: Path) -> bool:
            return False

        result = output_files.prepare_output_directory(
            output_dir, log_dir, auto_remove=False, prompt=mock_prompt
        )

        assert result is False
        assert (tmp_output_structure["artifacts"] / "preserve_me.json").exists()


@pytest.mark.unit
class TestDefaultPrompt:
    """Unit tests for the default prompt function."""

    def test_default_prompt_accepts_y(self, tmp_test_dir: Path) -> None:
        """Verify 'y' response is accepted.

        Real-world significance:
        - User should be able to confirm with 'y'
        - Lowercase letter should work
        """
        with patch("builtins.input", return_value="y"):
            result = output_files.default_prompt(tmp_test_dir)
            assert result is True

    def test_default_prompt_accepts_yes(self, tmp_test_dir: Path) -> None:
        """Verify 'yes' response is accepted.

        Real-world significance:
        - User should be able to confirm with full word 'yes'
        - Common user response pattern
        """
        with patch("builtins.input", return_value="yes"):
            result = output_files.default_prompt(tmp_test_dir)
            assert result is True

    def test_default_prompt_rejects_n(self, tmp_test_dir: Path) -> None:
        """Verify 'n' response is rejected (returns False).

        Real-world significance:
        - User should be able to cancel with 'n'
        - Default is No if user is uncertain
        """
        with patch("builtins.input", return_value="n"):
            result = output_files.default_prompt(tmp_test_dir)
            assert result is False

    def test_default_prompt_rejects_empty(self, tmp_test_dir: Path) -> None:
        """Verify empty/no response is rejected (default No).

        Real-world significance:
        - User pressing Enter without input should default to No
        - Safety default: don't delete unless explicitly confirmed
        """
        with patch("builtins.input", return_value=""):
            result = output_files.default_prompt(tmp_test_dir)
            assert result is False

    def test_default_prompt_rejects_invalid(self, tmp_test_dir: Path) -> None:
        """Verify invalid responses are rejected.

        Real-world significance:
        - Typos or random input should not trigger deletion
        - Only 'y', 'yes', 'Y', 'YES' should trigger
        """
        with patch("builtins.input", return_value="maybe"):
            result = output_files.default_prompt(tmp_test_dir)
            assert result is False


@pytest.mark.unit
class TestSafeDelete:
    """Unit tests for safe_delete function."""

    def test_safe_delete_removes_file(self, tmp_test_dir: Path) -> None:
        """Verify file is deleted safely.

        Real-world significance:
        - Must delete intermediate .typ files
        - Should not crash if file already missing
        """
        test_file = tmp_test_dir / "test.typ"
        test_file.write_text("content")

        output_files.safe_delete(test_file)

        assert not test_file.exists()

    def test_safe_delete_removes_directory(self, tmp_test_dir: Path) -> None:
        """Verify directory and contents are deleted recursively.

        Real-world significance:
        - Should delete entire artifact directory structures
        - Cleans up nested directories (e.g., artifacts/qr_codes/)
        """
        test_dir = tmp_test_dir / "artifacts"
        test_dir.mkdir()
        (test_dir / "file1.json").write_text("data")
        (test_dir / "subdir").mkdir()
        (test_dir / "subdir" / "file2.json").write_text("data")

        output_files.safe_delete(test_dir)

        assert not test_dir.exists()

    def test_safe_delete_missing_file_doesnt_error(self, tmp_test_dir: Path) -> None:
        """Verify no error when file already missing.

        Real-world significance:
        - Cleanup might run multiple times on same directory
        - Should be idempotent (safe to call multiple times)
        """
        missing_file = tmp_test_dir / "nonexistent.typ"

        # Should not raise
        output_files.safe_delete(missing_file)

        assert not missing_file.exists()

    def test_safe_delete_missing_directory_doesnt_error(
        self, tmp_test_dir: Path
    ) -> None:
        """Verify no error when directory already missing.

        Real-world significance:
        - Directory may have been deleted already
        - Cleanup should be idempotent
        """
        missing_dir = tmp_test_dir / "artifacts"

        # Should not raise
        output_files.safe_delete(missing_dir)

        assert not missing_dir.exists()


@pytest.mark.unit
class TestCleanupWithConfig:
    """Unit tests for cleanup_with_config function."""

    def test_cleanup_removes_artifacts_when_configured(
        self, tmp_output_structure: dict, config_file: Path
    ) -> None:
        """Verify artifacts directory is removed when configured.

        Real-world significance:
        - Config specifies pipeline.after_run.remove_artifacts: true
        - Removes output/artifacts directory to save storage
        - Preserves pdf_individual/ with final PDFs
        """
        output_dir = tmp_output_structure["root"]

        # Create test structure
        (tmp_output_structure["artifacts"] / "typst").mkdir()
        (tmp_output_structure["artifacts"] / "typst" / "notice_00001.typ").write_text(
            "typ"
        )

        # Modify config to enable artifact removal
        with open(config_file) as f:
            config = yaml.safe_load(f)
        config["pipeline"]["after_run"]["remove_artifacts"] = True
        with open(config_file, "w") as f:
            yaml.dump(config, f)

        output_files.cleanup_output(output_dir, yaml.safe_load(config_file.read_text()))

        assert not tmp_output_structure["artifacts"].exists()
        assert tmp_output_structure["pdf_individual"].exists()

    def test_cleanup_preserves_artifacts_by_default(
        self, tmp_output_structure: dict, config_file: Path
    ) -> None:
        """Verify artifacts preserved when remove_artifacts: false.

        Real-world significance:
        - Default config preserves artifacts for debugging
        - Users can inspect intermediate files if pipeline behavior is unexpected
        """
        output_dir = tmp_output_structure["root"]

        (tmp_output_structure["artifacts"] / "test.json").write_text("data")

        # Config already has remove_artifacts: false by default
        output_files.cleanup_output(output_dir, yaml.safe_load(config_file.read_text()))

        assert (tmp_output_structure["artifacts"] / "test.json").exists()

    def test_cleanup_removes_unencrypted_pdfs_when_encryption_enabled(
        self, tmp_output_structure: dict, config_file: Path
    ) -> None:
        """Verify unencrypted PDFs removed only when encryption enabled.

        Real-world significance:
        - When encryption is on and remove_unencrypted_pdfs: true
        - Original (non-encrypted) PDFs are deleted
        - Only _encrypted versions remain for distribution
        """
        output_dir = tmp_output_structure["root"]

        # Create test PDFs
        (
            tmp_output_structure["pdf_individual"] / "en_notice_00001_0000000001.pdf"
        ).write_text("original")
        (
            tmp_output_structure["pdf_individual"]
            / "en_notice_00001_0000000001_encrypted.pdf"
        ).write_text("encrypted")

        # Modify config to enable encryption and unencrypted PDF removal
        with open(config_file) as f:
            config = yaml.safe_load(f)
        config["encryption"]["enabled"] = True
        config["pipeline"]["after_run"]["remove_unencrypted_pdfs"] = True
        with open(config_file, "w") as f:
            yaml.dump(config, f)

        output_files.cleanup_output(output_dir, yaml.safe_load(config_file.read_text()))

        # Non-encrypted removed, encrypted preserved
        assert not (
            tmp_output_structure["pdf_individual"] / "en_notice_00001_0000000001.pdf"
        ).exists()
        assert (
            tmp_output_structure["pdf_individual"]
            / "en_notice_00001_0000000001_encrypted.pdf"
        ).exists()

    def test_cleanup_ignores_unencrypted_removal_when_encryption_disabled(
        self, tmp_output_structure: dict, config_file: Path
    ) -> None:
        """Verify unencrypted PDFs preserved when encryption disabled.

        Real-world significance:
        - If encryption is disabled, remove_unencrypted_pdfs has no effect
        - PDFs are not encrypted, so removing "unencrypted" ones makes no sense
        - Config should have no effect in this scenario
        """
        output_dir = tmp_output_structure["root"]

        # Create test PDF
        (
            tmp_output_structure["pdf_individual"] / "en_notice_00001_0000000001.pdf"
        ).write_text("pdf content")

        # Modify config to have encryption disabled and bundling disabled, but removal requested
        with open(config_file) as f:
            config = yaml.safe_load(f)
        config["encryption"]["enabled"] = False
        config["bundling"]["bundle_size"] = 0
        config["pipeline"]["after_run"]["remove_unencrypted_pdfs"] = True
        with open(config_file, "w") as f:
            yaml.dump(config, f)

        output_files.cleanup_output(output_dir, yaml.safe_load(config_file.read_text()))

        # PDF preserved because both encryption and bundling are disabled
        assert (
            tmp_output_structure["pdf_individual"] / "en_notice_00001_0000000001.pdf"
        ).exists()

    def test_cleanup_removes_unencrypted_pdfs_when_bundling_enabled(
        self, tmp_output_structure: dict, config_file: Path
    ) -> None:
        """Verify unencrypted PDFs removed when bundling is enabled.

        Real-world significance:
        - When bundling groups PDFs and remove_unencrypted_pdfs: true
        - Original individual PDFs are deleted
        - Only batched PDFs remain for distribution
        - This assumes individual PDFs are intermediate artifacts
        """
        output_dir = tmp_output_structure["root"]

        # Create test PDFs
        (
            tmp_output_structure["pdf_individual"] / "en_notice_00001_0000000001.pdf"
        ).write_text("original")
        (
            tmp_output_structure["pdf_individual"] / "en_notice_00002_0000000002.pdf"
        ).write_text("original2")

        # Modify config to enable bundling and unencrypted PDF removal
        with open(config_file) as f:
            config = yaml.safe_load(f)
        config["encryption"]["enabled"] = False
        config["bundling"]["bundle_size"] = 10
        config["pipeline"]["after_run"]["remove_unencrypted_pdfs"] = True
        with open(config_file, "w") as f:
            yaml.dump(config, f)

        output_files.cleanup_output(output_dir, yaml.safe_load(config_file.read_text()))

        # Individual PDFs removed because bundling is enabled
        assert not (
            tmp_output_structure["pdf_individual"] / "en_notice_00001_0000000001.pdf"
        ).exists()
        assert not (
            tmp_output_structure["pdf_individual"] / "en_notice_00002_0000000002.pdf"
        ).exists()

    def test_cleanup_preserves_unencrypted_pdfs_when_both_disabled(
        self, tmp_output_structure: dict, config_file: Path
    ) -> None:
        """Verify individual non-encrypted PDFs preserved when encryption and bundling disabled.

        Real-world significance:
        - When both encryption and bundling are disabled
        - Individual non-encrypted PDFs are assumed to be final output
        - remove_unencrypted_pdfs setting is ignored (has no effect)
        - This is the default use case: generate individual notices
        """
        output_dir = tmp_output_structure["root"]

        # Create test PDF
        (
            tmp_output_structure["pdf_individual"] / "en_notice_00001_0000000001.pdf"
        ).write_text("pdf content")

        # Ensure both encryption and bundling are disabled
        with open(config_file) as f:
            config = yaml.safe_load(f)
        config["encryption"]["enabled"] = False
        config["bundling"]["bundle_size"] = 0
        config["pipeline"]["after_run"]["remove_unencrypted_pdfs"] = True
        with open(config_file, "w") as f:
            yaml.dump(config, f)

        output_files.cleanup_output(output_dir, yaml.safe_load(config_file.read_text()))

        # PDF preserved because both encryption and bundling are disabled
        assert (
            tmp_output_structure["pdf_individual"] / "en_notice_00001_0000000001.pdf"
        ).exists()


@pytest.mark.unit
class TestMain:
    """Unit tests for main cleanup entry point."""

    def test_main_validates_output_directory(self, tmp_test_dir: Path) -> None:
        """Verify error if output_dir is not a directory.

        Real-world significance:
        - Caller should pass a directory, not a file
        - Should validate input before attempting cleanup
        """
        invalid_path = tmp_test_dir / "file.txt"
        invalid_path.write_text("not a directory")

        with pytest.raises(ValueError, match="not a valid directory"):
            output_files.cleanup_output(invalid_path, {})

    def test_main_applies_cleanup_configuration(
        self, tmp_output_structure: dict, config_file: Path
    ) -> None:
        """Verify main entry point applies cleanup configuration.

        Real-world significance:
        - Main is entry point from orchestrator Step 9
        - Should load and apply pipeline.after_run configuration
        """
        output_dir = tmp_output_structure["root"]

        (tmp_output_structure["artifacts"] / "test.json").write_text("data")

        # Modify config to enable artifact removal
        with open(config_file) as f:
            config = yaml.safe_load(f)
        config["pipeline"]["after_run"]["remove_artifacts"] = True
        with open(config_file, "w") as f:
            yaml.dump(config, f)

        output_files.cleanup_output(output_dir, yaml.safe_load(config_file.read_text()))

        assert not tmp_output_structure["artifacts"].exists()

    def test_main_with_none_config_path_uses_default(
        self, tmp_output_structure: dict
    ) -> None:
        """Verify main works with config_path=None (uses default location).

        Real-world significance:
        - orchestrator may not pass config_path
        - Should use default location (config/parameters.yaml)
        """
        output_dir = tmp_output_structure["root"]

        # Should not raise (will use defaults)
        output_files.cleanup_output(output_dir, {})


@pytest.mark.unit
class TestCleanupIntegration:
    """Unit tests for cleanup workflow integration."""

    def test_cleanup_preserves_pdfs_removes_artifacts(
        self, tmp_output_structure: dict, config_file: Path
    ) -> None:
        """Verify complete cleanup workflow: remove artifacts, keep PDFs.

        Real-world significance:
        - Common cleanup scenario:
          - Remove .typ templates and intermediate files in artifacts/
          - Keep .pdf files in pdf_individual/
        - Reduces storage footprint significantly
        """
        output_dir = tmp_output_structure["root"]

        # Create test files
        (tmp_output_structure["artifacts"] / "notice_00001.typ").write_text("template")
        (tmp_output_structure["pdf_individual"] / "notice_00001.pdf").write_text(
            "pdf content"
        )

        # Modify config to enable artifact removal
        with open(config_file) as f:
            config = yaml.safe_load(f)
        config["pipeline"]["after_run"]["remove_artifacts"] = True
        with open(config_file, "w") as f:
            yaml.dump(config, f)

        output_files.cleanup_output(output_dir, yaml.safe_load(config_file.read_text()))

        assert not (tmp_output_structure["artifacts"] / "notice_00001.typ").exists()
        assert (tmp_output_structure["pdf_individual"] / "notice_00001.pdf").exists()

    def test_cleanup_multiple_calls_idempotent(
        self, tmp_output_structure: dict, config_file: Path
    ) -> None:
        """Verify cleanup can be called multiple times safely.

        Real-world significance:
        - If cleanup runs twice, should not error
        - Idempotent operation: no side effects from repeated runs
        """
        output_dir = tmp_output_structure["root"]

        # Modify config to enable artifact removal
        with open(config_file) as f:
            config = yaml.safe_load(f)
        config["pipeline"]["after_run"]["remove_artifacts"] = True
        with open(config_file, "w") as f:
            yaml.dump(config, f)

        # First call
        output_files.cleanup_output(output_dir, yaml.safe_load(config_file.read_text()))

        # Second call should not raise
        output_files.cleanup_output(output_dir, yaml.safe_load(config_file.read_text()))

        assert not tmp_output_structure["artifacts"].exists()
