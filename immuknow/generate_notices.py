"""Stage authored project resources and row-keyed factual inputs in the run workspace."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .data_models import ClientRecord, RenderJob
from .render_payload import validate_render_payload
from .version_notices import Language, validate_version_id


def reject_overlap(source: Path, destination: Path) -> None:
    """Reject source overlap, including nested links followed during template copying."""
    source = source.resolve()
    destination = destination.resolve()
    candidates = [source]
    if source.is_dir():
        candidates.extend(
            path.resolve() for path in source.rglob("*") if path.is_symlink()
        )
    for candidate in candidates:
        if candidate.is_relative_to(destination) or destination.is_relative_to(
            candidate
        ):
            raise ValueError(
                f"Selected source {candidate} overlaps output workspace {destination}"
            )


def select_template(template_dir: Path, version_id: str, language: str) -> Path:
    """Select a native entry point without language or PHU fallback.

    Parameters
    ----------
    template_dir : Path
        Selected built-in or custom template directory.
    version_id : str
        Resolved notice identity from the catalog and assignment manifest.
    language : str
        Resolved notice language.

    Returns
    -------
    Path
        Existing maintained entry point.

    Raises
    ------
    ValueError
        If language or version cannot safely identify a template.
    FileNotFoundError
        If the selected template has not been authored or migrated.
    """
    Language.from_string(language)
    validate_version_id(version_id)
    template = template_dir / f"{version_id}.{language}.typ"
    if not template.is_file():
        raise FileNotFoundError(f"Notice template not found: {template}")
    return template


def prepare_render_jobs(
    clients: list[ClientRecord], run_dir: Path, config: dict[str, Any]
) -> list[RenderJob]:
    """Write row-keyed facts against the immutable project already staged by the run."""
    workspace = run_dir.resolve()
    template_dir = workspace / "resources" / "templates"
    facts = workspace / "facts"
    facts.mkdir(exist_ok=True)
    jobs = []
    for client in clients:
        if client.version_id is None:
            raise ValueError(f"Source row {client.sequence} has no resolved notice")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", client.sequence):
            raise ValueError(f"Unsafe source row key: {client.sequence!r}")
        template = select_template(template_dir, client.version_id, client.language)
        notice = build_notice_data(client, config)
        validate_render_payload(notice)
        data_path = facts / f"{client.sequence}.json"
        data_path.write_text(
            json.dumps(notice, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        jobs.append(
            RenderJob(
                sequence=client.sequence,
                client_id=client.client_id,
                language=client.language,
                version_id=client.version_id,
                workspace=workspace,
                template=template,
                data=data_path,
                pdf=workspace / "originals" / f"{client.sequence}.pdf",
                creation_timestamp=int(config.get("creation_timestamp", 0)),
            )
        )
    return jobs


def build_notice_data(client: ClientRecord, config: dict[str, Any]) -> dict[str, Any]:
    """Supply facts and trusted selected identity; display and QR choices belong to Typst."""
    return {
        "schema_version": 1,
        "row_key": client.sequence,
        "client_id": client.client_id,
        "template": f"{client.version_id}.{client.language}.typ",
        "version_id": client.version_id,
        "language": client.language,
        "client_data": {
            "name": " ".join(
                filter(None, [client.person["first_name"], client.person["last_name"]])
            ).strip(),
            "first_name": client.person["first_name"],
            "last_name": client.person["last_name"],
            "address": client.contact["street"],
            "city": client.contact["city"],
            "province": client.contact["province"],
            "postal_code": client.contact["postal_code"],
            "date_of_birth_iso": client.person["date_of_birth_iso"],
            "age": client.person["age"],
            "over_16": client.person["over_16"],
            "school": client.school["name"],
        },
        "school": client.school,
        "board": client.board,
        "date_of_delivery": config.get("date_of_delivery") or "",
        "date_as_of": config.get("date_as_of") or "",
        "overdue_diseases": client.overdue_diseases,
        "overdue_agents": client.overdue_agents,
        "history": client.history,
        "validity_coverage": client.validity_coverage,
        "unparsed_history": client.unparsed_history,
    }
