"""Authored notices keep the complete engine-supplied component library."""

import json
import shutil
from hashlib import sha256
from pathlib import Path

import pytest

from tests.integration.test_native_pipeline import ROOT, prepare_cohort, run_cli

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "change",
    ["changed", "missing", "extra", "renamed", "linked_file", "linked_directory"],
)
def test_changed_library_stops_cohort_before_rendering(tmp_path: Path, change: str):
    command, output, _ = prepare_cohort(tmp_path)
    templates = tmp_path / "templates"
    shutil.copytree(ROOT / "immuknow/templates", templates)
    library = templates / "lib/immuknow"
    component = library / "src/findings.typ"
    if change == "changed":
        component.write_text(component.read_text() + "\n// Unsupported change\n")
    elif change == "missing":
        component.unlink()
    elif change == "extra":
        (library / "extra.typ").write_text("#let changed = true\n")
    elif change == "renamed":
        component.rename(component.with_name("renamed.typ"))
    elif change == "linked_file":
        outside = tmp_path / "findings.typ"
        component.rename(outside)
        component.symlink_to(outside)
    else:
        outside = tmp_path / "library"
        library.rename(outside)
        library.symlink_to(outside, target_is_directory=True)
    # An authored file list can describe changed bytes, but cannot approve them.
    (templates / "build.json").write_text(
        json.dumps(
            {
                "shared_resources": {
                    "files": [
                        {
                            "path": path.relative_to(templates).as_posix(),
                            "sha256": sha256(path.read_bytes()).hexdigest(),
                        }
                        for path in library.rglob("*")
                        if path.is_file()
                    ]
                }
            }
        )
    )
    result = run_cli(command + ["--templates", str(templates)], tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    record = json.loads(next(output.glob("*/run.json")).read_text())
    assert record["status"] == "failed_setup"
    assert "supplied" in result.stdout + result.stderr
    assert not list(output.rglob("*.pdf"))
    assert all(entry["original"]["status"] == "not_run" for entry in record["entries"])
