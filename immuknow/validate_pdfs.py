"""Inspect saved PDF bytes and identity; Typst owns all layout calculations."""

from __future__ import annotations

import hashlib
import re
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from pypdf.generic import DictionaryObject, TextStringObject

from .data_models import CheckResult, RenderJob


def check_qr_destinations(summary: dict[str, Any] | None) -> CheckResult:
    """Check recorded QR web addresses without contacting their destinations."""
    urls = summary["qr_urls"] if summary else []
    invalid = 0
    for url in urls:
        try:
            parts = urlsplit(url)
            host = (parts.hostname or "").encode("idna").decode("ascii")
            host_valid = ":" in host or all(
                re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label)
                for label in host.rstrip(".").split(".")
            )
            valid = (
                parts.scheme in ("http", "https")
                and host_valid
                and (parts.port is None or 0 < parts.port <= 65535)
                and not any(
                    char.isspace() or ord(char) < 32 or char in '\\<>"^`{|}\x7f'
                    for char in url
                )
                and not re.search(r"%(?![0-9a-fA-F]{2})", url)
            )
        except (ValueError, UnicodeError):
            valid = False
        invalid += not valid
    if summary is None:
        status, message = "not_run", "QR destinations could not be checked."
    elif not urls:
        status, message = "not_applicable", "No QR code was placed."
    elif invalid:
        status, message = (
            "warn",
            "Use complete HTTP or HTTPS web addresses for QR destinations; check hosts, ports, spaces and percent escapes.",
        )
    else:
        status, message = "pass", "QR destinations have HTTP or HTTPS web addresses."
    return CheckResult(
        "output.qr_destination",
        "output",
        status,
        message,
        measurements={"checked": len(urls), "invalid": invalid},
    )


def check_pdf_evidence(
    reader: PdfReader, summary: dict[str, Any] | None, identity: dict[str, str]
) -> list[CheckResult]:
    """Compare PDF evidence and find destinations outside the supplied helpers."""
    unchecked_links = CheckResult(
        "output.unrecorded_link",
        "output",
        "not_run",
        "PDF link destinations could not be compared with the supplied helpers.",
    )
    if summary is None:
        return [
            CheckResult(
                "output.evidence_matches",
                "output",
                "fail",
                "Render checks could not be completed; inspect this original PDF.",
            ),
            unchecked_links,
        ]
    destinations = set()
    links = summary["measurements"].get("link", [])
    expected = {url.encode("utf-8") for url in summary["qr_urls"]} | {
        link["url"].encode("utf-8") for link in links
    }
    checked = unrecorded = 0
    try:
        for number, page in enumerate(reader.pages, 1):
            for reference in page.annotations or []:
                annotation = reference.get_object()
                if not isinstance(annotation, DictionaryObject):
                    raise ValueError("Invalid PDF annotation")
                if annotation.get("/Subtype") != "/Link" or "/A" not in annotation:
                    continue
                action = annotation["/A"]
                if not isinstance(action, DictionaryObject):
                    raise ValueError("Invalid PDF link action")
                if action.get("/S") != "/URI":
                    continue
                destination = action.get("/URI")
                if isinstance(destination, bytes):
                    values = {destination}
                elif isinstance(destination, str):
                    values = {destination.encode("utf-8")}
                    if isinstance(destination, TextStringObject):
                        # Typst writes URI text as UTF-8 bytes; PDF text decoding
                        # can interpret those bytes as a different character set.
                        values.add(destination.original_bytes)
                else:
                    raise ValueError("Invalid PDF link destination")
                destinations.update((number, value) for value in values)
                checked += 1
                unrecorded += not bool(values & expected)
    except (PdfReadError, ValueError, KeyError):
        return [
            CheckResult(
                "output.evidence_matches",
                "output",
                "fail",
                "PDF links could not be checked against the recorded destinations.",
            ),
            unchecked_links,
        ]
    missing = {url.encode("utf-8") for url in summary["qr_urls"]} - {
        url for _, url in destinations
    }
    missing_links = {
        (link["page"], link["url"].encode("utf-8")) for link in links
    } - destinations
    matches = (
        summary["page_count"] == len(reader.pages)
        and summary["identity"] == identity
        and not missing
        and not missing_links
    )
    return [
        CheckResult(
            "output.evidence_matches",
            "output",
            "pass" if matches else "fail",
            "PDF page count, document identity and link destinations agree with render evidence."
            if matches
            else "PDF page count, selected identity or link destinations disagree with render evidence.",
            measurements={
                "pdf_page_count": len(reader.pages),
                "evidence_page_count": summary["page_count"],
                "missing_qr_links": len(missing),
                "missing_links": len(missing_links),
            },
        ),
        CheckResult(
            "output.unrecorded_link",
            "output",
            "warn" if unrecorded else "pass" if checked else "not_applicable",
            "A PDF link destination was not recorded by a supplied helper; use notice-link for external links."
            if unrecorded
            else "PDF link destinations are recorded by supplied helpers."
            if checked
            else "No external PDF links were placed.",
            measurements={"checked_links": checked, "unrecorded_links": unrecorded},
        ),
    ]


