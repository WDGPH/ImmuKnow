"""Validate the versioned rendering contract before writing notice JSON."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


def validate_render_payload(payload: dict[str, Any]) -> None:
    """Reject unsupported schemas and report the first invalid field by path."""
    version = payload.get("schema_version")
    if type(version) is not int or version != 1:
        raise ValueError(
            f"Unsupported rendering schema_version {version!r}; expected 1"
        )
    schema = json.loads(
        files("immuknow")
        .joinpath("schemas/rendering-v1.json")
        .read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    error = next(iter(validator.iter_errors(payload)), None)
    if error is not None:
        path = ".".join(str(part) for part in error.absolute_path) or "payload"
        raise ValueError(f"Invalid rendering payload at {path}: {error.message}")
