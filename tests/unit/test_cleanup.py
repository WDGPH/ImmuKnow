"""Unit tests for cleanup module - Intermediate file removal.

Tests cover:
- Safe file and directory deletion
- Selective cleanup (preserve PDFs, remove artifacts)
- Configuration-driven cleanup behavior (pipeline.after_run.*)
- Error handling for permission issues and missing paths
- Conditional PDF removal based on encryption status
- Idempotent cleanup (safe to call multiple times)

Real-world significance:
- Step 9 of pipeline (optional): removes intermediate artifacts after successful run
- Keeps output directory clean and storage minimal
- Must preserve final PDFs while removing working files
- Configuration controlled via pipeline.after_run.remove_artifacts and remove_unencrypted_pdfs
- Removes non-encrypted PDFs only when encryption is enabled and configured
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from immuknow import cleanup


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

        cleanup.safe_delete(test_file)

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

        cleanup.safe_delete(test_dir)

        assert not test_dir.exists()

    def test_safe_delete_missing_file_doesnt_error(self, tmp_test_dir: Path) -> None:
        """Verify no error when file already missing.

        Real-world significance:
        - Cleanup might run multiple times on same directory
        - Should be idempotent (safe to call multiple times)
        """
        missing_file = tmp_test_dir / "nonexistent.typ"

        # Should not raise
        cleanup.safe_delete(missing_file)

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
        cleanup.safe_delete(missing_dir)

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

        cleanup.cleanup_output(output_dir, yaml.safe_load(config_file.read_text()))

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
        cleanup.cleanup_output(output_dir, yaml.safe_load(config_file.read_text()))

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

        cleanup.cleanup_output(output_dir, yaml.safe_load(config_file.read_text()))

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

        # Modify config to have encryption disabled and batching disabled, but removal requested
        with open(config_file) as f:
            config = yaml.safe_load(f)
        config["encryption"]["enabled"] = False
        config["bundling"]["bundle_size"] = 0
        config["pipeline"]["after_run"]["remove_unencrypted_pdfs"] = True
        with open(config_file, "w") as f:
            yaml.dump(config, f)

        cleanup.cleanup_output(output_dir, yaml.safe_load(config_file.read_text()))

        # PDF preserved because both encryption and batching are disabled
        assert (
            tmp_output_structure["pdf_individual"] / "en_notice_00001_0000000001.pdf"
        ).exists()

    def test_cleanup_removes_unencrypted_pdfs_when_batching_enabled(
        self, tmp_output_structure: dict, config_file: Path
    ) -> None:
        """Verify unencrypted PDFs removed when batching is enabled.

        Real-world significance:
        - When batching groups PDFs and remove_unencrypted_pdfs: true
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

        # Modify config to enable batching and unencrypted PDF removal
        with open(config_file) as f:
            config = yaml.safe_load(f)
        config["encryption"]["enabled"] = False
        config["bundling"]["bundle_size"] = 10
        config["pipeline"]["after_run"]["remove_unencrypted_pdfs"] = True
        with open(config_file, "w") as f:
            yaml.dump(config, f)

        cleanup.cleanup_output(output_dir, yaml.safe_load(config_file.read_text()))

        # Individual PDFs removed because batching is enabled
        assert not (
            tmp_output_structure["pdf_individual"] / "en_notice_00001_0000000001.pdf"
        ).exists()
        assert not (
            tmp_output_structure["pdf_individual"] / "en_notice_00002_0000000002.pdf"
        ).exists()

    def test_cleanup_preserves_unencrypted_pdfs_when_both_disabled(
        self, tmp_output_structure: dict, config_file: Path
    ) -> None:
        """Verify individual non-encrypted PDFs preserved when encryption and batching disabled.

        Real-world significance:
        - When both encryption and batching are disabled
        - Individual non-encrypted PDFs are assumed to be final output
        - remove_unencrypted_pdfs setting is ignored (has no effect)
        - This is the default use case: generate individual notices
        """
        output_dir = tmp_output_structure["root"]

        # Create test PDF
        (
            tmp_output_structure["pdf_individual"] / "en_notice_00001_0000000001.pdf"
        ).write_text("pdf content")

        # Ensure both encryption and batching are disabled
        with open(config_file) as f:
            config = yaml.safe_load(f)
        config["encryption"]["enabled"] = False
        config["bundling"]["bundle_size"] = 0
        config["pipeline"]["after_run"]["remove_unencrypted_pdfs"] = True
        with open(config_file, "w") as f:
            yaml.dump(config, f)

        cleanup.cleanup_output(output_dir, yaml.safe_load(config_file.read_text()))

        # PDF preserved because both encryption and batching are disabled
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
            cleanup.cleanup_output(invalid_path, {})

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

        cleanup.cleanup_output(output_dir, yaml.safe_load(config_file.read_text()))

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
        cleanup.cleanup_output(output_dir, {})


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

        cleanup.cleanup_output(output_dir, yaml.safe_load(config_file.read_text()))

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
        cleanup.cleanup_output(output_dir, yaml.safe_load(config_file.read_text()))

        # Second call should not raise
        cleanup.cleanup_output(output_dir, yaml.safe_load(config_file.read_text()))

        assert not tmp_output_structure["artifacts"].exists()
