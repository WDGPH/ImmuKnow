"""Prepare localized notice JSON and stage maintained Typst templates once per run.

The canonical cohort supplies every resolved version and language. The render-job
manifest maps each client to its unchanged template, JSON input, and expected PDF.
All writes stay in the caller's output directory. Document source belongs to Typst.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import shutil
from dataclasses import asdict
from importlib.resources import files
from pathlib import Path
from typing import Dict, List

from .config_loader import load_config
from .data_models import (
    ArtifactPayload,
    ClientRecord,
    RenderJob,
)
from .enums import Language
from .notice_versioning import validate_version_id
from .preprocess import format_iso_date_for_language
from .translation_helpers import display_label
from .utils import deserialize_client_record

LOG = logging.getLogger(__name__)

_DOSE_LABEL_PATTERN = re.compile(
    r"^(?P<disease>.+) \((?P<dose_label>(?P<number>\d+)(?:st|nd|rd|th) dose)\)$"
)

LEGACY_VERSION = "legacy_overdue_v1"


def select_template(template_dir: Path, version_id: str, language: str) -> Path:
    """Select a native entry point without language or PHU fallback.

    Parameters
    ----------
    template_dir : Path
        Selected built-in or custom template directory.
    version_id : str
        Resolved notice identity; legacy fixed notices use ``legacy_overdue_v1``.
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
        old_directory = (
            template_dir if version_id == LEGACY_VERSION else template_dir / version_id
        )
        legacy = old_directory / f"{language}_template.py"
        migration = (
            f" Migrate {legacy.name} to a static .typ template using the template authoring guide."
            if legacy.exists()
            else " No language or PHU fallback is applied."
        )
        raise FileNotFoundError(f"Notice template not found: {template}.{migration}")
    return template


def prepare_render_jobs(
    artifact_path: Path,
    artifact_dir: Path,
    template_dir: Path | None = None,
    config_path: Path | None = None,
    pdf_dir: Path | None = None,
) -> list[RenderJob]:
    """Write notice JSON and a job manifest under the caller's output directory.

    Parameters
    ----------
    artifact_path : Path
        Canonical preprocessed cohort.
    artifact_dir : Path
        Writable output directory for the bounded render workspace and manifest.
    template_dir : Path, optional
        Isolated custom template directory, or packaged templates when omitted.
    config_path : Path, optional
        Caller-selected parameters used to prepare display data.
    pdf_dir : Path, optional
        Expected PDF directory; defaults to a sibling ``pdf_individual`` directory.

    Returns
    -------
    list[RenderJob]
        One job per client in canonical sequence order. No Typst source is generated.
    """
    payload = read_artifact(artifact_path)
    artifact_dir = artifact_dir.resolve()
    template_dir = (template_dir or Path(str(files("templates")))).resolve()
    pdf_dir = (pdf_dir or artifact_dir.parent / "pdf_individual").resolve()
    workspace = artifact_dir / "render"
    manifest_path = artifact_dir / "render_jobs.json"
    manifest_path.unlink(missing_ok=True)
    (artifact_dir / "compilation.json").unlink(missing_ok=True)

    # Resolve every entry point before writing any notice payload.
    selections = []
    for client in payload.clients:
        resolved = client.metadata["resolved_notice"]
        version_id = resolved["version_id"]
        if resolved["language"] != client.language:
            raise ValueError(
                f"Conflicting resolved language for client {client.client_id}"
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
    qr_enabled = load_config(config_path).get("qr", {}).get("enabled", False)
    jobs = []
    for client, version_id, relative_template in selections:
        notice = build_notice_data(client, config_path=config_path)
        notice.update(
            version_id=version_id,
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
                "run_id": payload.run_id,
                "total_clients": len(payload.clients),
                "jobs": [asdict(job) for job in jobs],
            },
            default=str,
            indent=2,
        ),
        encoding="utf-8",
    )
    return jobs


