"""Build records identify the exact package and shared rendering resources."""

import json
import subprocess
from hashlib import sha256
from pathlib import Path

import pytest

from immuknow import build_info
from immuknow.resources import rendering_build_info, resource_root

ROOT = Path(__file__).resolve().parents[2]


def test_checkout_identifies_its_revision_and_shared_resources():
    package = resource_root()
    info = rendering_build_info()
    assert package == ROOT / "immuknow"
    assert info["rendering_schema_version"] == 1
    assert (
        info["core_source_revision"]
        == subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    )
    files = info["shared_resources"]["files"]
    assert "schemas/rendering-v1.json" in {item["path"] for item in files}
    assert all(
        sha256((package / item["path"]).read_bytes()).hexdigest() == item["sha256"]
        for item in files
    )


def test_distribution_record_includes_build_tools():
    info = build_info.create_build_info(
        resource_root(), "1.0.0", {"source_revision": None}, kind="wheel"
    )
    assert info["kind"] == "wheel"
    assert set(info["build_tools"]) == {"python", "setuptools", "wheel"}


def test_installed_record_is_read_and_its_absence_is_refused(tmp_path, monkeypatch):
    package = tmp_path / "immuknow"
    package.mkdir()
    monkeypatch.setattr(build_info, "files", lambda name: package)
    with pytest.raises(ValueError, match="missing its build record"):
        build_info.current_build_info()
    (package / "build.json").write_text('{"kind": "wheel"}')
    assert build_info.current_build_info() == {"kind": "wheel"}


@pytest.mark.parametrize("changed", [False, True])
def test_source_outside_git_keeps_its_recorded_revision(tmp_path, changed):
    package = tmp_path / "immuknow"
    package.mkdir()
    (package / "module.py").write_text("VALUE = 1\n")
    inputs = build_info.file_manifest(tmp_path, [package / "module.py"])
    (package / "build.json").write_text(
        json.dumps(
            {
                "source_revision": "abc123",
                "source_modified": False,
                "source_inputs": inputs,
            }
        )
    )
    if changed:
        (package / "module.py").write_text("VALUE = 2\n")
    details = build_info.source_details(tmp_path)
    assert details["source_revision"] == "abc123"
    assert details["source_modified"] is changed


def test_linked_build_input_is_refused(tmp_path):
    (tmp_path / "target.txt").write_text("text")
    (tmp_path / "link.txt").symlink_to(tmp_path / "target.txt")
    with pytest.raises(ValueError, match="cannot be a link"):
        build_info.file_manifest(tmp_path, [tmp_path / "link.txt"])
