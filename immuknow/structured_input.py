"""Read JSON and YAML without silently replacing repeated fields."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import yaml
from yaml.nodes import MappingNode


def _distinct_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Repeated field: {key}")
        result[key] = value
    return result


def _finite_number(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("JSON numbers must be finite")
    return number


def parse_json(content: str | bytes, *, label: str = "JSON") -> Any:
    """Reject repeated fields and nonfinite numbers, including nested values."""
    try:
        if isinstance(content, bytes):
            content = content.decode("utf-8-sig")
        return json.loads(
            content,
            object_pairs_hook=_distinct_fields,
            parse_constant=_finite_number,
            parse_float=_finite_number,
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"{label}: {exc}") from None


def read_json(path: Path) -> Any:
    return parse_json(path.read_bytes(), label=path.name)


class _UniqueFieldsLoader(yaml.SafeLoader):
    def __init__(self, stream: str | bytes):
        self._active_merges: set[int] = set()
        super().__init__(stream)

    def flatten_mapping(self, node: MappingNode) -> None:
        if id(node) in self._active_merges:
            raise ValueError("YAML merges cannot refer back to their containing value")
        self._active_merges.add(id(node))
        try:
            super().flatten_mapping(node)
        finally:
            self._active_merges.remove(id(node))

    def construct_mapping(self, node: MappingNode, deep: bool = False) -> dict:
        # Flatten first so a merge cannot hide a repeated field.
        self.flatten_mapping(node)
        pairs = []
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise ValueError(
                    f"Field names must be strings (line {key_node.start_mark.line + 1})"
                )
            pairs.append((key, self.construct_object(value_node, deep=deep)))
        return _distinct_fields(pairs)


def _check_yaml_values(value: Any, active: set[int]) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("YAML numbers must be finite")
    if not isinstance(value, (dict, list)):
        return
    if id(value) in active:
        raise ValueError("YAML aliases cannot refer back to their containing value")
    active.add(id(value))
    for child in value.values() if isinstance(value, dict) else value:
        _check_yaml_values(child, active)
    active.remove(id(value))


def parse_yaml(content: str | bytes, *, label: str) -> Any:
    """Read safe YAML; errors identify fields or lines without copying input values."""
    try:
        value = yaml.load(content, Loader=_UniqueFieldsLoader)
        _check_yaml_values(value, set())
        return value
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        location = f" at line {mark.line + 1}" if mark is not None else ""
        raise ValueError(f"{label}: invalid YAML{location}") from None
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"{label}: {exc}") from None
