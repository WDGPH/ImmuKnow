"""Encrypt the compiled notice cohort with passwords from prepared client data.

Render jobs identify every expected PDF. Encryption failures halt this optional
stage, leaving its unencrypted input available for diagnosis or rerun.
"""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter

from .compile_notices import check_expected_notices
from .data_models import ClientRecord, RenderJob
from .client_placeholders import (
    CLIENT_PLACEHOLDERS,
    build_client_context,
    validate_and_format_template,
)


def encrypt_pdf(file_path: str, context: dict, *, config: dict) -> str:
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
    password_config = config.get("password", {})
    template = password_config.get("template", "{date_of_birth_iso_compact}")

    try:
        password = validate_and_format_template(
            template, context, allowed_fields=CLIENT_PLACEHOLDERS
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
    clients: list[ClientRecord], jobs: list[RenderJob], config: dict
) -> list[Path]:
    """Encrypt the complete validated notice cohort in client order."""
    check_expected_notices(clients, jobs, require_files=True)
    clients_by_key = {(client.sequence, client.client_id): client for client in clients}
    outputs = []
    for job in jobs:
        client = clients_by_key[(job.sequence, job.client_id)]
        context = build_client_context(client)
        outputs.append(
            Path(
                encrypt_pdf(str(job.pdf), context, config=config.get("encryption", {}))
            )
        )
    return outputs
