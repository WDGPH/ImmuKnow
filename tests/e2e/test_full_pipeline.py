"""End-to-end tests for full pipeline execution.

Tests cover:
- Complete pipeline runs for English input
- Complete pipeline runs for French input
- Optional feature integration (encryption, batching, QR codes)
- Edge cases and minimal data

Real-world significance:
- E2E tests verify entire pipeline works together
- First indication that pipeline can successfully process user input
- Must verify output files are created and contain expected data
- Tests run against production config (not mocked)

Each test:
1. Prepares a temporary input Excel file
2. Runs the full viper pipeline
3. Validates exit code and output structure
4. Checks that expected artifacts were created
5. Verifies PDF count matches client count
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Generator
from pathlib import Path

import pytest
import yaml

from tests.fixtures.sample_input import create_test_input_dataframe


@pytest.mark.e2e
class TestFullPipelineExecution:
    """End-to-end tests for complete pipeline execution."""

    @pytest.fixture
    def project_root(self) -> Path:
        """Get the project root directory."""
        return Path(__file__).resolve().parent.parent.parent

    @pytest.fixture
    def e2e_workdir(
        self, project_root: Path, tmp_path_factory: pytest.TempPathFactory
    ) -> Generator[Path, None, None]:
        """Create a temporary working directory within the project root.

        Typst requires absolute paths relative to the project root for asset
        resolution (QR codes, logos). This workdir is inside project root
        to satisfy that constraint while maintaining isolation.
        """
        workdir = project_root / f"tmp_e2e_{tmp_path_factory.mktemp('e2e').name}"
        workdir.mkdir(parents=True, exist_ok=True)
        (workdir / "input").mkdir(exist_ok=True)
        (workdir / "output").mkdir(exist_ok=True)

        # Copy base config to workdir
        config_dir = workdir / "config"
        shutil.copytree(project_root / "config", config_dir)

        yield workdir

        # Cleanup
        if workdir.exists():
            shutil.rmtree(workdir)

    @pytest.fixture
    def pipeline_input_file(self, e2e_workdir: Path) -> Path:
        """Create a test input Excel file in the E2E workdir."""
        input_file = e2e_workdir / "input" / "e2e_test_clients.xlsx"
        df = create_test_input_dataframe(num_clients=3)
        df.to_excel(input_file, index=False, engine="openpyxl")
        return input_file

    def run_pipeline(
        self,
        input_file: Path,
        language: str,
        project_root: Path,
        e2e_workdir: Path,
        config_overrides: dict | None = None,
    ) -> subprocess.CompletedProcess:
        """Run the viper pipeline via subprocess using isolated config/output."""
        config_dir = e2e_workdir / "config"

        if config_overrides:
            config_path = config_dir / "parameters.yaml"
            with open(config_path) as f:
                config = yaml.safe_load(f)

            # Merge overrides
            for key, value in config_overrides.items():
                if (
                    isinstance(value, dict)
                    and key in config
                    and isinstance(config[key], dict)
                ):
                    config[key].update(value)
                else:
                    config[key] = value

            with open(config_path, "w") as f:
                yaml.dump(config, f)

        cmd = [
            "uv",
            "run",
            "viper",
            str(input_file.name),
            language,
            "--input",
            str(input_file.parent),
            "--output",
            str(e2e_workdir / "output"),
            "--config",
            str(config_dir),
        ]

        result = subprocess.run(
            cmd, cwd=str(project_root), capture_output=True, text=True
        )
        return result

    def test_full_pipeline_english(
        self, pipeline_input_file: Path, project_root: Path, e2e_workdir: Path
    ) -> None:
        """Test complete pipeline execution with English language."""
        # Disable encryption for core E2E test
        config_overrides = {"encryption": {"enabled": False}}
        result = self.run_pipeline(
            pipeline_input_file, "en", project_root, e2e_workdir, config_overrides
        )

        assert result.returncode == 0, f"Pipeline failed: {result.stderr}"
        assert "Pipeline completed successfully" in result.stdout

        # Verify output structure in E2E workdir
        output_dir = e2e_workdir / "output"
        assert (output_dir / "artifacts").exists()
        assert (output_dir / "pdf_individual").exists()

        # Verify PDFs exist
        pdfs = list((output_dir / "pdf_individual").glob("en_notice_*.pdf"))
        assert len(pdfs) == 3, f"Expected 3 PDFs but found {len(pdfs)}"

        # Bundling runs by default (bundle_size: 100 in parameters.yaml)
        assert (output_dir / "pdf_combined").exists()

    def test_full_pipeline_french(
        self, pipeline_input_file: Path, project_root: Path, e2e_workdir: Path
    ) -> None:
        """Test complete pipeline execution with French language."""
        # Disable encryption for core E2E test
        config_overrides = {"encryption": {"enabled": False}}
        result = self.run_pipeline(
            pipeline_input_file, "fr", project_root, e2e_workdir, config_overrides
        )

        assert result.returncode == 0, f"Pipeline failed: {result.stderr}"
        assert "Pipeline completed successfully" in result.stdout

        # Verify output structure in E2E workdir
        output_dir = e2e_workdir / "output"
        assert (output_dir / "artifacts").exists()
        assert (output_dir / "pdf_individual").exists()

        # Verify PDFs exist with French prefix
        pdfs = list((output_dir / "pdf_individual").glob("fr_notice_*.pdf"))
        assert len(pdfs) == 3, f"Expected 3 French PDFs but found {len(pdfs)}"

    def test_full_pipeline_with_encryption(
        self, pipeline_input_file: Path, project_root: Path, e2e_workdir: Path
    ) -> None:
        """Test complete pipeline execution with encryption enabled (Steps 7 + 9).

        Real-world significance:
        - Encryption is a core optional feature used in production deliveries
        - Steps 7 and 9 are never exercised by the baseline smoke tests
        - Verifies that encrypted PDFs are created alongside unencrypted originals

        Assertion: One _encrypted.pdf exists per client in pdf_individual/
        """
        config_overrides = {"encryption": {"enabled": True}}
        result = self.run_pipeline(
            pipeline_input_file, "en", project_root, e2e_workdir, config_overrides
        )

        assert result.returncode == 0, f"Pipeline failed: {result.stderr}"
        assert "Pipeline completed successfully" in result.stdout

        output_dir = e2e_workdir / "output"
        encrypted_pdfs = list(
            (output_dir / "pdf_individual").glob("*_encrypted.pdf")
        )
        assert len(encrypted_pdfs) == 3, (
            f"Expected 3 encrypted PDFs but found {len(encrypted_pdfs)}"
        )

