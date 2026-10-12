"""Identify native package files without reading or building Studio resources."""

from __future__ import annotations

import ast
import json
import platform
import subprocess
from hashlib import sha256
from importlib.metadata import version
from importlib.resources import files
from pathlib import Path
from typing import Any


def file_manifest(root: Path, paths: list[Path]) -> dict[str, Any]:
    records = []
    for path in sorted(paths):
        if path.is_symlink():
            raise ValueError(f"Build input cannot be a link: {path}")
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256(path.read_bytes()).hexdigest(),
            }
        )
    digest = sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()
    return {"sha256": digest, "files": records}


def package_files(package: Path) -> list[Path]:
    return [
        path
        for path in package.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix not in {".pyc", ".pyo"}
        and path != package / "build.json"
    ]


def native_typst_version(package: Path) -> str:
    source = ast.parse((package / "compile_notices.py").read_text(encoding="utf-8"))
    return next(
        ast.literal_eval(node.value)
        for node in source.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "TYPST_VERSION"
            for target in node.targets
        )
    )


def source_details(root: Path) -> dict[str, Any]:
    paths = package_files(root / "immuknow") + [
        root / name
        for name in (
            "pyproject.toml",
            "setup.py",
            "setup.cfg",
            "MANIFEST.in",
            "README.md",
            "LICENSE",
            "LICENSE.txt",
            "uv.lock",
            "scripts/build-native.py",
        )
        if (root / name).is_file()
    ]
    inputs = file_manifest(root, paths)
    revision, modified = None, None
    try:
        repository = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (FileNotFoundError, subprocess.CalledProcessError):
        repository = None
    if repository and Path(repository).resolve() == root.resolve():
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip()
        modified = bool(
            subprocess.check_output(
                [
                    "git",
                    "status",
                    "--porcelain",
                    "--",
                    "immuknow",
                    *[
                        item["path"]
                        for item in inputs["files"]
                        if not item["path"].startswith("immuknow/")
                    ],
                ],
                cwd=root,
                text=True,
            ).strip()
        )
    elif (root / "immuknow/build.json").is_file():
        prior = json.loads((root / "immuknow/build.json").read_text(encoding="utf-8"))
        revision = prior["source_revision"]
        modified = prior["source_modified"]
        if inputs != prior["source_inputs"]:
            modified = True
    return {
        "source_revision": revision,
        "source_modified": modified,
        "source_inputs": inputs,
    }


def create_build_info(
    package: Path, application_version: str, source: dict, *, kind: str
) -> dict[str, Any]:
    schema = json.loads(
        (package / "schemas/rendering-v1.json").read_text(encoding="utf-8")
    )
    result = {
        "format_version": 1,
        "kind": kind,
        "application_version": application_version,
        "rendering_schema_version": schema["properties"]["schema_version"]["const"],
        "native_typst_version": native_typst_version(package),
        **source,
        "package_files": file_manifest(package, package_files(package)),
    }
    if kind != "checkout":
        result["build_tools"] = {
            "python": platform.python_version(),
            "setuptools": version("setuptools"),
            "wheel": version("wheel"),
        }
    return result


def current_build_info() -> dict[str, Any]:
    package = Path(str(files("immuknow")))
    manifest = package / "build.json"
    if manifest.is_file():
        return json.loads(manifest.read_text(encoding="utf-8"))
    if not (package.parent / "pyproject.toml").is_file():
        raise ValueError("The installed package is missing its build record")
    return create_build_info(
        package, version("ImmuKnow"), source_details(package.parent), kind="checkout"
    )