def read_render_jobs(
    artifact_dir: Path, *, require_compiled: bool = False
) -> list[RenderJob]:
    """Read the explicit job list and, when requested, require all compiled outputs.

    Parameters
    ----------
    artifact_dir : Path
        Directory holding ``render_jobs.json``.
    require_compiled : bool
        Require successful completion of the whole compilation stage and every PDF.

    Returns
    -------
    list[RenderJob]
        Jobs in the recorded canonical order.

    Raises
    ------
    ValueError
        If the manifest loses or repeats an expected notice.
    FileNotFoundError
        If compilation evidence or an expected PDF is absent.
    """
    manifest = json.loads(
        (artifact_dir / "render_jobs.json").read_text(encoding="utf-8")
    )
    jobs = []
    for raw in manifest["jobs"]:
        for field in ("workspace", "template", "data", "pdf"):
            raw[field] = Path(raw[field])
        jobs.append(RenderJob(**raw))
    if len(jobs) != manifest["total_clients"] or len({job.pdf for job in jobs}) != len(
        jobs
    ):
        raise ValueError(
            "Render jobs must account for every expected notice exactly once"
        )
    if require_compiled:
        evidence = json.loads(
            (artifact_dir / "compilation.json").read_text(encoding="utf-8")
        )
        if evidence["outputs"] != [str(job.pdf) for job in jobs]:
            raise ValueError("Compilation evidence does not match the expected notices")
        for job in jobs:
            if not job.pdf.is_file():
                raise FileNotFoundError(f"Expected notice PDF is missing: {job.pdf}")
    return jobs


