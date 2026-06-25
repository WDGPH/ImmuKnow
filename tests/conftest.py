"""Shared pytest fixtures for unit, integration, and e2e tests.

This module provides:
- Temporary directory fixtures for file I/O testing
- Mock data generators (DataFrames, JSON artifacts)
- Configuration fixtures for parameter testing
- Cleanup utilities for test isolation
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, Generator

import pytest
import yaml

from pipeline import data_models


@pytest.fixture
def tmp_test_dir() -> Generator[Path, None, None]:
    """Provide a temporary directory that's cleaned up after each test.

    Real-world significance:
    - Isolates file I/O tests from each other
    - Prevents test artifacts from polluting the file system
    - Required for testing file cleanup and artifact management

    Yields
    ------
    Path
        Absolute path to temporary directory (automatically deleted after test)
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def tmp_output_structure(tmp_test_dir: Path) -> Dict[str, Path]:
    """Create standard output directory structure expected by pipeline.

    Real-world significance:
    - Tests can assume artifacts/, pdf_individual/, metadata/ directories exist
    - Matches production output structure for realistic testing
    - Enables testing of file organization and cleanup steps

    Parameters
    ----------
    tmp_test_dir : Path
        Root temporary directory from fixture

    Returns
    -------
    Dict[str, Path]
        Keys: 'root', 'artifacts', 'pdf_individual', 'metadata', 'logs'
        Values: Paths to created directories
    """
    (tmp_test_dir / "artifacts").mkdir(exist_ok=True)
    (tmp_test_dir / "pdf_individual").mkdir(exist_ok=True)
    (tmp_test_dir / "metadata").mkdir(exist_ok=True)
    (tmp_test_dir / "logs").mkdir(exist_ok=True)

    return {
        "root": tmp_test_dir,
        "artifacts": tmp_test_dir / "artifacts",
        "pdf_individual": tmp_test_dir / "pdf_individual",
        "metadata": tmp_test_dir / "metadata",
        "logs": tmp_test_dir / "logs",
    }


@pytest.fixture
def default_vaccine_reference() -> Dict[str, list]:
    """Provide a minimal vaccine reference for testing.

    Real-world significance:
    - Maps vaccine codes to component diseases
    - Used by preprocess to expand vaccine records into diseases
    - Affects disease coverage text in notices

    Returns
    -------
    Dict[str, list]
        Maps vaccine codes to disease components, e.g. {"DTaP": ["Diphtheria", "Tetanus", "Pertussis"]}
    """
    return {
        "DTaP": ["Diphtheria", "Tetanus", "Pertussis"],
        "IPV": ["Polio"],
        "MMR": ["Measles", "Mumps", "Rubella"],
        "Varicella": ["Chickenpox"],
        "MenC": ["Meningococcal"],
        "PCV": ["Pneumococcal"],
        "Hib": ["Haemophilus influenzae"],
        "HBV": ["Hepatitis B"],
        "HPV": ["Human Papillomavirus"],
    }


@pytest.fixture
def default_config(tmp_output_structure: Dict[str, Path]) -> Dict[str, Any]:
    """Provide a minimal pipeline configuration for testing.

    Real-world significance:
    - Tests can assume this config structure is valid
    - Enables testing of feature flags (qr.enabled, encryption.enabled, etc.)
    - Matches production config schema

    Parameters
    ----------
    tmp_output_structure : Dict[str, Path]
        Output directories from fixture (used for config paths)

    Returns
    -------
    Dict[str, Any]
        Configuration dict with all standard sections
    """
    return {
        "pipeline": {
            "before_run": {
                "clear_output_directory": False,
            },
            "after_run": {
                "remove_artifacts": False,
                "remove_unencrypted_pdfs": False,
            },
        },
        "qr": {
            "enabled": True,
            "payload_template": "https://example.com/vac/{client_id}",
        },
        "encryption": {
            "enabled": False,
            "password": {
                "template": "Password123",
            },
        },
        "bundling": {
            "bundle_size": 100,
            "group_by": None,
        },
        "chart_diseases_header": [
            "Diphtheria",
            "Tetanus",
            "Pertussis",
            "Polio",
            "Measles",
            "Mumps",
            "Rubella",
        ],
        "replace_unspecified": [],
        "typst": {
            "bin": "typst",
        },
        "pdf_validation": {
            "rules": {
                "client_id_presence": "error",
            },
        },
    }


