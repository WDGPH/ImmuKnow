"""Run a fresh native wheel outside the checkout using only locked resources."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from hashlib import sha256
from pathlib import Path

import pymupdf
import pytest
import yaml
import zxingcpp
from pypdf import PdfReader
from pypdf.generic import DictionaryObject

from tests.fixtures.sample_input import create_test_input_dataframe

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


def run_checked(
    command: list[str], cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess:
    result = subprocess.run(
        command, cwd=cwd, env=env, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def test_installed_wheel_uses_packaged_and_external_resources(tmp_path: Path) -> None:
    distributions = tmp_path / "distributions"
    source_paths = (
        subprocess.check_output(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT,
        )
        .decode()
        .split("\0")
    )
    source_before = {
        name: sha256((ROOT / name).read_bytes()).hexdigest()
        if (ROOT / name).is_file()
        else None
        for name in source_paths
        if name
    }
    run_checked(
        [
            sys.executable,
            str(ROOT / "scripts/build-native.py"),
            "--out-dir",
            str(distributions),
        ],
        ROOT,
    )
    assert not (ROOT / "immuknow/build.json").exists()
    assert source_before == {
        name: sha256((ROOT / name).read_bytes()).hexdigest()
        if (ROOT / name).is_file()
        else None
        for name in source_before
    }
    wheel = next(distributions.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        for resource in (
            "build.json",
            "schemas/input_schema.json",
            "schemas/rendering-v1.json",
            "templates/settings.typ",
            "templates/presentation.typ",
            "templates/lib/immuknow/lib.typ",
            "templates/lib/immuknow/src/findings.typ",
            "templates/lib/immuknow/vendor/codetastic/LICENSE",
            "templates/assets/logo.png",
            "templates/assets/signature.png",
            "templates/suspension_order_v1.en.typ",
            "review_templates/review_sheet.typ",
            "review_templates/review_stamp.typ",
        ):
            assert f"immuknow/{resource}" in names
        for language in ("en", "fr"):
            for domain in ("diseases_chart", "diseases_overdue"):
                assert (
                    f"immuknow/templates/translations/{language}_{domain}.json" in names
                )
        assert not any(
            name.endswith((".ttf", ".otf", ".woff", ".woff2")) for name in names
        )
        build = json.loads(archive.read("immuknow/build.json"))
        assert (
            build["source_revision"]
            == subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip()
        )
        assert build["rendering_schema_version"] == 1
        assert build["kind"] == "wheel"
        assert (
            not {
                "base_revision",
                "donor_revision",
                "browser_compiler",
                "browser_renderer",
            }
            & build.keys()
        )
        assert build["build_tools"]["setuptools"] == "84.0.0"
        assert build["build_tools"]["wheel"] == "0.48.0"
        assert {
            item["path"]: item["sha256"] for item in build["package_files"]["files"]
        } == {
            name.removeprefix("immuknow/"): sha256(archive.read(name)).hexdigest()
            for name in names
            if name.startswith("immuknow/") and name != "immuknow/build.json"
        }
        assert not any(
            name.startswith(("studio/", "node_modules/", "pipeline/")) for name in names
        )
        metadata = (
            archive.read(
                next(name for name in names if name.endswith(".dist-info/METADATA"))
            )
            .decode()
            .lower()
        )
        assert "requires-dist: pillow" not in metadata
        assert "requires-dist: qrcode" not in metadata
    with tarfile.open(next(distributions.glob("*.tar.gz"))) as archive:
        assert not any(
            name.endswith((".ttf", ".otf", ".woff", ".woff2"))
            for name in archive.getnames()
        )

    environment = tmp_path / "Clean environment"
    run_checked(["uv", "venv", "--python", sys.executable, str(environment)], tmp_path)
    python = environment / "bin/python"
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
    (unrelated / "templates.py").write_text(
        'raise RuntimeError("APPLICATION TEMPLATES IMPORTED")'
    )
    inspect = run_checked(
        [
            str(python),
            "-c",
            "from hashlib import sha256; "
            "from immuknow.resources import resource_root, rendering_build_info; "
            "p = resource_root(); b = rendering_build_info(); "
            "assert (p / 'templates/settings.typ').is_file(); "
            "assert (p / 'config/parameters.yaml').is_file(); "
            "assert b['rendering_schema_version'] == 1; "
            "assert b['core_source_revision']; "
            "assert all(sha256((p / f['path']).read_bytes()).hexdigest() == "
            "f['sha256'] for f in b['shared_resources']['files']); "
            "print(p)",
        ],
        unrelated,
    )
    installed = Path(inspect.stdout.strip())
    assert installed.is_relative_to(environment)
    run_checked(
        [
            str(python),
            "-c",
            "import importlib.util; assert all(importlib.util.find_spec(m) is None for m in ('PIL','qrcode','pymupdf','zxingcpp'))",
        ],
        unrelated,
    )

    source = tmp_path / "Élèves.csv"
    frame = create_test_input_dataframe(num_clients=2)
    frame["overdue_disease"] = "Measles - 2"
    frame["overdue_agent"] = "M"
    frame.loc[0, "street_address_line_1"] = ""
    frame.to_csv(source, index=False)
    assignments = tmp_path / "assignments.json"
    assignments.write_text(
        json.dumps(
            [
                {"client_id": "0000000001", "template": "overdue_agents_v1.en.typ"},
                {"client_id": "0000000002", "template": "overdue_agents_v1.fr.typ"},
            ]
        )
    )
    config_dir = tmp_path / "Configuration"
    shutil.copytree(installed / "config", config_dir)
    parameters = config_dir / "parameters.yaml"
    settings = yaml.safe_load(parameters.read_text())
    settings["encryption"] = {
        "enabled": True,
        "password": {"template": "{date_of_birth_iso_compact}"},
    }
    parameters.write_text(yaml.safe_dump(settings))
    (config_dir / "input_schema.json").write_text("not a schema")
    native_bin = tmp_path / "Native tools"
    native_bin.mkdir()
    compiler = os.environ.get("TYPST_BIN", "typst")
    (native_bin / "typst").symlink_to(
        Path(shutil.which(compiler) or compiler).resolve()
    )
    native_env: dict[str, str] = {
        **os.environ,
        "PATH": f"{environment / 'bin'}{os.pathsep}{native_bin}",
        "TYPST_BIN": str(native_bin / "typst"),
    }
    native_env.pop("PYTHONPATH", None)
    run_checked(
        [
            str(python),
            "-c",
            "import shutil; assert shutil.which('node') is None; assert shutil.which('rustc') is None",
        ],
        unrelated,
        native_env,
    )
    resources = [installed, *installed.rglob("*")]
    modes = {path: path.stat().st_mode & 0o777 for path in resources}
    try:
        for path in resources:
            path.chmod(0o555 if path.is_dir() else 0o444)
        manifest_output = tmp_path / "Manifest run"
        run_checked(
            [
                str(python),
                "-c",
                "from pathlib import Path; from immuknow.orchestrator import run_pipeline; "
                f"p=run_pipeline(Path({str(source)!r}),Path({str(manifest_output)!r}),"
                f"config_dir=Path({str(config_dir)!r}),notice_assignments=Path({str(assignments)!r})); assert p.name=='run.json'",
            ],
            unrelated,
            native_env,
        )
        custom = tmp_path / "Private PHU modèles"
        shutil.copytree(installed / "templates", custom)
        for path in [custom, *custom.rglob("*")]:
            path.chmod(0o755 if path.is_dir() else 0o644)
        labels_path = custom / "translations/fr_diseases_overdue.json"
        labels = json.loads(labels_path.read_text())
        labels["Measles"] = "LIBELLÉ LOCAL SÉLECTIONNÉ"
        labels_path.write_text(json.dumps(labels, ensure_ascii=False))
        relocated = tmp_path / "Moved project"
        custom.rename(relocated)
        settings_path = relocated / "settings.typ"
        settings_path.write_text(
            settings_path.read_text().replace(
                'body-font = "FreeSans"', 'body-font = "New Computer Modern"'
            )
        )
        custom_output = tmp_path / "Custom run"
        run_checked(
            [
                str(environment / "bin/immuknow"),
                str(source),
                "--template",
                str(relocated / "overdue_diseases_v1.fr.typ"),
                "--config",
                str(config_dir),
                "--output",
                str(custom_output),
            ],
            unrelated,
            native_env,
        )
        for output in (manifest_output, custom_output):
            records = list(output.glob("*/run.json"))
            assert len(records) == 1
            run_dir = records[0].parent
            record = json.loads(records[0].read_text())
            assert record["status"] in ("completed", "completed_with_warnings")
            assert "base" not in record["version"]
            assert record["version"]["build"] == build
            assert len(record["entries"]) == 2
            assert "compiler_fonts" not in record["resources"]
            assert not list((run_dir / "resources").rglob("*.ttf"))
            for entry in record["entries"]:
                assert entry["original"]["status"] == "completed"
                pdf = run_dir / entry["original"]["path"]
                assert (
                    sha256(pdf.read_bytes()).hexdigest() == entry["original"]["sha256"]
                )
                reader = PdfReader(pdf)
                if output == custom_output:
                    with pymupdf.open(pdf) as local_font_pdf:
                        assert any(
                            "NewCM" in font[3]
                            for page in local_font_pdf
                            for font in page.get_fonts()
                        )
                encrypted_artifact = entry["encryption"]
                assert encrypted_artifact["requested"] is True
                assert encrypted_artifact["status"] == "completed"
                encrypted_path = run_dir / encrypted_artifact["path"]
                assert (
                    sha256(encrypted_path.read_bytes()).hexdigest()
                    == encrypted_artifact["sha256"]
                )
                encrypted_reader = PdfReader(encrypted_path)
                assert encrypted_reader.is_encrypted
                assert encrypted_artifact["method"] == {
                    "algorithm": "AES-256",
                    "revision": 6,
                    "key_bits": 256,
                }
                profile = encrypted_reader.trailer["/Encrypt"]
                assert isinstance(profile, DictionaryObject)
                assert (profile["/V"], profile["/R"], profile["/Length"]) == (5, 6, 256)
                password = {"0000000001": "20150102", "0000000002": "20140506"}[
                    entry["client_id"]
                ]
                assert encrypted_reader.decrypt(password) > 0
                assert entry["client_id"] in encrypted_reader.pages[0].extract_text()
                with pymupdf.open(encrypted_path) as opened:
                    assert opened.needs_pass
                    assert not opened.authenticate("")
                    assert not opened.authenticate("wrong-password")
                    assert opened.authenticate(password)
                    assert entry["client_id"] in opened[0].get_text()
                    assert opened.page_count == len(reader.pages)
                    with pymupdf.open(pdf) as original:
                        for page_number in range(opened.page_count):
                            assert (
                                opened[page_number].get_pixmap().samples
                                == original[page_number].get_pixmap().samples
                            )
                text = " ".join(page.extract_text() for page in reader.pages)
                assert entry["client_id"] in reader.pages[0].extract_text()
                assert entry["render_summary"]["page_count"] == len(reader.pages)
                assert not any(
                    check["code"].startswith("compiler.") for check in entry["checks"]
                )
                if output == custom_output and entry["client_id"] == "0000000001":
                    assert "LIBELLÉ LOCAL SÉLECTIONNÉ" in text
                with pymupdf.open(pdf) as rendered:
                    decoded = set()
                    for page in rendered:
                        pixmap = page.get_pixmap(dpi=150, colorspace=pymupdf.csGRAY)
                        pixels = memoryview(pixmap.samples).cast(
                            "B", [pixmap.height, pixmap.width]
                        )
                        decoded.update(
                            code.text for code in zxingcpp.read_barcodes(pixels)
                        )
                assert decoded == set(entry["render_summary"]["qr_urls"])
            assert (run_dir / "report.html").is_file()

        # The custom run survives removal of every original authored input.
        first = next(
            entry for entry in record["entries"] if entry["client_id"] == "0000000001"
        )
        assert first["routing"]["destination"] == "review"
        warning_checks = [
            check for check in first["checks"] if check["status"] == "warn"
        ]
        assert any(
            check["code"] == "source.address_incomplete" for check in warning_checks
        )
        review_membership = first["bundle"]
        review_pages = PdfReader(run_dir / review_membership["path"]).pages
        assert "source.address_incomplete" in " ".join(
            page.extract_text()
            for page in review_pages[
                review_membership["sheet_start_page"] - 1 : review_membership[
                    "sheet_end_page"
                ]
            ]
        )
        for page in review_pages[
            review_membership["notice_start_page"] - 1 : review_membership[
                "notice_end_page"
            ]
        ]:
            assert "REVIEW" in page.extract_text()
        originals = {
            entry["row_key"]: entry["original"].copy() for entry in record["entries"]
        }
        encryptions = {
            entry["row_key"]: entry["encryption"].copy() for entry in record["entries"]
        }
        for path in (source, assignments):
            path.unlink()
        shutil.rmtree(config_dir)
        shutil.rmtree(relocated)
        tokens = list(
            record["delivery_attempts"][-1]["evaluations"][first["row_key"]][
                "warning_tokens"
            ].values()
        )
        run_checked(
            [
                str(environment / "bin/immuknow-rebundle"),
                str(run_dir),
                *[arg for token in tokens for arg in ("--accept-warning", token)],
                "--reason",
                "Reviewed original PDF",
            ],
            unrelated,
            native_env,
        )
        rebundled = json.loads((run_dir / "run.json").read_text())
        assert (
            len(rebundled["delivery_attempts"]) == len(record["delivery_attempts"]) + 1
        )
        attempt = rebundled["delivery_attempts"][-1]
        assert attempt["status"] == "completed"
        assert attempt["review"]["accepted_tokens"] == tokens
        assert rebundled["warning_acceptances"]
        member_rows = [
            row for bundle in attempt["bundles"] for row in bundle["row_keys"]
        ]
        assert len(member_rows) == len(set(member_rows)) == 2
        assert set(member_rows) == set(originals) == set(attempt["memberships"])
        assert {
            path.relative_to(run_dir).as_posix()
            for path in (run_dir / "bundles").rglob("*.pdf")
        } == {bundle["path"] for bundle in attempt["bundles"]}
        for entry in rebundled["entries"]:
            assert entry["original"] == originals[entry["row_key"]]
            assert entry["encryption"] == encryptions[entry["row_key"]]
            assert (
                sha256((run_dir / entry["original"]["path"]).read_bytes()).hexdigest()
                == entry["original"]["sha256"]
            )
        delivered = next(
            entry
            for entry in rebundled["entries"]
            if entry["client_id"] == "0000000001"
        )
        assert delivered["routing"]["destination"] == "delivery"
        assert [
            check for check in delivered["checks"] if check["status"] == "warn"
        ] == warning_checks
        membership = delivered["bundle"]
        assert membership["sheet_start_page"] is None
        assert membership["sheet_end_page"] is None
        delivered_pages = PdfReader(run_dir / membership["path"]).pages[
            membership["notice_start_page"] - 1 : membership["notice_end_page"]
        ]
        original_pages = PdfReader(run_dir / delivered["original"]["path"]).pages
        assert len(delivered_pages) == len(original_pages)
        for actual, original in zip(delivered_pages, original_pages):
            assert "REVIEW" not in actual.extract_text()
            assert " ".join(actual.extract_text().split()) == " ".join(
                original.extract_text().split()
            )
        assert not custom.exists()
        assert not (unrelated / "runs").exists()
    finally:
        for path, mode in modes.items():
            path.chmod(mode)
