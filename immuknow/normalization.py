"""Canonical disease normalization used when reading source data."""

from __future__ import annotations

import json
from pathlib import Path


def load_normalization(path: Path) -> dict[str, str]:
    """Read the selected normalization resource for one pipeline run."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in data.items()
    ):
        raise ValueError(f"Disease normalization must be a string mapping: {path}")
    return data


def normalize_disease(token: str, normalization: dict[str, str]) -> str:
    """Map a raw disease label to its canonical identifier."""
    token = token.strip()
    return normalization.get(token, token)
