"""Verify a browser-edited project through both real CLI selectors, outside checkout."""

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from playground.scripts.pdf_compare import compare_pdf

ROOT = Path(__file__).resolve().parents[2]


def verify(
    archive: Path, browser_pdf: Path, flattened: Path | None = None
) -> list[dict]:
    reports = []
    with tempfile.TemporaryDirectory(prefix="immuknow-browser-export-") as temporary:
        clean = Path(temporary)
        distributions = clean / "distributions"
        environment = clean / "environment"
        requirements = clean / "requirements.txt"
        setup_commands = [
            ["uv", "build", "--wheel", "--out-dir", str(distributions)],
            ["uv", "venv", "--python", sys.executable, str(environment)],
            [
                "uv",
                "export",
                "--frozen",
                "--no-dev",
                "--no-emit-project",
                "--no-hashes",
                "--output-file",
                str(requirements),
            ],
        ]
        for command in setup_commands:
            subprocess.run(command, cwd=ROOT, check=True, capture_output=True)
        python = environment / "bin/python"
        subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                "--no-deps",
                "-r",
                str(requirements),
                str(next(distributions.glob("*.whl"))),
            ],
            cwd=clean,
            check=True,
            capture_output=True,
        )
        project = clean / "relocated project"
        project.mkdir()
        with zipfile.ZipFile(archive) as zipped:
            assert sum(info.file_size for info in zipped.infolist()) <= 24 * 1024 * 1024
            for info in zipped.infolist():
                path = PurePosixPath(info.filename)
                assert (
                    not path.is_absolute()
                    and ".." not in path.parts
                    and "\\" not in info.filename
                )
                assert not stat.S_ISLNK(info.external_attr >> 16)
            zipped.extractall(project)
        manifest = json.loads((project / "immuknow-project.json").read_text())
        template = project / manifest["template"]
        assert template.resolve().is_relative_to(project / "templates")
        assert template.name == "overdue_diseases_v1.en.typ"
        originals = {
            path.relative_to(project).as_posix(): path.read_bytes()
            for path in (project / "templates").rglob("*")
            if path.is_file()
        }
        for selector in ("single", "manifest"):
            output = Path(temporary) / selector
            command = [
                str(python),
                "-m",
                "immuknow.orchestrator",
                str(project / "examples/known-overdue.csv"),
                "--config",
                str(project / "config"),
                "--output",
                str(output),
            ]
            if selector == "single":
                command.extend(["--template", str(template)])
            else:
                command.extend(
                    [
                        "--notice-assignments",
                        str(project / "examples/assignments.json"),
                        "--templates",
                        str(project / "templates"),
                    ]
                )
            result = subprocess.run(
                command,
                cwd=project,
                capture_output=True,
                text=True,
                check=False,
                env={
                    **os.environ,
                    "TYPST_FONT_PATHS": "/usr/share/fonts/truetype/freefont",
                    "TYPST_IGNORE_SYSTEM_FONTS": "true",
                    "PYTHONPATH": "",
                    "XDG_CACHE_HOME": str(clean / "empty-cache"),
                    "TYPST_PACKAGE_PATH": str(clean / "empty-packages"),
                    "TYPST_PACKAGE_CACHE_PATH": str(clean / "empty-packages"),
                },
            )
            assert result.returncode == 0, result.stdout + result.stderr
            assert "did not converge" not in result.stderr
            assert len(list((output / "metadata").glob("completion_*.json"))) == 1
            jobs = json.loads((output / "artifacts/render_jobs.json").read_text())[
                "jobs"
            ]
            assert len(jobs) == 8
            selected = next(job for job in jobs if job["client_id"] == "0000000001")
            assert Path(selected["template"]).name == template.name
            assert all(
                (project / name).read_bytes() == value
                for name, value in originals.items()
            )
            for name, value in originals.items():
                assert (Path(selected["workspace"]) / name).read_bytes() == value
            if flattened:
                workspace = Path(selected["workspace"])
                Path(selected["template"]).write_bytes(flattened.read_bytes())
                # Removing companion settings proves the download is self-contained for settings.
                shutil.rmtree(workspace / "templates/settings")
                (workspace / "templates/layout-settings.json").unlink()
                flattened_pdf = archive.parent / f"{selector}.flattened.pdf"
                subprocess.run(
                    [
                        "typst",
                        "compile",
                        "--root",
                        str(workspace),
                        "--input",
                        "data=/"
                        + Path(selected["data"]).relative_to(workspace).as_posix(),
                        str(selected["template"]),
                        str(flattened_pdf),
                    ],
                    check=True,
                    capture_output=True,
                    env={
                        **os.environ,
                        "TYPST_FONT_PATHS": "/usr/share/fonts/truetype/freefont",
                        "TYPST_IGNORE_SYSTEM_FONTS": "true",
                    },
                )
                compare_pdf(flattened_pdf, browser_pdf)
            native = archive.parent / f"{selector}.native.pdf"
            shutil.copyfile(selected["pdf"], native)
            reports.append(
                {
                    "selector": selector,
                    "installed_wheel": True,
                    "clients": len(jobs),
                    "source_sha256": hashlib.sha256(template.read_bytes()).hexdigest(),
                    **compare_pdf(native, browser_pdf),
                }
            )
    (archive.parent / "roundtrip.json").write_text(json.dumps(reports, indent=2) + "\n")
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("browser_pdf", type=Path)
    parser.add_argument("--flattened", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            verify(
                args.archive.resolve(),
                args.browser_pdf.resolve(),
                args.flattened.resolve() if args.flattened else None,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
