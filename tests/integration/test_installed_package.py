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
    result = subprocess.run(
        command, cwd=cwd, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def test_installed_wheel_uses_packaged_and_external_resources(tmp_path: Path) -> None:
    """The wheel supports library and CLI use outside the repo with read-only resources."""
    distributions = tmp_path / "distributions"
    run_checked(["uv", "build", "--out-dir", str(distributions)], ROOT)
    wheel = next(distributions.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        assert "immuknow/templates/overdue_agents_v1.fr.typ" in names
        assert "immuknow/templates/affirmative_schedule_v1.en.typ" in names
        assert "immuknow/templates/assets/logo.png" in names
        assert "immuknow/templates/assets/signature.png" in names
        assert "immuknow/schemas/input_schema.json" in names
        assert "immuknow/schemas/rendering-v1.json" in names
        for resource in ("typst.toml", "lib.typ", "src/validation.typ", "LICENSE"):
            assert f"immuknow/templates/lib/immuknow/{resource}" in names
        assert "immuknow/config/input_schema.json" not in names
        assert "immuknow/config/translations/fr_diseases_chart.json" in names
        assert "immuknow/templates/presentation.typ" in names
        for language in ("en", "fr"):
            for domain in ("diseases_chart", "diseases_overdue"):
                assert f"immuknow/config/translations/{language}_{domain}.json" in names
        assert not any(
            name.startswith(("pipeline/", "templates/", "config/")) for name in names
        )
        assert not any(name.endswith("_template.py") for name in names)
    with tarfile.open(next(distributions.glob("*.tar.gz"))) as archive:
        source_names = archive.getnames()
        for resource in ("typst.toml", "lib.typ", "src/validation.typ", "LICENSE"):
            assert any(
                name.endswith(f"immuknow/templates/lib/immuknow/{resource}")
                for name in source_names
            )
        assert any(
            name.endswith("immuknow/templates/overdue_agents_v1.fr.typ")
            for name in source_names
        )
        assert any(
            name.endswith("immuknow/config/vaccine_reference.json")
            for name in source_names
        )

        assert any(
            name.endswith("immuknow/schemas/input_schema.json") for name in source_names
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
    (unrelated / "config.py").write_text(
        'raise RuntimeError("APPLICATION CONFIG IMPORTED")'
    )
    (unrelated / "templates").mkdir()
    (unrelated / "templates" / "__init__.py").write_text(
        'raise RuntimeError("APPLICATION TEMPLATES IMPORTED")'
    )
    inspect = run_checked(
        [
            str(python),
            "-c",
            (
                "import json; from importlib.resources import files; "
                "print(json.dumps([str(files(p)) for p in ('immuknow',)]))"
            ),
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
        # A configuration-local schema cannot replace the installed contract.
        (config_dir / "input_schema.json").write_text("not a schema")
        input_file = Path(command[3])
        manifest = Path(command[command.index("--notice-assignments") + 1])
        result = run_checked(
            [
                str(python),
                "-c",
                (
                    "from pathlib import Path; from immuknow.orchestrator import run_pipeline; "
                    f"completion=run_pipeline(Path({str(input_file)!r}), Path({str(output_dir)!r}), "
                    f"config_dir=Path({str(config_dir)!r}), notice_assignments=Path({str(manifest)!r})); "
                    "assert completion.is_file()"
                ),
            ],
            unrelated,
        )
        assert "Pipeline completed successfully" in result.stdout
        assert len(list((output_dir / "pdf_individual").glob("*.pdf"))) == 2

        # Exercise the opposite application-owned names through the installed CLI.
        (unrelated / "config.py").unlink()
        (unrelated / "config").mkdir()
        (unrelated / "config" / "__init__.py").write_text(
            'raise RuntimeError("APPLICATION CONFIG IMPORTED")'
        )
        shutil.rmtree(unrelated / "templates")
        (unrelated / "templates.py").write_text(
            'raise RuntimeError("APPLICATION TEMPLATES IMPORTED")'
        )
        custom = tmp_path / "Private PHU modèles"
        shutil.copytree(installed_dirs[0] / "templates", custom)
        for directory in [custom, *custom.rglob("*")]:
            if directory.is_dir():
                directory.chmod(0o755)
        custom_output = tmp_path / "Custom installed templates"
        run_checked(
            [
                str(environment / "bin" / "immuknow"),
                str(input_file),
                "--template",
                str(custom / "overdue_diseases_v1.fr.typ"),
                "--output",
                str(custom_output),
            ],
            unrelated,
        )
        assert len(list((custom_output / "pdf_individual").glob("*.pdf"))) == 2
        assert not (unrelated / "output").exists()
    finally:
        for path, mode in original_modes.items():
            path.chmod(mode)
