"""Record the readable original PDF artifact."""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .data_models import CheckResult, RenderJob


def inspect_notice(
    job: RenderJob, run_dir: Path
) -> tuple[dict[str, Any], list[CheckResult]]:
    """Record the hash and page count of a readable original PDF."""
    content = job.pdf.read_bytes()
    reader = PdfReader(BytesIO(content))
    pages = len(reader.pages)
    if not pages:
        raise PdfReadError("Compiled notice PDF contains no pages")
    original = {
        "status": "completed",
        "path": job.pdf.relative_to(run_dir).as_posix(),
        "sha256": hashlib.sha256(content).hexdigest(),
        "pages": pages,
    }
    checks = [
        CheckResult(
            "output.readable",
            "output",
            "pass",
            "Original PDF is readable.",
            measurements={"page_count": pages},
        )
    ]
    return original, checks
