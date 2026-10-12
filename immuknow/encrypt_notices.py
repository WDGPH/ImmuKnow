"""Make optional individual encrypted copies without changing original notices."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter

from .client_placeholders import (
    CLIENT_PLACEHOLDERS,
    build_client_context,
    extract_template_fields,
    validate_and_format_template,
)
from .data_models import ClientRecord


def encrypt_notice(
    client: ClientRecord, source: Path, destination: Path, settings: dict
) -> None:
    """Publish a separate copy only after its password and PDF are verified.

    Unavailable referenced facts cannot become an empty or partially guessed
    password. No exception includes the expanded password. The orchestrator
    records the actual outcome and continues independent clients.
    """
    if source.resolve() == destination.resolve():
        raise ValueError("Encrypted output must be separate from the original")
    context = build_client_context(client)
    template = settings.get("password", {}).get(
        "template", "{date_of_birth_iso_compact}"
    )
    try:
        fields = extract_template_fields(template)
        password = validate_and_format_template(
            template, context, allowed_fields=CLIENT_PLACEHOLDERS
        )
    except (KeyError, ValueError):
        raise ValueError(
            "Invalid password template; check allowed fields and formatting"
        ) from None
    missing = sorted(field for field in fields if not context.get(field, "").strip())
    if missing:
        raise ValueError("Password facts are unavailable: " + ", ".join(missing))
    if not password.strip():
        raise ValueError("Password must not be empty")

    reader = PdfReader(source)
    writer = PdfWriter()
    writer.append(reader)
    if reader.metadata:
        writer.add_metadata(reader.metadata)
    writer.encrypt(user_password=password, owner_password=password)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(".partial.pdf")
    try:
        with partial.open("wb") as stream:
            writer.write(stream)
        encrypted = PdfReader(partial)
        if not encrypted.is_encrypted or not encrypted.decrypt(password):
            raise ValueError("Encrypted output could not be verified")
        if len(encrypted.pages) != len(reader.pages):
            raise ValueError("Encrypted output page count differs from the original")
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)
