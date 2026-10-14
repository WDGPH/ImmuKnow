"""Read installed templates, schemas and rendering identity for authoring tools.

Resources belong to the installed engine. Copy them before editing; neither
Studio builds nor native runs should write into the installed package.
"""

from importlib.resources import files
from pathlib import Path
from typing import Any

from .build_info import current_build_info, file_manifest


def resource_root() -> Path:
    """Locate read-only resources in an unpacked wheel or editable installation."""
    return Path(str(files("immuknow")))


def rendering_build_info() -> dict[str, Any]:
    """Identify the installed engine and its complete shared rendering resources.

    Browser tools add their own compiler and application identity separately.
    Compatibility depends on formats and resource bytes, not application versions.
    """
    package = resource_root()
    build = current_build_info()
    shared = [package / "schemas/rendering-v1.json"]
    shared.extend(
        path
        for path in (package / "templates/lib/immuknow").rglob("*")
        if path.is_file()
    )
    return {
        "application_version": build["application_version"],
        "rendering_schema_version": build["rendering_schema_version"],
        "native_typst_version": build["native_typst_version"],
        "shared_resources": file_manifest(package, shared),
        "core_source_revision": build["source_revision"],
        "core_source_modified": build["source_modified"],
    }