def read_artifact(path: Path) -> ArtifactPayload:
    """Read and deserialize the preprocessed artifact JSON.

    **Input Contract:** Assumes artifact was created by preprocessing step and
    contains valid client records. Does not validate client schema; relies on
    preprocessing to have ensured data quality.

    Parameters
    ----------
    path : Path
        Path to the preprocessed artifact JSON file.

    Returns
    -------
    ArtifactPayload
        Parsed artifact with clients and metadata.

    Raises
    ------
    FileNotFoundError
        If artifact file does not exist.
    ValueError
        If artifact is not valid JSON.
    KeyError
        If artifact is missing required fields.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Preprocessed artifact not found: {path}. "
            "Ensure preprocessing step has completed."
        )

    try:
        payload_dict = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Preprocessed artifact is not valid JSON: {path}") from exc

    clients = []

    for client_dict in payload_dict["clients"]:
        client = deserialize_client_record(client_dict)
        clients.append(client)

    return ArtifactPayload(
        run_id=payload_dict["run_id"],
        language=payload_dict["language"],
        clients=clients,
        warnings=payload_dict.get("warnings", []),
        created_at=payload_dict.get("created_at", ""),
        total_clients=payload_dict.get("total_clients", len(clients)),
        assignment_mode=payload_dict.get("assignment_mode", "fixed"),
        default_version=payload_dict.get("default_version"),
    )


def load_and_translate_chart_diseases(
    language: str, config_path: Path | None = None
) -> List[str]:
    """Load and translate the chart disease list from configuration.

    Loads chart_diseases_header from config/parameters.yaml and translates each
    disease name to the target language using the diseases_chart translation domain.
    This ensures chart column headers match the configured set of diseases and are
    properly localized.

    Parameters
    ----------
    language : str
        Language code (e.g., "en", "fr").
    config_path : Path, optional
        Path to ``parameters.yaml``. Defaults to the repository configuration.

    Returns
    -------
    List[str]
        List of translated disease names in order.
    """
    config = load_config(config_path)
    chart_diseases_header = config.get("chart_diseases_header", [])

    translated_diseases: List[str] = []
    for disease in chart_diseases_header:
        label = display_label(
            "diseases_chart",
            disease,
            language,
            strict=False,
            config_dir=config_path.parent if config_path else None,
        )
        translated_diseases.append(label)

    return translated_diseases


def _localize_vaccine_due_label(
    label: str, language: str, config_dir: Path | None = None
) -> str:
    """Localize a canonical overdue disease label and optional dose suffix.

    Preprocessing stores dose-specific entries in the stable English form
    ``<disease> (<ordinal> dose)``. Translate the disease and generated suffix
    separately so that the composite label does not miss the exact disease
    translation lookup.

    Parameters
    ----------
    label : str
        Canonical overdue disease label, optionally with a dose suffix.
    language : str
        Language code for the notice.

    Returns
    -------
    str
        Localized overdue disease and dose label.
    """
    match = _DOSE_LABEL_PATTERN.fullmatch(label)
    if match is None:
        return display_label(
            "diseases_overdue", label, language, strict=False, config_dir=config_dir
        )

    disease = display_label(
        "diseases_overdue",
        match.group("disease"),
        language,
        strict=False,
        config_dir=config_dir,
    )
    number = match.group("number")
    if language == "fr":
        ordinal = f"{number}{'re' if number == '1' else 'e'}"
        return f"{disease} ({ordinal} dose)"

    # Preserve the artifact's established English suffix for English and any
    # unsupported language that reaches this already validated rendering path.
    return f"{disease} ({match.group('dose_label')})"


def build_notice_data(
    client: ClientRecord,
    config_path: Path | None = None,
) -> dict:
    """Prepare ordinary JSON values for a notice in its resolved language.

    Translates disease names in vaccines_due_list and received records to
    localized display strings using the configured translation files.
    Also loads and translates the chart disease header list from configuration.
    Formats the notice date_data_cutoff with locale-aware formatting using Babel.

    Parameters
    ----------
    client : ClientRecord
        Client record with all required fields.
    config_path : Path, optional
        Path to ``parameters.yaml``. Defaults to the repository configuration.

    Returns
    -------
    dict
        Ordinary JSON values with canonical ISO dates and localized display text.
    """
    config = load_config(config_path)
    preprocess_cfg: Dict[str, object] = config.get("preprocess", {})
    show_validity_markers = bool(preprocess_cfg.get("show_validity_markers", False))

    # Load and format date_data_cutoff for the client's language
    date_data_cutoff_iso = config.get("date_data_cutoff")
    if date_data_cutoff_iso:
        date_data_cutoff_formatted = format_iso_date_for_language(
            date_data_cutoff_iso, client.language
        )
    else:
        date_data_cutoff_formatted = ""

    client_data = {
        "name": " ".join(
            filter(None, [client.person["first_name"], client.person["last_name"]])
        ).strip(),
        "address": client.contact["street"],
        "city": client.contact["city"],
        "postal_code": client.contact["postal_code"],
        "date_of_birth": format_iso_date_for_language(
            client.person["date_of_birth_iso"], client.language
        )
        if client.person["date_of_birth_iso"]
        else "",
        "date_of_birth_iso": client.person["date_of_birth_iso"],
        "school": client.school["name"],
        "date_data_cutoff": date_data_cutoff_formatted,
        "over_16": client.person["over_16"],
    }

    if client.qr and client.qr.get("payload"):
        client_data["qr_url"] = client.qr["payload"]

    # Load and translate chart disease header
    chart_diseases_translated = load_and_translate_chart_diseases(
        client.language, config_path
    )

    # Translate vaccines_due_list to display labels
    vaccines_due_array_translated: List[str] = []
    if client.vaccines_due_list:
        for disease in client.vaccines_due_list:
            label = _localize_vaccine_due_label(
                disease, client.language, config_path.parent if config_path else None
            )
            vaccines_due_array_translated.append(label)

    # Translate vaccines_due string
    vaccines_due_str_translated = (
        ", ".join(vaccines_due_array_translated)
        if vaccines_due_array_translated
        else ""
    )

    # Agent list requires no translation — pass through as-is
    vaccines_due_agents_array = client.vaccines_due_agent_list or []
    vaccines_due_agents_str = ", ".join(vaccines_due_agents_array)

    # Translate received records' column keys
    received_translated: List[Dict[str, object]] = []
    if client.received:
        for record in client.received:
            translated_record = dict(record)
            if "columns" in translated_record and isinstance(
                translated_record["columns"], dict
            ):
                translated_record["columns"] = {
                    display_label(
                        "diseases_chart",
                        disease,
                        client.language,
                        strict=False,
                        config_dir=config_path.parent if config_path else None,
                    ): status
                    for disease, status in translated_record["columns"].items()
                }
            received_translated.append(translated_record)

    return {
        "language": client.language,
        "client_row": [client.client_id],
        "client_data": client_data,
        "date_data_cutoff_iso": date_data_cutoff_iso,
        "vaccines_due_str": vaccines_due_str_translated,
        "vaccines_due_array": vaccines_due_array_translated,
        "vaccines_due_agents_str": vaccines_due_agents_str,
        "vaccines_due_agents_array": vaccines_due_agents_array,
        "received": received_translated,
        "num_rows": len(received_translated),
        "chart_diseases_translated": chart_diseases_translated,
        "show_validity_markers": show_validity_markers,
    }


if __name__ == "__main__":
    import sys

    print(
        "⚠️  Direct invocation: This module is typically executed via orchestrator.py.\n"
        "   Re-running a single step is valid when pipeline artifacts are retained on disk,\n"
        "   allowing you to skip earlier steps and regenerate output.\n"
        "   Note: Output will overwrite any previous files.\n"
        "\n"
        "   For typical usage, run: uv run viper <input> <language>\n",
        file=sys.stderr,
    )
    sys.exit(1)
