"""Render optional QR images and return clients carrying their encoded links."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import replace
from pathlib import Path
from typing import Optional
from urllib.parse import quote

try:
    import qrcode
    from qrcode import constants as qrcode_constants
    from PIL import Image
except ImportError:
    qrcode = None  # type: ignore
    qrcode_constants = None  # type: ignore
    Image = None

from .data_models import ClientRecord
from .enums import TemplateField
from .utils import build_client_context, validate_and_format_template

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# Allowed template fields for QR payloads (from centralized enum)
SUPPORTED_QR_TEMPLATE_FIELDS = TemplateField.all_values()


def encode_qr_payload_url(payload_url: str) -> str:
    """URL-encode parameter values in a QR payload URL.

    This function preserves the URL structure (scheme, domain, path, parameter
    delimiters) while properly encoding parameter values to handle special
    characters like spaces, accents, and special symbols.

    Parameters
    ----------
    payload_url : str
        A URL string like "https://example.com/surveys/?s=ABC&qrfn=First Name&qrln=Last Name"

    Returns
    -------
    str
        The same URL with parameter values properly percent-encoded (e.g., spaces → %20)
    """
    # Split URL into scheme+domain+path and query string
    if "?" not in payload_url:
        return payload_url

    base_url, query_string = payload_url.split("?", 1)

    # Parse and re-encode each parameter
    encoded_params = []
    for param in query_string.split("&"):
        if "=" in param:
            key, value = param.split("=", 1)
            # URL-encode the value (preserve unreserved characters)
            encoded_value = quote(value, safe="")
            encoded_params.append(f"{key}={encoded_value}")
        else:
            # No value, just preserve the key
            encoded_params.append(param)

    # Reconstruct the URL
    return base_url + "?" + "&".join(encoded_params)


def generate_qr_code(
    data: str,
    output_dir: Path,
    *,
    filename: Optional[str] = None,
) -> Path:
    """Generate a monochrome QR code PNG and return the saved path.

    Parameters
    ----------
    data:
        The string payload to encode inside the QR code.
    output_dir:
        Directory where the QR image should be saved. The directory is created
        if it does not already exist.
    filename:
        Optional file name (including extension) for the resulting PNG. When
        omitted a deterministic name derived from the payload hash is used.

    Returns
    -------
    Path
        Absolute path to the generated PNG file.
    """

    if qrcode is None or Image is None:  # pragma: no cover - exercised in optional envs
        raise RuntimeError(
            "QR code generation requires the 'qrcode' and 'pillow' packages. "
            "Install them via 'uv sync' before enabling QR payloads."
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode_constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    image = qr.make_image(fill_color="black", back_color="white")
    pil_image = getattr(image, "get_image", lambda: image)()

    # Convert to 1-bit black/white without dithering to keep crisp edges.
    # NONE (0) means no dithering
    pil_bitmap = pil_image.convert("1", dither=0)

    if not filename:
        digest = hashlib.sha1(data.encode("utf-8")).hexdigest()[:12]
        filename = f"qr_{digest}.png"

    target_path = output_dir / filename
    pil_bitmap.save(target_path, format="PNG", bits=1)
    return target_path


def generate_qr_codes(
    clients: list[ClientRecord],
    output_dir: Path,
    config: dict,
) -> tuple[list[ClientRecord], list[Path]]:
    """Generate QR PNGs and return updated records in client order."""
    qr_config = config.get("qr", {})
    qr_enabled = qr_config.get("enabled", False)

    if not qr_enabled:
        return clients, []

    if not clients:
        return clients, []

    payload_template = qr_config["payload_template"]

    # Ensure output directory exists
    qr_output_dir = output_dir / "qr_codes"
    qr_output_dir.mkdir(parents=True, exist_ok=True)

    generated_files: list[Path] = []
    updated_clients: list[ClientRecord] = []

    # Generate QR code for each client
    for client in clients:
        client_id = client.client_id
        # Build context directly from client data using shared helper
        qr_context = build_client_context(client)

        # Generate payload (template is now required)
        try:
            qr_payload = validate_and_format_template(
                payload_template,
                qr_context,
                allowed_fields=SUPPORTED_QR_TEMPLATE_FIELDS,
            )
            # Properly URL-encode the payload for QR code
            qr_payload = encode_qr_payload_url(qr_payload)
        except (KeyError, ValueError) as exc:
            LOG.warning(
                "Could not format QR payload for client %s: %s",
                client_id,
                exc,
            )
            updated_clients.append(client)
            continue

        # Generate PNG
        try:
            qr_path = generate_qr_code(
                qr_payload,
                qr_output_dir,
                filename=f"qr_code_{client.sequence}_{client_id}.png",
            )
            generated_files.append(qr_path)

            updated_clients.append(
                replace(
                    client,
                    qr={
                        "payload": qr_payload,
                        "filename": qr_path.name,
                        "path": str(qr_path.resolve()),
                    },
                )
            )

            LOG.info("Generated QR code for client %s: %s", client_id, qr_path)
        except RuntimeError as exc:
            LOG.warning(
                "Could not generate QR code for client %s: %s",
                client_id,
                exc,
            )
            updated_clients.append(client)

    return updated_clients, generated_files