def check_client_identity(
    reader: PdfReader, summary: dict[str, Any] | None, client_id: str
) -> CheckResult:
    """Check personal text inside the supplied client and address PDF areas."""
    ids = summary["measurements"].get("client", []) if summary else []
    addresses = summary["measurements"].get("address", []) if summary else []
    regions = ids + addresses
    observed: list[list[str]] = [[] for _ in regions]
    try:
        for number, page in enumerate(reader.pages, 1):
            placed = [
                (index, area)
                for index, area in enumerate(regions)
                if area["page"] == number
            ]
            if placed and (page.rotation or page.user_unit != 1):
                raise ValueError(
                    "Personal content positions cannot be checked on transformed PDF pages"
                )
            width, height = float(page.mediabox.width), float(page.mediabox.height)
            for _, area in placed:
                if not (
                    0 <= area["x_pt"] < area["x_pt"] + area["width_pt"] <= width
                    and 0 <= area["y_pt"] < area["y_pt"] + area["height_pt"] <= height
                ):
                    raise ValueError(
                        "Personal content area is empty or outside the PDF page"
                    )

            unsupported = False

            def collect(text, cm, tm, _font, _size):
                nonlocal unsupported
                if not text:
                    return
                x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4] - float(page.mediabox.left)
                y = float(page.mediabox.top) - (tm[4] * cm[1] + tm[5] * cm[3] + cm[5])
                for index, area in placed:
                    # Typst and PDF numbers round independently; allow a quarter point.
                    if (
                        area["x_pt"] - 0.25
                        <= x
                        <= area["x_pt"] + area["width_pt"] + 0.25
                        and area["y_pt"] - 0.25
                        <= y
                        <= area["y_pt"] + area["height_pt"] + 0.25
                    ):
                        matrix = (
                            tm[0] * cm[0] + tm[1] * cm[2],
                            tm[0] * cm[1] + tm[1] * cm[3],
                            tm[2] * cm[0] + tm[3] * cm[2],
                            tm[2] * cm[1] + tm[3] * cm[3],
                        )
                        if text.strip() and any(
                            abs(value - expected) > 0.000001
                            for value, expected in zip(matrix, (1, 0, 0, 1))
                        ):
                            unsupported = True
                        observed[index].append(text)

            page.extract_text(visitor_text=collect)
            if unsupported:
                raise ValueError("Personal content text is rotated or scaled")
    except (PdfReadError, ValueError, KeyError) as exc:
        return CheckResult(
            "output.client_identity",
            "output",
            "fail",
            f"PDF text could not be checked: {exc}",
        )
    matches = (
        bool(client_id and ids)
        and all(area["client_id"] == client_id for area in ids)
        and all(
            " ".join("".join(parts).split()) == " ".join(area["text"].split())
            for area, parts in zip(regions, observed)
        )
    )
    return CheckResult(
        "output.client_identity",
        "output",
        "pass" if matches else "fail",
        "Placed client details and mailing addresses match the notice data."
        if matches
        else "Client details or a mailing address are missing or differ in the PDF.",
        measurements={"client_blocks": len(ids), "address_blocks": len(addresses)},
    )


def inspect_notice(
    job: RenderJob, run_dir: Path, summary: dict[str, Any] | None
) -> tuple[dict[str, Any], list[CheckResult]]:
    """Inspect actual original bytes; Typst alone owns layout measurements.

    A readable PDF remains an output even if its text or render evidence cannot
    be checked. Identity requires the exact expected value inside each supplied client
    block; an incidental phone number cannot satisfy it.
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
    checks.extend(
        check_pdf_evidence(
            reader,
            summary,
            {
                "row_key": job.sequence,
                "template": job.template.name,
                "client_id": job.client_id,
                "version_id": job.version_id,
                "language": job.language,
            },
        )
    )
    checks.append(check_client_identity(reader, summary, job.client_id))
    checks.append(check_qr_destinations(summary))
    return original, checks
