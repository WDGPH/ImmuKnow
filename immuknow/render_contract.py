"""Validate placed report structure and its association with one notice."""

import json
from importlib.resources import files
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from .structured_input import parse_json


def report_schema() -> dict:
    return parse_json(
        files("immuknow")
        .joinpath("templates/lib/immuknow/report-v2.json")
        .read_text(encoding="utf-8")
    )


def validate_render_report(summary: Any, identity: dict[str, str]) -> None:
    """Reject unsupported evidence, contradictory components and out-of-range pages."""
    schema = report_schema()
    try:
        json.dumps(summary, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise ValueError("Render evidence contains an unsupported value") from exc
    try:
        Draft202012Validator(schema).validate(summary)
    except ValidationError as exc:
        path = "/".join(str(part) for part in exc.absolute_path) or "report"
        raise ValueError(f"Render evidence has an invalid field: {path}") from exc
    if summary["identity"] != identity:
        raise ValueError(
            "Render evidence does not belong to the selected source row and notice"
        )

    def bounds(value: dict) -> None:
        for key, number in value.items():
            if (key == "page" or key.endswith("_page")) and number > summary[
                "page_count"
            ]:
                raise ValueError("Render evidence refers to a page outside this notice")
        if value.get("first_page", 0) > value.get("last_page", summary["page_count"]):
            raise ValueError("Render evidence has a reversed page range")

    rules = {
        item["const"]: item
        for item in schema["$defs"]["check"]["properties"]["code"]["oneOf"]
    }
    for name, placed in summary["components"].items():
        measurements = summary["measurements"].get(name, [])
        absent = [
            item
            for item in summary["checks"]
            if item["code"] == f"component.{name}.absent"
        ]
        if bool(measurements) != placed or len(absent) != (0 if placed else 1):
            raise ValueError(f"Render evidence contradicts the placed {name} component")
        for value in measurements:
            bounds(value)
            if name == "client" and value["client_id"] != identity["client_id"]:
                raise ValueError(
                    "Placed client evidence belongs to a different source row"
                )
    for check in summary["checks"]:
        bounds(check)
        bounds(check.get("measurements", {}))
        allowed = rules[check["code"]]["x-components"]
        component = check.get("component")
        if (allowed and component not in allowed) or (
            not allowed and component is not None
        ):
            raise ValueError("Render check names the wrong component")
        if check["code"].startswith("component."):
            if check["status"] != "not_applicable" or "page" in check:
                raise ValueError(
                    "An absent component must be reported as not applicable"
                )
        elif allowed and (not summary["components"][component] or "page" not in check):
            raise ValueError("Render check is missing its placed component or page")
