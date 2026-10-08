"""Encrypt the compiled notice cohort with passwords from canonical client data.

Render jobs identify every expected PDF. Encryption failures halt this optional
stage, leaving its unencrypted input available for diagnosis or rerun.
"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter

from .config_loader import load_config
from .enums import TemplateField
from .generate_notices import read_artifact, read_render_jobs
from .utils import build_client_context, validate_and_format_template


def encrypt_pdf(file_path: str, context: dict, *, config: dict | None = None) -> str:
    """Encrypt a PDF with a password derived from client context.

    Parameters
    ----------
    file_path : str
        Path to the PDF file to encrypt.
    context : dict
        Template context dict with client metadata (from build_client_context).
        Must contain fields referenced in the password template.

    Returns
    -------
    str
        Path to the encrypted PDF file with _encrypted suffix.

    Raises
    ------
    ValueError
        If password template references missing fields or is invalid.
    """
    if config is None:
        config = load_config().get("encryption", {})
    password_config = config.get("password", {})
    template = password_config.get("template", "{date_of_birth_iso_compact}")

    try:
        password = validate_and_format_template(
            template, context, allowed_fields=TemplateField.all_values()
        )
    except (KeyError, ValueError) as e:
        raise ValueError(f"Invalid password template: {e}") from e

    reader = PdfReader(file_path, strict=False)
    writer = PdfWriter()

    # Use pypdf's standard append method
    writer.append(reader)

    if reader.metadata:
        writer.add_metadata(reader.metadata)

    writer.encrypt(user_password=password, owner_password=password)

    src = Path(file_path)
    encrypted_path = src.with_name(f"{src.stem}_encrypted{src.suffix}")
    with open(encrypted_path, "wb") as f:
        writer.write(f)

    return str(encrypted_path)


def encrypt_expected_notices(
    artifact_path: Path, artifact_dir: Path, config_path: Path
) -> list[Path]:
    """Encrypt exactly the compiled cohort, using its recorded client mapping.

    Parameters
    ----------
    artifact_path : Path
        Canonical client records for password preparation.
    artifact_dir : Path
        Render jobs and successful compilation evidence.
    config_path : Path
        Selected parameters, including the password format.

    Returns
    -------
    list[Path]
        Encrypted outputs in canonical order. Any failure halts the run.
    """
    clients = {
        (client.sequence, client.client_id): client
        for client in read_artifact(artifact_path).clients
    }
    jobs = read_render_jobs(artifact_dir, require_compiled=True)
    if {(job.sequence, job.client_id) for job in jobs} != set(clients):
        raise ValueError("Render jobs do not match the canonical cohort")
    config = load_config(config_path).get("encryption", {})
    outputs = []
    for job in jobs:
        client = clients[(job.sequence, job.client_id)]
        context = build_client_context(client)
        outputs.append(Path(encrypt_pdf(str(job.pdf), context, config=config)))
    return outputs
