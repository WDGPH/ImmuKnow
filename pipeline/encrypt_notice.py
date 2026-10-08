"""Encryption module for immunization PDF notices.

This module provides functions to encrypt PDF notices using client metadata.
It's designed to be integrated into the pipeline as an optional step.

Passwords are generated per-client per-PDF using templates defined in
config/parameters.yaml under encryption.password.template. Templates support
placeholders like {client_id}, {date_of_birth_iso}, {date_of_birth_iso_compact},
{first_name}, {last_name}, {school}, {postal_code}, etc.

**Input Contract:**

- Reads PDF files from disk and client metadata from JSON
- Assumes PDF and JSON files exist before encryption
- Assumes JSON contains valid client metadata with required fields for password template

**Output Contract:**

- Writes encrypted PDFs to disk with "_encrypted" suffix
- Unencrypted originals are preserved (deleted during cleanup step if configured)
- Per-PDF failures are logged and skipped (optional feature; some PDFs may not be encrypted)
- Pipeline completes even if some PDFs fail to encrypt

**Error Handling:**

- Infrastructure errors (missing PDF/JSON files) raise immediately (fail-fast)
- Configuration errors (invalid password template) raise immediately (fail-fast)
- Per-PDF failures (encryption error, invalid template data) are logged and skipped
- This strategy allows partial success; users are notified with summary of results
- Per-PDF recovery is intentional for optional step; allows users to still get output
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from importlib.resources import files
from typing import List, Tuple

import yaml
from pypdf import PdfReader, PdfWriter

from .enums import TemplateField
from .config_loader import load_config
from .generate_notices import read_artifact, read_render_jobs
from .utils import build_client_context, validate_and_format_template

# Configuration paths
CONFIG_DIR = Path(str(files("config")))

_encryption_config = None


def load_encryption_config():
    """Load and cache encryption configuration from parameters.yaml.

    Module-internal helper. Configuration is loaded once and cached globally
    for subsequent function calls. This avoids repeated file I/O when generating
    passwords for multiple PDFs.

    Returns
    -------
    dict
        Encryption configuration dict (typically contains 'password' key with
        'template' sub-key), or empty dict if config file not found.
    """
    global _encryption_config
    if _encryption_config is None:
        try:
            parameters_path = CONFIG_DIR / "parameters.yaml"
            if parameters_path.exists():
                with open(parameters_path) as f:
                    params = yaml.safe_load(f) or {}
                    _encryption_config = params.get("encryption", {})
            else:
                _encryption_config = {}
        except Exception:
            _encryption_config = {}
    return _encryption_config


def get_encryption_config():
    """Get the encryption configuration from parameters.yaml.

    Returns
    -------
    dict
        Cached encryption configuration.
    """
    return load_encryption_config()


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
        config = get_encryption_config()
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
    config = load_config(config_path).get("encryption", {})
    outputs = []
    for job in read_render_jobs(artifact_dir, require_compiled=True):
        client = clients[(job.sequence, job.client_id)]
        context = build_client_context(client)
        outputs.append(Path(encrypt_pdf(str(job.pdf), context, config=config)))
    return outputs


def load_notice_metadata(json_path: Path) -> tuple:
    """Load client data dict and context from JSON notice metadata.

    Module-internal helper for encrypt_notice(). Loads the JSON, extracts
    the client data dict, builds the templating context, and returns both.

    Parameters
    ----------
    json_path : Path
        Path to JSON metadata file.

    Returns
    -------
    tuple
        (client_dict: dict, context: dict) for password generation.

    Raises
    ------
    ValueError
        If JSON is invalid or has unexpected structure.
    """
    try:
        payload = json.loads(json_path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON structure ({json_path.name}): {exc}") from exc

    if not payload:
        raise ValueError(f"No client data in {json_path.name}")

    first_key = next(iter(payload))
    client_dict = payload[first_key]

    # Ensure record is a dict
    if not isinstance(client_dict, dict):
        raise ValueError(f"Invalid client record format in {json_path.name}")

    # Build context using shared helper
    context = build_client_context(client_dict)
    return client_dict, context


def encrypt_notice(json_path: str | Path, pdf_path: str | Path, language: str) -> str:
    """Encrypt a PDF notice using client data from the JSON file.

    Returns the path to the encrypted PDF with _encrypted suffix.
    If the encrypted version already exists and is newer than the source,
    returns the existing file without re-encrypting.

    Parameters
    ----------
    json_path : Path
        Path to the JSON file containing client metadata
    pdf_path : Path
        Path to the PDF file to encrypt
    language: str
        ISO 639-1 language code ('en' for English, 'fr' for French)

    Returns
    -------
    path
        Path to the encrypted PDF file

    Raises
    ------
    FileNotFoundError
        If JSON or PDF file not found
    ValueError
        If JSON is invalid
    """
    json_path = Path(json_path)
    pdf_path = Path(pdf_path)

    if not json_path.exists():
        raise FileNotFoundError(f"JSON file not found: {json_path}")
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    encrypted_path = pdf_path.with_name(f"{pdf_path.stem}_encrypted{pdf_path.suffix}")
    if encrypted_path.exists():
        try:
            if encrypted_path.stat().st_mtime >= pdf_path.stat().st_mtime:
                return str(encrypted_path)
        except OSError:
            pass

    client_data, context = load_notice_metadata(json_path)
    return encrypt_pdf(str(pdf_path), context)


def encrypt_pdfs_in_directory(
    pdf_directory: Path,
    json_file: Path,
    language: str,
) -> None:
    """Encrypt all PDF notices in a directory using a combined JSON metadata file.

    The JSON file should contain a dict where keys are client identifiers and
    values contain client metadata with DOB information.

    PDFs are encrypted in-place with the _encrypted suffix added to filename.

    Parameters
    ----------
    pdf_directory : str
        Directory containing PDF files to encrypt
    json_file : Path
        Path to the combined JSON file with all client metadata
    language :str
        ISO 639-1 language code ('en' for English, 'fr' for French)

    Raises
    ------
    FileNotFoundError
        If PDF directory or JSON file don't exist
    """
    pdf_directory = Path(pdf_directory)
    json_file = Path(json_file)

    if not pdf_directory.exists():
        raise FileNotFoundError(f"PDF directory not found: {pdf_directory}")
    if not json_file.exists():
        raise FileNotFoundError(f"JSON file not found: {json_file}")

    # Load the combined metadata
    try:
        metadata = json.loads(json_file.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {json_file.name}: {exc}") from exc

    # Extract clients from the metadata
    # Handle both preprocessed artifact format (has 'clients' key) and dict of clients
    if isinstance(metadata, dict) and "clients" in metadata:
        clients_data = metadata["clients"]
    else:
        clients_data = metadata

    if not clients_data:
        print("No client data found in JSON file.")
        return

    # Build a lookup dict: client_id -> client_data
    client_lookup = {}
    if isinstance(clients_data, list):
        # Format: list of client dicts with 'client_id' field
        for client in clients_data:
            client_id = client.get("client_id")
            if client_id:
                client_lookup[str(client_id)] = client
    elif isinstance(clients_data, dict):
        # Format: dict keyed by client_id
        client_lookup = {str(k): v for k, v in clients_data.items()}

    # Find PDFs and encrypt them
    pdf_files = sorted(pdf_directory.glob("*.pdf"))
    if not pdf_files:
        print("No PDFs found for encryption.")
        return

    start = time.perf_counter()
    print(
        f"🔐 Encrypting {len(pdf_files)} notices...",
        flush=True,
    )

    successes = 0
    skipped: List[Tuple[str, str]] = []
    failures: List[Tuple[str, str]] = []

    for pdf_path in pdf_files:
        pdf_name = pdf_path.name
        stem = pdf_path.stem

        # Skip conf and already-encrypted files
        if stem == "conf" or stem.endswith("_encrypted"):
            continue

        # Extract client_id from filename (format: en_client_XXXXX_YYYYYYY)
        # The last part after the last underscore is the client_id (OEN)
        parts = stem.split("_")
        if len(parts) >= 3:
            client_id = parts[-1]
        else:
            skipped.append((pdf_name, "Could not extract client_id from filename"))
            continue

        # Look up client data
        client_data = client_lookup.get(client_id)
        if not client_data:
            skipped.append((pdf_name, f"No metadata found for client_id {client_id}"))
            continue

        # Build context directly from client dict using shared helper
        try:
            context = build_client_context(client_data)
        except (ValueError, KeyError) as exc:
            skipped.append((pdf_name, str(exc)))
            continue

        # Encrypt the PDF
        try:
            encrypted_path = pdf_path.with_name(
                f"{pdf_path.stem}_encrypted{pdf_path.suffix}"
            )

            # Skip if encrypted version is newer than source
            if encrypted_path.exists():
                try:
                    if encrypted_path.stat().st_mtime >= pdf_path.stat().st_mtime:
                        successes += 1
                        continue
                except OSError:
                    pass

            encrypt_pdf(str(pdf_path), context)
            # Unencrypted PDF is preserved; deletion is handled in cleanup step
            successes += 1
        except Exception as exc:
            failures.append((pdf_name, str(exc)))

    duration = time.perf_counter() - start
    print(
        f"✅ Encryption complete in {duration:.2f}s "
        f"(success: {successes}, skipped: {len(skipped)}, failed: {len(failures)})"
    )

    for pdf_name, reason in skipped:
        print(f"SKIP: {pdf_name} -> {reason}")

    for pdf_name, reason in failures:
        print(f"WARNING: Encryption failed for {pdf_name}: {reason}")