@pytest.fixture
def config_file(tmp_test_dir: Path, default_config: Dict[str, Any]) -> Path:
    """Create a temporary config file with default configuration.

    Real-world significance:
    - Tests that need to load config from disk can use this fixture
    - Enables testing of config loading and validation
    - Provides realistic config for integration tests

    Parameters
    ----------
    tmp_test_dir : Path
        Root temporary directory
    default_config : Dict[str, Any]
        Default configuration dict

    Returns
    -------
    Path
        Path to created YAML config file
    """
    config_path = tmp_test_dir / "parameters.yaml"
    with open(config_path, "w") as f:
        yaml.dump(default_config, f)
    return config_path


@pytest.fixture
def run_id() -> str:
    """Provide a consistent run ID for testing artifact generation.

    Real-world significance:
    - Artifacts are stored with run_id to enable comparing multiple pipeline runs
    - Enables tracking of which batch processed which clients
    - Required for reproducibility testing

    Returns
    -------
    str
        Example run ID in format used by production code
    """
    return "test_run_20250101_120000"


# Markers fixture for organizing test execution
@pytest.fixture(params=["unit", "integration", "e2e"])
def test_layer(request: pytest.FixtureRequest) -> str:
    """Fixture to identify which test layer is running (informational only).

    Real-world significance:
    - Documents which test layer is executing (for reporting/analysis)
    - Can be used by conftest hooks to apply layer-specific setup

    Yields
    ------
    str
        Layer name: "unit", "integration", or "e2e"
    """
    return request.param


@pytest.fixture
def custom_templates(tmp_test_dir: Path) -> Generator[Path, None, None]:
    """Create a temporary custom template directory with copied templates.

    This fixture dynamically creates a custom template directory by copying
    the default templates from the project, enabling testing of the template
    directory feature without committing test fixtures to git.

    **Setup:**
    - Creates temporary directory
    - Copies templates/{en_template.py, fr_template.py, conf.typ}
    - Copies templates/assets/ directory
    - Provides path to test

    **Teardown:**
    - All files automatically cleaned up when test ends (tmp_test_dir cleanup)

    Real-world significance:
    - Tests can verify custom template loading without modifying project files
    - Custom template directory can be anywhere (not just tests/fixtures/)
    - Simulates PHU teams creating their own template directories
    - No committed test files means cleaner git history

    Yields
    ------
    Path
        Path to temporary custom template directory with all required files

    Raises
    ------
    FileNotFoundError
        If source templates directory doesn't exist (should never happen in CI)

    Examples
    --------
    >>> def test_custom_template(custom_templates):
    ...     renderers = build_language_renderers(custom_templates)
    ...     assert "en" in renderers
    """
    import shutil

    # Create custom template directory in tmp_test_dir
    custom_dir = tmp_test_dir / "custom_templates"
    custom_dir.mkdir(parents=True, exist_ok=True)

    # Get path to source templates in project
    src_templates = Path(__file__).parent.parent / "templates"

    if not src_templates.exists():
        raise FileNotFoundError(
            f"Source templates directory not found: {src_templates}. "
            "Cannot create custom template fixture."
        )

    # Copy template modules
    for template_file in ["en_template.py", "fr_template.py", "conf.typ"]:
        src = src_templates / template_file
        if not src.exists():
            raise FileNotFoundError(f"Template file not found: {src}")
        dest = custom_dir / template_file
        shutil.copy2(src, dest)

    # Copy assets directory
    src_assets = src_templates / "assets"
    if src_assets.exists():
        dest_assets = custom_dir / "assets"
        if dest_assets.exists():
            shutil.rmtree(dest_assets)
        shutil.copytree(src_assets, dest_assets)

    yield custom_dir
    # Cleanup handled automatically by tmp_test_dir fixture


@pytest.fixture
def sample_client_record() -> data_models.ClientRecord:
    """Provide a standard ClientRecord for testing.

    Real-world significance:
    - Provides a consistent starting point for downstream tests
    - Reduces duplication of manual record creation
    """
    from tests.fixtures.sample_input import create_test_client_record

    return create_test_client_record()


@pytest.fixture
def sample_artifact_payload(run_id: str) -> data_models.ArtifactPayload:
    """Provide a standard ArtifactPayload for testing.

    Real-world significance:
    - Reduces duplication of manual artifact creation
    - Ensures consistency across integration tests
    """
    from tests.fixtures.sample_input import create_test_artifact_payload

    return create_test_artifact_payload(run_id=run_id)


@pytest.fixture
def sample_assets(tmp_path: Path) -> tuple[Path, Path]:
    """Provide paths to real logo and signature assets.

    Real-world significance:
    - Tests requiring real image files can use these
    - Fails gracefully if assets are missing
    """
    project_root = Path(__file__).parent.parent
    assets_dir = project_root / "templates" / "assets"
    logo = assets_dir / "logo.png"
    signature = assets_dir / "signature.png"

    if not logo.exists() or not signature.exists():
        pytest.skip("Logo or signature assets not found")

    return logo, signature
