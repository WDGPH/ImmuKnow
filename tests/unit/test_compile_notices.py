"""Unit tests for compile_notices module - Typst compilation to PDF.

Tests cover:
- Typst file discovery
- Subprocess invocation with correct flags
- PDF output generation and path handling
- Error handling for compilation failures
- Configuration-driven behavior
- Font path and root directory handling

Real-world significance:
- Step 5 of pipeline: compiles Typst templates to PDF notices
- First time student notices become visible (PDF format)
- Compilation failures are a critical blocker
- Must handle Typst CLI errors gracefully
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from pipeline import compile_notices
import subprocess


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
    with patch("pipeline.compile_notices.subprocess.run", return_value=result):
        with pytest.raises(RuntimeError, match="Unsupported compiler"):
            compile_notices.check_compiler("typst")
