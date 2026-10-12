"""Validate the one structural facts contract shared by native Typst and Studio."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


def validate_render_payload(payload: dict[str, Any]) -> None:
    """Reject unusable structures while allowing blank optional source facts."""
    schema = json.loads(
        files("immuknow")
        .joinpath("schemas/rendering-v1.json")
        .read_text(encoding="utf-8")
    )
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
