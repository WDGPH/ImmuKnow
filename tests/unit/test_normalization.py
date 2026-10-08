"""Tests for run-scoped source disease normalization."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from immuknow.preprocess import load_normalization, normalize_disease


@pytest.mark.unit
def test_selected_normalization_resource_is_used_per_run(tmp_path: Path) -> None:
    path = tmp_path / "disease_normalization.json"
    path.write_text(json.dumps({"Raw": "First"}), encoding="utf-8")
    first = load_normalization(path)
    path.write_text(json.dumps({"Raw": "Second"}), encoding="utf-8")
    second = load_normalization(path)

    assert normalize_disease(" Raw ", first) == "First"
    assert normalize_disease(" Raw ", second) == "Second"
    assert normalize_disease("Other", second) == "Other"


@pytest.mark.unit
@pytest.mark.parametrize("invalid", [[], {"Raw": 1}, {"Raw": ["Configured"]}])
def test_malformed_normalization_resource_fails(
    tmp_path: Path, invalid: object
) -> None:
    path = tmp_path / "disease_normalization.json"
    path.write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(ValueError, match="string mapping"):
        load_normalization(path)
