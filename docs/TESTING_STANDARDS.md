# Testing Standards

This document defines the testing strategy and organizational standards for the immunization-charts-python project.

## Overview

Tests are organized in three layers to provide different types of validation at different speeds.

## Strategic Principles (Pre-1.0 Refinement)

As part of the pre-1.0 release strategy, the following principles guide the test suite:

1. **Contracts over Defensiveness:** Focus on validating the boundaries between steps (inputs/outputs on disk) rather than repetitive internal logic checks in every module.
2. **Minimal E2E Smoke Tests:** Preserve exactly one full pipeline path per language (English and French) to ensure end-to-end viability without overwhelming the suite with redundant E2E variants.
3. **Consolidated Units:** Merge tests for tightly coupled modules (e.g., config loading and validation) to reduce file overhead and improve maintainability.
4. **Deterministic and Isolated:** Tests must not rely on shared global state or external services. All PDF compilation must satisfy project-root path constraints.

## Frameworks and Metrics Used

`pytest` is the framework used to write and run tests for the codebase. As a metric to determine the percentage of source code that is executed during testing, code coverage is used. `pytest-cov` is used to determine whether there are areas in the codebase that are not executed during testing, which may contribute to bugs. Code coverage is integrated in our GitHub actions when a pull request is made to ensure that new additions to the main code base are tested. 

## Test Organization

### Recommended Structure

```
tests/
├── unit/                          # Unit tests (one per module/contract)
│   ├── test_config_loader.py      # Merged loader + validation
│   ├── test_preprocess.py
│   ├── test_generate_notices.py   # Merged template loading
│   ├── test_generate_qr_codes.py
│   ├── test_compile_notices.py
│   ├── test_validate_pdfs.py
│   ├── test_encrypt_notice.py
│   ├── test_bundle_pdfs.py
│   ├── test_cleanup.py
│   ├── test_prepare_output.py
│   ├── test_data_models.py        # Trimmed to custom logic
│   ├── test_utils.py
│   └── test_orchestrator.py       # Merged lang failure paths
│
├── integration/                   # Integration tests (step interactions)
│   ├── test_pipeline_contracts.py # Artifact round-trip and step handoff contracts
│   ├── test_custom_templates.py
│   ├── test_error_propagation.py  # Fail-fast and per-item recovery contracts
│   └── test_translation_integration.py
│
├── e2e/                           # End-to-end tests (full pipeline)
│   └── test_full_pipeline.py      # EN and FR paths (smoke tests)
│
├── conftest.py                    # Pytest fixtures (shared across all layers)
├── fixtures/                      # Shared test utilities
│   └── sample_input.py            # Mock data generators
│
└── tmp_test_dir/                 # Test temporary files
```

## Test Layers

### Unit Tests
**Location:** `tests/unit/test_<module>.py`  
**Speed:** <100ms per test  
**Focus:** Single function/class behavior in isolation  
**Run frequency:** Every save during development  
**Pytest marker:** `@pytest.mark.unit`

Tests verify:
- Single function behavior with realistic inputs
- Error handling and edge cases
- Parameter validation
- Return value structure

**Example:**
```python
@pytest.mark.unit
def test_config_loads_valid_yaml():
    """Verify valid YAML config loads without error.

    Real-world significance:
    - Configuration must be valid before pipeline execution
    - Catches YAML syntax errors early rather than mid-pipeline
    - Ensures all required keys are present

    Assertion: Config dict contains expected keys with valid values
    """
    config = load_config("config/parameters.yaml")
    assert "pipeline" in config
    assert config["pipeline"]["auto_remove_output"] in [True, False]
```

### Integration Tests
**Location:** `tests/integration/test_*.py`  
**Speed:** 100ms–1s per test  
**Focus:** How multiple steps work together; JSON artifact contracts  
**Run frequency:** Before commit  
**Pytest marker:** `@pytest.mark.integration`

Tests verify:
- Output from Step N is valid input to Step N+1
- JSON artifact schema consistency across steps
- Configuration options actually affect pipeline behavior
- Error propagation through multi-step workflows

