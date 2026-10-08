"""Build distributions and run an installed wheel without a writable source tree."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

from tests.integration.test_native_pipeline import ROOT, prepare_cohort

pytestmark = pytest.mark.integration


def run_checked(command: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Keep build and installed-process diagnostics available when a check fails."""
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def test_installed_wheel_uses_packaged_and_external_resources(tmp_path: Path) -> None:
    """The wheel supports library and CLI use outside the repo with read-only resources."""
    distributions = tmp_path / "distributions"
    run_checked(["uv", "build", "--out-dir", str(distributions)], ROOT)
    wheel = next(distributions.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        assert "templates/overdue_standard_v1/fr.typ" in names
        assert "templates/affirmative_schedule_v1/en.typ" in names
        assert "templates/assets/logo.png" in names
        assert "templates/assets/signature.png" in names
        assert "config/input_schema.json" in names
        assert "config/translations/fr_diseases_chart.json" in names
        assert not any(name.endswith("_template.py") for name in names)
    with tarfile.open(next(distributions.glob("*.tar.gz"))) as archive:
        source_names = archive.getnames()
        assert any(
            name.endswith("templates/overdue_standard_v1/fr.typ")
            for name in source_names
        )
        assert any(
            name.endswith("config/vaccine_reference.json") for name in source_names
        )

    environment = tmp_path / "Clean environment"
    run_checked(["uv", "venv", "--python", sys.executable, str(environment)], tmp_path)
    python = environment / "bin" / "python"
    requirements = tmp_path / "requirements.txt"
    run_checked(
        [
            "uv",
            "export",
            "--frozen",
            "--no-dev",
            "--no-emit-project",
            "--no-hashes",
            "--format",
            "requirements-txt",
            "--output-file",
            str(requirements),
        ],
        ROOT,
    )
    run_checked(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            "--no-deps",
            "--requirement",
            str(requirements),
            str(wheel),
        ],
        tmp_path,
    )
    unrelated = tmp_path / "Unrelated working directory"
    unrelated.mkdir()
    inspect = run_checked(
        [
            str(python),
            "-c",
            "import json; from importlib.resources import files; "
            "print(json.dumps([str(files(p)) for p in ('pipeline', 'templates', 'config')]))",
        ],
        unrelated,
    )
    installed_dirs = [Path(path) for path in json.loads(inspect.stdout)]
    assert all(path.is_relative_to(environment) for path in installed_dirs)
    resources = [
        path
        for directory in installed_dirs
        for path in [directory, *directory.rglob("*")]
    ]
    original_modes = {path: path.stat().st_mode & 0o777 for path in resources}
    try:
        for path in resources:
            path.chmod(0o555 if path.is_dir() else 0o444)
        command, output_dir, config_dir = prepare_cohort(tmp_path / "Manifest run")
        command[0] = str(python)
        result = run_checked(command, unrelated)
        assert "Pipeline completed successfully" in result.stdout
        assert len(list((output_dir / "pdf_individual").glob("*.pdf"))) == 2

        # Exercise the same ordinary library function as the CLI.
        run_checked(
            [
                str(python),
                "-c",
                "from pathlib import Path; from pipeline.generate_notices import read_render_jobs; "
                f"assert len(read_render_jobs(Path({str(output_dir / 'artifacts')!r}), require_compiled=True)) == 2",
            ],
            unrelated,
        )

        custom = tmp_path / "Private PHU modèles"
        shutil.copytree(installed_dirs[1], custom)
        for directory in [custom, *custom.rglob("*")]:
            if directory.is_dir():
                directory.chmod(0o755)
        input_file = Path(command[3])
        fixed_output = tmp_path / "Fixed packaged configuration"
        run_checked(
            [
                str(environment / "bin" / "viper"),
                str(input_file),
                "fr",
                "--output",
                str(fixed_output),
                "--templates",
                str(custom),
            ],
            unrelated,
        )
        assert len(list((fixed_output / "pdf_individual").glob("*.pdf"))) == 2
        assert not (unrelated / "output").exists()
    finally:
        for path, mode in original_modes.items():
            path.chmod(mode)
