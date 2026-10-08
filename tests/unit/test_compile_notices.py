"""Compiler discovery and pinned-version diagnostics."""

from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from pipeline import compile_notices


@pytest.mark.unit
def test_missing_compiler_has_installation_guidance() -> None:
    """An unavailable executable should explain the supported selection routes."""
    with pytest.raises(RuntimeError, match="Install Typst 0.15.1.*TYPST_BIN"):
        compile_notices.check_compiler("/missing/typst")


@pytest.mark.unit
@pytest.mark.parametrize("version", ["0.14.2", "0.15.0", "0.16.0-rc1"])
def test_unsupported_compiler_is_rejected(version: str) -> None:
    """Older compilers and untested prereleases must fail before notice compilation."""
    result = subprocess.CompletedProcess([], 0, stdout=f"typst {version} (test)")
    with (
        patch("pipeline.compile_notices.subprocess.run", return_value=result),
        pytest.raises(RuntimeError, match="Unsupported compiler"),
    ):
        compile_notices.check_compiler("typst")