**Example:**
```python
@pytest.mark.integration
def test_preprocess_output_works_with_qr_generation(tmp_path: Path) -> None:
    """Integration: preprocessed artifact feeds correctly to QR generation.

    Real-world significance:
    - Verifies pipeline contract: Step 1 output is valid for Step 2 input
    - Catches schema mismatches that would fail mid-pipeline
    - Ensures QR codes are generated for all clients in artifact

    Parameters
    ----------
    tmp_path : Path
        Pytest fixture providing temporary directory for artifacts

    Assertion: QR files generated equal the number of clients in artifact
    """
    artifact = preprocess.build_preprocess_result(df, language="en", ...)
    artifact_path = preprocess.write_artifact(tmp_path, artifact, ...)
    
    qr_files = generate_qr_codes.generate_qr_codes(artifact_path, tmp_path, config_path)
    
    assert len(qr_files) == len(artifact['clients'])
```

### End-to-End Tests
**Location:** `tests/e2e/test_*.py`  
**Speed:** 1s–30s per test  
**Focus:** Complete pipeline from Excel input to PDF output  
**Run frequency:** Before release / nightly in CI  
**Pytest marker:** `@pytest.mark.e2e`

Tests verify:
- Full pipeline runs without error for valid input
- Language variants (English, French)
- Optional features (encryption, batching)
- Edge cases (minimal data, missing fields)

## E2E Test Patterns for Immunization Pipeline

This section documents project-specific patterns discovered during Phase 4 E2E testing.

### Path Constraint: Use Project Context, Not tmp_path

**Critical constraint:** E2E tests must run in **project context**, not pytest's `tmp_path`.

**Why:** The Typst PDF compilation step requires absolute paths relative to the project root. The `generate_notices.py` step uses `_to_root_relative()` to create paths like `artifacts/qr_codes/00001.png`, which Typst resolves relative to the project. Running from a tmp directory outside the project tree breaks this resolution.

**Solution:**
```python
import subprocess
from pathlib import Path

@pytest.fixture
def project_root() -> Path:
    """Return the absolute path to project root.

    Used by E2E tests to ensure correct working directory for Typst PDF
    compilation and path resolution.

    Returns
    -------
    Path
        Absolute path to project root (three levels up from tests/e2e/)
    """
    return Path(__file__).parent.parent.parent  # tests/e2e/... → project root

@pytest.mark.e2e
class TestFullPipelineExecution:
    """E2E: Complete pipeline generates PDF output for multiple languages."""

    @pytest.fixture
    def project_root(self) -> Path:
        """Fixture providing absolute path to project root."""
        return Path(__file__).resolve().parent.parent.parent

    @pytest.fixture
    def e2e_workdir(self, project_root: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
        """Create a temporary workdir within project root for path resolution."""
        workdir = project_root / f"tmp_e2e_{tmp_path_factory.mktemp('e2e').name}"
        workdir.mkdir(parents=True, exist_ok=True)
        # Prepare subdirs...
        return workdir

    def test_full_pipeline_english(self, project_root: Path, e2e_workdir: Path) -> None:
        """Verifies full 9-step pipeline works end-to-end for English."""
        # Run pipeline using 'uv run viper' in project_root...
        pass
```

### Feature Toggle Testing (Config Overrides)

While E2E tests are reserved for full smoke paths, feature toggles (e.g., QR enabled/disabled) should primarily be tested at the **Integration** level. This avoids the overhead of full PDF compilation for every configuration variant.

**Preferred Pattern:**
In `tests/integration/test_pipeline_contracts.py`, use a modular approach to verify that configuration flags correctly skip or include specific step logic.

```python
@pytest.mark.integration
def test_pipeline_skips_qr_when_disabled(tmp_path: Path):
    """Integration: verify that 'qr.enabled=False' skips Step 3.

    Real-world significance:
    - Feature flags must be deterministic and respected
    - Avoids unnecessary processing time when features aren't needed
    """
    # Logic to verify step bypass or artifact omission
```

### Input/Output Fixture Pattern

**Pattern:** Create test input files in `project_root / "input"`, output in `project_root / "output"`, use `yield` for cleanup.

**Why:** Keeps all test artifacts within project tree (path constraints), enables cleanup without relying on tmp_path garbage collection.

