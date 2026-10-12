"""Inspect saved PDF bytes and identity; Typst owns all layout calculations."""

from __future__ import annotations

import hashlib
import re
from io import BytesIO
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .data_models import CheckResult, RenderJob


def inspect_notice(
    job: RenderJob, run_dir: Path, summary: dict[str, Any] | None
) -> tuple[dict[str, Any], list[CheckResult]]:
    """Inspect actual original bytes; Typst alone owns layout measurements.

    A readable PDF remains an output even if its text or render evidence cannot
    be checked. Identity requires the labelled client block and exact expected
    value; an incidental phone number cannot satisfy it.
    """
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
    if summary is None:
        checks.append(
            CheckResult(
                "output.evidence_unavailable",
                "output",
                "warn",
                "Render checks could not be completed; inspect this original PDF.",
            )
        )
    else:
        expected_identity = {
            "client_id": job.client_id,
            "version_id": job.version_id,
            "language": job.language,
        }
        matches = (
            summary["page_count"] == pages and summary["identity"] == expected_identity
        )
        checks.append(
            CheckResult(
                "output.evidence_matches",
                "output",
                "pass" if matches else "fail",
                "PDF page count and document identity agree with render evidence."
                if matches
                else "PDF page count or selected identity disagrees with render evidence.",
                measurements={
                    "pdf_page_count": pages,
                    "evidence_page_count": summary["page_count"],
                },
            )
        )
        if not matches:
            checks.append(
                CheckResult(
                    "output.evidence_mismatch",
                    "output",
                    "warn",
                    "The rendered evidence does not match this original notice.",
                )
            )
    try:
        texts = [" ".join(page.extract_text().split()) for page in reader.pages]
    except (PdfReadError, ValueError, KeyError) as exc:
        checks.extend(
            [
                CheckResult(
                    "output.text_readable",
                    "output",
                    "fail",
                    f"PDF text inspection failed: {exc}",
                ),
                CheckResult(
                    "output.evidence_unavailable",
                    "output",
                    "warn",
                    "Visible client identity could not be checked.",
                ),
            ]
        )
        return original, checks
    expected_id = " ".join(job.client_id.split())
    pattern = re.compile(
        r"(?:Client ID|Identifiant du client)\s*:\s*"
        + re.escape(expected_id)
        + r"(?![\w-])"
    )
    found_page = next(
        (
            index
            for index, text in enumerate(texts, 1)
            if expected_id and pattern.search(text)
        ),
        None,
    )
    checks.append(
        CheckResult(
            "output.client_identity",
            "output",
            "pass" if found_page else "warn",
            "Labelled client ID matches the selected source row."
            if found_page
            else "The exact client ID is missing from the labelled client block.",
            page=found_page,
        )
    )
    return original, checks
