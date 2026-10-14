"""Native builds work from source alone and never write into package source."""

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

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


def command(arguments, directory, env=None):
    result = subprocess.run(
        arguments, cwd=directory, env=env, text=True, capture_output=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


def snapshot(root):
    return {
        path.relative_to(root).as_posix(): sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
        and not any(
            part in {".git", "__pycache__", "build"} or part.endswith(".egg-info")
            for part in path.relative_to(root).parts
        )
    }


def wheel_info(directory):
    with zipfile.ZipFile(next(directory.glob("*.whl"))) as archive:
        record = json.loads(archive.read("immuknow/build.json"))
        recorded = {
            item["path"]: item["sha256"] for item in record["package_files"]["files"]
        }
        actual = {
            name.removeprefix("immuknow/"): sha256(archive.read(name)).hexdigest()
            for name in archive.namelist()
            if name.startswith("immuknow/") and name != "immuknow/build.json"
        }
        assert recorded == actual
        return record


def test_readonly_source_build_and_rebuild_without_git_studio_or_typst(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    for name in (
        "pyproject.toml",
        "setup.py",
        "MANIFEST.in",
        "README.md",
        "LICENSE",
        "uv.lock",
        ".gitignore",
    ):
        shutil.copyfile(ROOT / name, source / name)
    shutil.copytree(
        ROOT / "immuknow",
        source / "immuknow",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (source / "scripts").mkdir()
    shutil.copyfile(
        ROOT / "scripts/build-native.py", source / "scripts/build-native.py"
    )
    for name in snapshot(source):
        (source / name).chmod(0o444)
    command(["git", "init", "--quiet"], source)
    command(["git", "add", "."], source)
    command(
        [
            "git",
            "-c",
            "user.name=Build test",
            "-c",
            "user.email=build@example.invalid",
            "commit",
            "--quiet",
            "-m",
            "Native sources",
        ],
        source,
    )
    revision = command(["git", "rev-parse", "HEAD"], source)
    before = snapshot(source)
    # Build execution has Python and uv only; neither a native nor browser compiler is needed.
    tools = tmp_path / "tools"
    tools.mkdir()
    for name, target in (
        ("python", sys.executable),
        ("uv", shutil.which("uv")),
        ("git", shutil.which("git")),
    ):
        assert target is not None
        (tools / name).symlink_to(target)
    env = {**os.environ, "PATH": str(tools)}
    out = tmp_path / "first-build"
    command(
        [sys.executable, "scripts/build-native.py", "--out-dir", str(out)], source, env
    )
    assert snapshot(source) == before
    assert command(["git", "status", "--porcelain"], source) == ""
    info = wheel_info(out)
    assert info["source_revision"] == revision
    assert info["source_modified"] is False
    assert info["kind"] == "wheel"
    assert (
        not {"browser_compiler", "browser_renderer", "base_revision", "donor_revision"}
        & info.keys()
    )

    unpacked = tmp_path / "unpacked"
    with tarfile.open(next(out.glob("*.tar.gz"))) as archive:
        archive.extractall(unpacked, filter="data")
    (rebuild_source,) = unpacked.iterdir()
    assert not (rebuild_source / ".git").exists()
    assert not (rebuild_source / "studio").exists()
    original = (rebuild_source / "immuknow/build.json").read_bytes()
    staged = json.loads(original)
    assert staged["kind"] == "sdist"
    assert staged["source_revision"] == revision
    assert staged["source_modified"] is False
    snapshot_before = snapshot(rebuild_source)
    for name in snapshot_before:
        (rebuild_source / name).chmod(0o444)
    (tools / "git").unlink()
    rebuilt = tmp_path / "rebuilt"
    command(["uv", "build", "--out-dir", str(rebuilt)], rebuild_source, env)
    assert snapshot(rebuild_source) == snapshot_before
    assert (rebuild_source / "immuknow/build.json").read_bytes() == original
    rebuilt_info = wheel_info(rebuilt)
    assert rebuilt_info["source_revision"] == revision
    assert rebuilt_info["source_modified"] is False
    assert rebuilt_info["package_files"] == info["package_files"]

    # Editing unpacked source keeps its known starting revision and reports the change.
    changed = rebuild_source / "immuknow/templates/settings.typ"
    changed.chmod(0o644)
    changed.write_bytes(changed.read_bytes() + b"\n// Changed after unpacking\n")
    modified = tmp_path / "modified"
    command(["uv", "build", "--wheel", "--out-dir", str(modified)], rebuild_source, env)
    modified_info = wheel_info(modified)
    assert modified_info["source_revision"] == revision
    assert modified_info["source_modified"] is True
    assert modified_info["package_files"] != info["package_files"]
    assert (rebuild_source / "immuknow/build.json").read_bytes() == original
