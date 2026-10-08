"""Prepare localized notice JSON and stage maintained Typst templates once per run.

The prepared client list supplies every resolved version and language. The render-job
manifest maps each client to its unchanged template, JSON input, and expected PDF.
All writes stay in the caller's output directory. Document source belongs to Typst.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from dataclasses import asdict
from datetime import date
from importlib.resources import files
from pathlib import Path
from typing import Any

from .data_models import ClientRecord, RenderJob
from .notice_versioning import Language, validate_version_id

LOG = logging.getLogger(__name__)

TRANSLATION_DOMAINS = ("diseases_chart", "diseases_overdue")


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
    clients: list[ClientRecord],
    artifact_dir: Path,
    template_dir: Path,
    config: dict[str, Any],
    config_dir: Path,
    run_id: str,
    pdf_dir: Path | None = None,
) -> list[RenderJob]:
    """Write notice JSON and a job manifest under the caller's output directory.

    Parameters
    ----------
    clients : list[ClientRecord]
        Prepared client list with resolved notice assignments.
    artifact_dir : Path
        Writable output directory for the bounded render workspace and manifest.
    template_dir : Path
        Selected maintained template directory.
    config : dict
        Run-local resolved configuration.
    config_dir : Path
        Caller-selected configuration resources.
    run_id : str
        Identifier for this run.
    pdf_dir : Path, optional
        Expected PDF directory; defaults to a sibling ``pdf_individual`` directory.

    Returns
    -------
    list[RenderJob]
        One job per client in client sequence order. No Typst source is generated.
    """
    artifact_dir = artifact_dir.resolve()
    template_dir = template_dir.resolve()
    config_dir = config_dir.resolve()
    pdf_dir = (pdf_dir or artifact_dir.parent / "pdf_individual").resolve()
    workspace = artifact_dir / "render"
    reject_overlap(template_dir, workspace)
    reject_overlap(config_dir, workspace)
    if not template_dir.is_dir():
        raise FileNotFoundError(f"Notice template directory not found: {template_dir}")
    cutoff = config.get("date_data_cutoff")
    if cutoff not in (None, ""):
        if not isinstance(cutoff, str) or not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}", cutoff
        ):
            raise ValueError("date_data_cutoff must be an ISO calendar date")
        try:
            date.fromisoformat(cutoff)
        except ValueError as exc:
            raise ValueError(
                "date_data_cutoff must be a valid ISO calendar date"
            ) from exc

    packaged_translations = (
        Path(str(files("immuknow").joinpath("config"))) / "translations"
    )
    selected_translations: dict[str, Path] = {}
    for language in sorted(Language.all_codes()):
        for domain in TRANSLATION_DOMAINS:
            name = f"{language}_{domain}.json"
            selected = config_dir / "translations" / name
            if not selected.is_file():
                selected = packaged_translations / name
            if not selected.is_file():
                raise FileNotFoundError(
                    f"Notice translation resource not found: {name}"
                )
            selected_translations[name] = selected

    manifest_path = artifact_dir / "render_jobs.json"

    # Resolve every entry point before writing any notice payload.
    selections = []
    for client in clients:
        version_id = client.version_id
        if version_id is None:
            raise ValueError(
                f"Missing resolved version_id for client {client.client_id}"
            )
        template = select_template(template_dir, version_id, client.language)
        for label, value in (
            ("sequence", client.sequence),
            ("client ID", client.client_id),
        ):
            if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
                raise ValueError(f"Unsafe {label} for notice filename: {value!r}")
        selections.append((client, version_id, template.relative_to(template_dir)))

    # Copy once per run. Private template sets remain isolated from built-ins.
    manifest_path.unlink(missing_ok=True)
    (artifact_dir / "compilation.json").unlink(missing_ok=True)
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(
        template_dir,
        workspace / "templates",
        ignore=shutil.ignore_patterns("*.py", "__pycache__"),
        copy_function=shutil.copyfile,
    )
    # Installed resources can be read-only; run-local copies must remain removable.
    for directory in [workspace / "templates", *(workspace / "templates").rglob("*")]:
        if directory.is_dir():
            directory.chmod(0o755)
    (workspace / "data").mkdir()
    (workspace / "qr_codes").mkdir()
    (workspace / "translations").mkdir()
    for name, selected in selected_translations.items():
        shutil.copyfile(selected, workspace / "translations" / name)
    qr_enabled = config.get("qr", {}).get("enabled", False)
    jobs = []
    for client, version_id, relative_template in selections:
        notice = build_notice_data(client, config)
        notice.update(
            logo_path="/templates/assets/logo.png",
            signature_path="/templates/assets/signature.png",
        )
        if qr_enabled:
            qr_name = f"qr_code_{client.sequence}_{client.client_id}.png"
            qr_source = artifact_dir / "qr_codes" / qr_name
            if not qr_source.is_file():
                raise FileNotFoundError(f"Expected QR image is missing: {qr_source}")
            shutil.copy2(qr_source, workspace / "qr_codes" / qr_name)
            notice["client_data"]["qr_img"] = f"/qr_codes/{qr_name}"
        name = f"{client.language}_notice_{client.sequence}_{client.client_id}"
        data_path = workspace / "data" / f"{name}.json"
        data_path.write_text(
            json.dumps(notice, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        jobs.append(
            RenderJob(
                sequence=client.sequence,
                client_id=client.client_id,
                language=client.language,
                version_id=version_id,
                workspace=workspace,
                template=workspace / "templates" / relative_template,
                data=data_path,
                pdf=pdf_dir / f"{name}.pdf",
            )
        )
    manifest_path.write_text(
        json.dumps(
            {
                "run_id": run_id,
                "total_clients": len(clients),
                "jobs": [asdict(job) for job in jobs],
            },
            default=str,
            indent=2,
        ),
        encoding="utf-8",
    )
    return jobs


def build_notice_data(client: ClientRecord, config: dict[str, Any]) -> dict[str, Any]:
    """Supply prepared client data and the resolved assignment to one notice."""
    client_data: dict[str, Any] = {
        "name": " ".join(
            filter(None, [client.person["first_name"], client.person["last_name"]])
        ).strip(),
        "address": client.contact["street"],
        "city": client.contact["city"],
        "postal_code": client.contact["postal_code"],
        "date_of_birth_iso": client.person["date_of_birth_iso"],
        "school": client.school["name"],
        "over_16": client.person["over_16"],
    }
    if client.qr and client.qr.get("payload"):
        client_data["qr_url"] = client.qr["payload"]
    preprocess_config = config.get("preprocess", {})
    return {
        "version_id": client.version_id,
        "language": client.language,
        "client_id": client.client_id,
        "client_data": client_data,
        "date_data_cutoff_iso": config.get("date_data_cutoff") or "",
        "overdue_diseases": client.overdue_diseases or [],
        "overdue_agents": client.overdue_agents or [],
        "include_dose": bool(preprocess_config.get("include_dose", False)),
        "received": client.received or [],
        "chart_diseases": config.get("chart_diseases_header", []),
        "show_validity_markers": bool(
            preprocess_config.get("show_validity_markers", False)
        ),
    }
