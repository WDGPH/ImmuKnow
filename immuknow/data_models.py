"""Records shared across notice preparation, rendering, and delivery."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal


@dataclass(frozen=True)
class RenderJob:
    """Map one prepared client to its static template, JSON input, and PDF.

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
    creation_timestamp: int = 0


@dataclass(frozen=True)
class ClientRecord:
    """Prepared client data and one resolved language/version assignment.

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
    metadata: dict[str, Any]
    version_id: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    validity_coverage: str = "all_absent"
    unparsed_history: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PreprocessResult:
    """Prepared facts and all source findings, including failures that reject input."""

    clients: list[ClientRecord]
    warnings: list[str]
    row_checks: dict[str, list[CheckResult]] = field(default_factory=dict)
    source_rows: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class PDFRecord:
    """One validated PDF and its source client for bundling."""

    sequence: str
    client_id: str
    pdf_path: Path
    page_count: int
    client: ClientRecord


CheckStatus = Literal["pass", "warn", "fail", "not_applicable", "not_run"]


@dataclass(frozen=True)
class CheckResult:
    """One source, rendering, or output check; warnings preserve useful PDFs."""

    code: str
    stage: str
    status: CheckStatus
    message: str
    component: str | None = None
    page: int | None = None
    measurements: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the shared Typst/Python shape without inapplicable fields."""
        return {key: value for key, value in asdict(self).items() if value is not None}