**Solution:**
```python
from pathlib import Path
import pandas as pd

@pytest.fixture
def pipeline_input_file(project_root: Path) -> Path:
    """Create a test Excel file in project input directory.

    Provides temporary test input file for E2E tests. File is created in
    project root's input/ directory (not tmp_path) to comply with path
    constraints for Typst PDF compilation.

    Parameters
    ----------
    project_root : Path
        Fixture providing absolute path to project root

    Yields
    ------
    Path
        Absolute path to created test Excel file

    Notes
    -----
    File is cleaned up after test via yield. Uses project root instead of
    tmp_path to enable Typst path resolution for PDF compilation.
    """
    input_file = project_root / "input" / "e2e_test_clients.xlsx"
    
    # Create test DataFrame and write to Excel
    df = create_test_input_dataframe(num_clients=3)
    df.to_excel(input_file, index=False, engine="openpyxl")
    
    yield input_file
    
    # Cleanup
    if input_file.exists():
        input_file.unlink()
```

## Running Tests with pytest

### Quick Reference

```bash
# All tests
uv run pytest

# Only unit tests (fast feedback)
uv run pytest -m unit

# Only integration tests
uv run pytest -m integration

# Only E2E tests
uv run pytest -m e2e

# Everything except slow E2E tests
uv run pytest -m "not e2e"

# With coverage report
uv run pytest --cov=scripts --cov-report=html

# Specific file
uv run pytest tests/unit/test_preprocess.py -v

# Specific test
uv run pytest tests/unit/test_preprocess.py::test_sorts_clients -v

# Stop on first failure
uv run pytest -x

# Show print statements
uv run pytest -s
```

### Pytest Markers Configuration

**In `pytest.ini`:**
```ini
[pytest]
pythonpath = scripts

markers =
    unit: Unit tests for individual modules (fast)
    integration: Integration tests for step interactions (medium)
    e2e: End-to-end pipeline tests (slow)
```

## Testing Patterns

**Example:**
```python
@pytest.mark.integration
def test_preprocessed_artifact_schema(tmp_path: Path) -> None:
    """Verify preprocess output matches expected schema.

    Real-world significance:
    - Downstream steps (QR generation, notice compilation) depend on
      consistent artifact structure
    - Schema mismatches cause silent failures later in pipeline
    - Ensures data normalization is deterministic across runs

    Parameters
    ----------
    tmp_path : Path
        Pytest fixture providing temporary directory

    Raises
    ------
    AssertionError
        If artifact missing required keys or clients lack expected fields

    Assertion: Artifact contains all required keys and client records complete
    """
    artifact = preprocess.build_preprocess_result(df, language="en", ...)
    
    assert "run_id" in artifact
    assert "clients" in artifact
    assert isinstance(artifact["clients"], list)
    for client in artifact["clients"]:
        assert "client_id" in client
        assert "sequence" in client
```

### 2. Configuration-Driven Testing

Test that configuration options actually control behavior by modifying config files and verifying the effect:

**For unit/integration tests** (using mocked config):
```python
@pytest.mark.unit
def test_qr_generation_skips_if_disabled() -> None:
    """When config['qr']['enabled'] is False, QR generation is skipped.

    Real-world significance:
    - Users can disable QR codes for certain notice types (e.g., old PDFs)
    - Configuration must actually affect pipeline behavior
    - Skipping should not crash pipeline or leave partial output

    Parameters
    ----------
    None - Uses mocked config parameter

    Raises
    ------
    AssertionError
        If QR files are generated when disabled

    Assertion: QR file list is empty when qr.enabled is False
    """
    config = {"qr": {"enabled": False}}
    
    qr_files = generate_qr_codes.generate_qr_codes(
        artifact_path, output_dir, config
    )
    
    assert len(qr_files) == 0
```

**For E2E tests** (using real config file modifications):
```python
import yaml
from pathlib import Path

@pytest.mark.e2e
def test_pipeline_with_qr_disabled_e2e(project_root: Path) -> None:
    """E2E: Verify QR feature flag actually controls pipeline behavior.

    Real-world significance:
    - Catches YAML parsing bugs and config file format issues
    - Tests that disabling QR doesn't crash downstream steps
    - Ensures config changes propagate correctly through pipeline

    Parameters
    ----------
    project_root : Path
        Fixture providing absolute path to project root

    Raises
    ------
    AssertionError
        If QR step runs when disabled or pipeline returns non-zero exit code

    Notes
    -----
    Modifies real config.yaml but restores it in finally block to prevent
    test pollution. Use this for real config parsing; use unit tests for
    logic verification.
    """
    config_path = project_root / "config" / "parameters.yaml"
    
    with open(config_path) as f:
        original_config = yaml.safe_load(f)
    
    try:
        # Disable QR in actual config file
        original_config["qr"]["enabled"] = False
        with open(config_path, "w") as f:
            yaml.dump(original_config, f)
        
        # Run full pipeline
        result = subprocess.run(
            ["uv", "run", "viper", "test_input.xlsx", "en"],
            cwd=str(project_root),
            capture_output=True,
            text=True
        )
        
        # Verify QR generation was truly skipped
        assert result.returncode == 0
        assert "Step 3: Generating QR codes" not in result.stdout
    
    finally:
        # Always restore original config
        original_config["qr"]["enabled"] = True
        with open(config_path, "w") as f:
            yaml.dump(original_config, f)
```

