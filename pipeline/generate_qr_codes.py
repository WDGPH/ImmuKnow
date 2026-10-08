"""Generate QR code PNG files from preprocessed client artifact.

This module creates QR code images for each client in the preprocessed artifact.
QR payloads are generated from template strings defined in parameters.yaml and
rendered as PNG files in the output artifacts directory.

The QR code generation step is optional and can be skipped via the qr.enabled
configuration setting.

**Input Contract:**

- Reads preprocessed artifact JSON (created by preprocess step)
- Assumes artifact contains valid client records with required fields
- Assumes qr.enabled=true and qr.payload_template defined in config (if QR generation requested)

**Output Contract:**

- Writes QR code PNG files to output/artifacts/qr_codes/
- Returns list of successfully generated QR file paths
- Per-client errors are logged and skipped (optional feature; doesn't halt pipeline)

**Error Handling:**

- Configuration errors (missing template) raise immediately (infrastructure error)
- Per-client failures (invalid data) log warning and continue (data error in optional feature)
- This strategy allows partial success; some clients may not have QR codes

**Validation Contract:**

What this module validates:

- Artifact file exists and is valid JSON (validation in read_preprocessed_artifact())
- QR code generation is enabled in config (qr.enabled=true)
- Payload template is defined if QR generation is enabled
- Payload template format is valid (has valid placeholders)
- QR code can be rendered as PNG (infrastructure check)

What this module assumes (validated upstream):

- Artifact JSON structure is valid (validated by preprocessing step)
- Client records have all required fields (validated by preprocessing step)
- Output directory can be created (general I/O)

Per-client failures (invalid client data, template rendering errors) are logged
and skipped (intentional for optional feature). Some clients may lack QR codes.
"""

from __future__ import annotations

import hashlib
import json
import logging
from importlib.resources import files
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import yaml

try:
    import qrcode
    from qrcode import constants as qrcode_constants
    from PIL import Image
except ImportError:
    qrcode = None  # type: ignore
    qrcode_constants = None  # type: ignore
    Image = None

from .config_loader import load_config
from .enums import TemplateField
from .utils import build_client_context, validate_and_format_template

CONFIG_DIR = Path(str(files("config")))
PARAMETERS_PATH = CONFIG_DIR / "parameters.yaml"

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


def read_preprocessed_artifact(path: Path) -> Dict[str, Any]:
    """Read preprocessed client artifact from JSON.

    **Input Contract:** Assumes artifact was created by preprocessing step and
    exists on disk. Does not validate artifact schema; assumes preprocessing
    has already validated client data structure.

    Parameters
    ----------
    path : Path
        Path to the preprocessed JSON artifact file.

    Returns
    -------
    Dict[str, Any]
        Parsed artifact dict with clients and metadata.

    Raises
    ------
    FileNotFoundError
        If artifact file does not exist.
    json.JSONDecodeError
        If artifact is not valid JSON.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Preprocessed artifact not found: {path}. "
            "Ensure preprocessing step has completed."
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload
    except json.JSONDecodeError as exc:
        raise ValueError(f"Preprocessed artifact is not valid JSON: {path}") from exc


def load_qr_settings(config_path: Path | None = None) -> str:
    """Load QR payload template from parameters.yaml file.

    Raises ValueError if qr.payload_template is not specified in the configuration.

    Returns:
        QR payload template string
    """
    if config_path is None:
        config_path = PARAMETERS_PATH

    if not config_path.exists():
        raise FileNotFoundError(
            f"QR code generation enabled but configuration file not found: {config_path}"
        )

    params = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    config_data = params.get("qr", {})

    template_config = config_data.get("payload_template")
    if not template_config:
        raise ValueError(
            "QR code generation is enabled but qr.payload_template is not specified in config. "
            "Please define qr.payload_template in parameters.yaml or set qr.enabled to false."
        )

    if not isinstance(template_config, str):
        raise ValueError(
            f"qr.payload_template must be a string, got {type(template_config).__name__}"
        )

    payload_template = template_config

    return payload_template


def generate_qr_codes(
    artifact_path: Path,
    output_dir: Path,
    config_path: Path | None = None,
) -> List[Path]:
    """Generate QR code PNG files from preprocessed artifact.

    Parameters
    ----------
    artifact_path : Path
        Path to the preprocessed JSON artifact.
    output_dir : Path
        Directory to write QR code PNG files.
    config_path : Path, optional
        Path to parameters.yaml. If not provided, uses default location.

    Returns
    -------
    List[Path]
        List of generated QR code PNG file paths.
    """
    if config_path is None:
        config_path = PARAMETERS_PATH

    # Load QR configuration
    config = load_config(config_path)
    qr_config = config.get("qr", {})
    qr_enabled = qr_config.get("enabled", True)

    if not qr_enabled:
        LOG.info("QR code generation disabled in configuration")
        return []

    # Read artifact
    artifact = read_preprocessed_artifact(artifact_path)
    clients = artifact.get("clients", [])

    if not clients:
        LOG.info("No clients in artifact")
        return []

    # Load QR settings (will raise ValueError if template not specified)
    try:
        payload_template = load_qr_settings(config_path)
    except (FileNotFoundError, ValueError) as exc:
        raise RuntimeError(f"Cannot generate QR codes: {exc}") from exc

    # Ensure output directory exists
    qr_output_dir = output_dir / "qr_codes"
    qr_output_dir.mkdir(parents=True, exist_ok=True)

    generated_files: List[Path] = []

    # Generate QR code for each client
    for client in clients:
        client_id = client.get("client_id")
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
            continue

        # Generate PNG
        try:
            sequence = client.get("sequence")
            qr_path = generate_qr_code(
                qr_payload,
                qr_output_dir,
                filename=f"qr_code_{sequence}_{client_id}.png",
            )
            generated_files.append(qr_path)

            # Store the QR payload in the client record
            client["qr"] = {
                "payload": qr_payload,
                "filename": f"qr_code_{sequence}_{client_id}.png",
                "path": str(qr_path.resolve()),
            }

            LOG.info("Generated QR code for client %s: %s", client_id, qr_path)
        except RuntimeError as exc:
            LOG.warning(
                "Could not generate QR code for client %s: %s",
                client_id,
                exc,
            )

    # Write updated artifact back to disk with qr fields
    if generated_files:
        artifact_path.write_text(
            json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        LOG.info("Updated artifact with QR codes: %s", artifact_path)

    return generated_files


def main(
    artifact_path: Path,
    output_dir: Path,
    config_path: Path | None = None,
) -> int:
    """Main entry point for QR code generation.

    Parameters
    ----------
    artifact_path : Path
        Path to the preprocessed JSON artifact.
    output_dir : Path
        Directory to write QR code PNG files.
    config_path : Path, optional
        Path to parameters.yaml configuration file.

    Returns
    -------
    int
        Number of QR codes generated.
    """
    generated = generate_qr_codes(artifact_path, output_dir, config_path)
    if generated:
        print(
            f"Generated {len(generated)} QR code PNG file(s) in {output_dir}/qr_codes/"
        )
    return len(generated)


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
