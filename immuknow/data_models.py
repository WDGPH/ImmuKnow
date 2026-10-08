"""Records shared across notice preparation, rendering, and delivery."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RenderJob:
    """Map one canonical client to its static template, JSON input, and PDF.

    All paths are absolute filesystem paths. ``workspace`` bounds Typst reads;
    the compiler translates ``data`` into a path relative to that root.
    """

    sequence: str
    client_id: str
    language: str
    version_id: str
    workspace: Path
    template: Path
    data: Path
    pdf: Path


@dataclass(frozen=True)
class ClientRecord:
    """Canonical source facts and one resolved language/version assignment.

    ``person["date_of_birth_iso"]`` is an ISO date or empty when absent;
    Typst owns its display format. Overdue disease entries keep an optional
    numeric dose; invalid source doses also keep ``dose_raw``.
    """

    sequence: str
    client_id: str
    language: str
    person: dict[str, Any]
    school: dict[str, Any]
    board: dict[str, Any]
    contact: dict[str, Any]
    overdue_diseases: list[dict[str, object]]
    overdue_agents: list[str]
    received: Sequence[dict[str, object]] | None
    metadata: dict[str, Any]
    qr: dict[str, Any] | None = None
    version_id: str | None = None


@dataclass(frozen=True)
class PreprocessResult:
    """Canonical cohort and nonfatal source warnings."""

    clients: list[ClientRecord]
    warnings: list[str]


@dataclass(frozen=True)
class PdfRecord:
    """One validated PDF and its source client for bundling."""

    sequence: str
    client_id: str
    pdf_path: Path
    page_count: int
    client: ClientRecord