This approach tests real config parsing logic, catching YAML-specific bugs that mocked tests would miss.

### 3. Temporary Directory Testing

Use pytest's `tmp_path` fixture for all file I/O:

```python
@pytest.mark.unit
def test_cleanup_removes_intermediate_files(tmp_path: Path) -> None:
    """Cleanup removes .typ files but preserves PDFs.

    Real-world significance:
    - Temp files (.typ) take disk space and should be cleaned after PDF generation
    - PDFs must be preserved for delivery to users
    - Cleanup must be deterministic and safe

    Parameters
    ----------
    tmp_path : Path
        Pytest fixture providing temporary directory

    Raises
    ------
    AssertionError
        If .typ file not removed or PDFs accidentally deleted

    Assertion: Only .typ files removed; PDF files remain intact
    """
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    
    typ_file = artifacts / "test.typ"
    typ_file.write_text("test")
    
    cleanup.main(tmp_path, config)
    
    assert not typ_file.exists()
```

### 4. Subprocess Mocking

Mock external commands (e.g., typst CLI):

```python
from unittest.mock import patch, MagicMock

@pytest.mark.unit
@patch("subprocess.run")
def test_compile_notices_calls_typst(mock_run: MagicMock, tmp_path: Path) -> None:
    """Verify compile step invokes typst command.

    Real-world significance:
    - Typst compilation is external and slow; mocking enables fast testing
    - Ensures CLI arguments are constructed correctly
    - Tests error handling without actual compilation

    Parameters
    ----------
    mock_run : MagicMock
        Mocked subprocess.run function
    tmp_path : Path
        Pytest fixture providing temporary directory

    Raises
    ------
    AssertionError
        If typst command not called or arguments incorrect

    Assertion: subprocess.run called with correct typst command
    """
    mock_run.return_value = MagicMock(returncode=0)
    
    compile_notices.compile_with_config(artifacts_dir, pdf_dir, config)
    
    mock_run.assert_called()
    call_args = mock_run.call_args
    assert "typst" in call_args[0][0]
```

### 5. Language Testing

Both English and French are first-class concerns:

```python
@pytest.mark.parametrize("language", ["en", "fr"])
@pytest.mark.unit
def test_preprocess_handles_language(language: str, tmp_path: Path) -> None:
    """Verify preprocessing works for both languages.

    Real-world significance:
    - Notices are generated in both English and French
    - Language affects vaccine name mapping, address formatting, etc.
    - Both variants must be deterministic and testable

    Parameters
    ----------
    language : str
        Language code: "en" or "fr"
    tmp_path : Path
        Pytest fixture providing temporary directory

    Raises
    ------
    AssertionError
        If language not set correctly in result

    Assertion: Result clients have correct language assigned
    """
    result = preprocess.build_preprocess_result(
        df, language=language, ...
    )
    assert result.clients[0].language == language
```

## Test Docstrings

Every test function must include a docstring explaining:

1. **What scenario is being tested** – Be specific and concrete
2. **Why it matters to users** – Real-world significance (how does it affect the notices?)
3. **What's being verified** – The specific assertion or behavior

**Example:**
```python
def test_preprocess_sorts_clients_deterministically():
    """Verify clients sort consistently for reproducible pipeline output.

    Real-world significance:
    - Same input always produces same sequence (00001, 00002, ...)
    - Enables comparison between pipeline runs
    - Required for school-based batching to work correctly
    
    Assertion: Clients are ordered by school → last_name → first_name → client_id
    """
```

## Test Coverage Goals

- **pipeline/**: >80% code coverage
- **Pipeline orchestration**: >60% coverage (verified via combination of unit and integration tests)
- **Critical path (Steps 1–6)**: >90% coverage
- **Optional features (Steps 7–9)**: >70% coverage

Run coverage reports with:
```bash
uv run pytest --cov=pipeline --cov-report=html
```

View results in `htmlcov/index.html`.