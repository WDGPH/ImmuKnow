"""Describe Studio's compiler and the shared resources needed to open a project."""

import json
import subprocess
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path

from immuknow.build_info import file_manifest, native_typst_version, source_details

ROOT = Path(__file__).resolve().parents[2]


def project_build() -> dict:
    package = ROOT / "immuknow"
    pins = json.loads((ROOT / "studio/compiler-pins.json").read_text(encoding="utf-8"))
    shared = [package / "schemas/rendering-v1.json"]
    shared += [
        path
        for path in (package / "templates/lib/immuknow").rglob("*")
        if path.is_file()
    ]
    source = source_details(ROOT)
    modified = None
    if source["source_revision"]:
        modified = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=ROOT, text=True
            ).strip()
        )
    schema = json.loads(
        (package / "schemas/rendering-v1.json").read_text(encoding="utf-8")
    )
    return {
        "application_version": version("ImmuKnow"),
        "rendering_schema_version": schema["properties"]["schema_version"]["const"],
        "native_typst_version": native_typst_version(package),
        **pins,
        "compiler_build_sha256": sha256(
            json.dumps(pins["browser_compiler"], sort_keys=True).encode()
        ).hexdigest(),
        "shared_resources": file_manifest(package, shared),
        "source_revision": source["source_revision"],
        "source_modified": modified,
    }
