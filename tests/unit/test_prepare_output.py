"""Unit tests for prepare_output module - Output directory finalization.

Tests cover:
- Output directory creation and initialization
- Directory structure creation (pdf_individual, pdf_combined, metadata, artifacts, logs)
- Existing directory handling and cleanup
- Log directory preservation during cleanup
- Configuration-driven behavior (auto_remove flag)
- User prompting for directory removal confirmation
- Error handling for permission issues

Real-world significance:
- Step 1 of pipeline: prepares output directory for new pipeline run
- Must preserve existing logs while cleaning working artifacts
- Directory structure must be consistent for subsequent steps
- User confirmation prevents accidental data loss
- Determines whether to wipe previous output before generating notices
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from immuknow import prepare_output


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

        prepare_output.purge_output_directory(output_dir, log_dir)

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

        prepare_output.purge_output_directory(output_dir, log_dir)

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

        prepare_output.purge_output_directory(output_dir, log_dir)

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

        result = prepare_output.prepare_output_directory(
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

        result = prepare_output.prepare_output_directory(
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

        result = prepare_output.prepare_output_directory(
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

        result = prepare_output.prepare_output_directory(
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
            result = prepare_output.default_prompt(tmp_test_dir)
            assert result is True

    def test_default_prompt_accepts_yes(self, tmp_test_dir: Path) -> None:
        """Verify 'yes' response is accepted.

        Real-world significance:
        - User should be able to confirm with full word 'yes'
        - Common user response pattern
        """
        with patch("builtins.input", return_value="yes"):
            result = prepare_output.default_prompt(tmp_test_dir)
            assert result is True

    def test_default_prompt_rejects_n(self, tmp_test_dir: Path) -> None:
        """Verify 'n' response is rejected (returns False).

        Real-world significance:
        - User should be able to cancel with 'n'
        - Default is No if user is uncertain
        """
        with patch("builtins.input", return_value="n"):
            result = prepare_output.default_prompt(tmp_test_dir)
            assert result is False

    def test_default_prompt_rejects_empty(self, tmp_test_dir: Path) -> None:
        """Verify empty/no response is rejected (default No).

        Real-world significance:
        - User pressing Enter without input should default to No
        - Safety default: don't delete unless explicitly confirmed
        """
        with patch("builtins.input", return_value=""):
            result = prepare_output.default_prompt(tmp_test_dir)
            assert result is False

    def test_default_prompt_rejects_invalid(self, tmp_test_dir: Path) -> None:
        """Verify invalid responses are rejected.

        Real-world significance:
        - Typos or random input should not trigger deletion
        - Only 'y', 'yes', 'Y', 'YES' should trigger
        """
        with patch("builtins.input", return_value="maybe"):
            result = prepare_output.default_prompt(tmp_test_dir)
            assert result is False
