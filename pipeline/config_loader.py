"""Configuration loading utilities for the immunization pipeline.

Provides a centralized way to load and validate the parameters.yaml
configuration file across all pipeline scripts.
"""

from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .enums import TemplateField
from .utils import extract_template_fields

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = SCRIPT_DIR.parent / "config" / "parameters.yaml"


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load and parse the parameters.yaml configuration file.

    Automatically validates the configuration after loading. Raises
    clear exceptions if validation fails, enabling fail-fast behavior
    for infrastructure errors.

    Parameters
    ----------
    config_path : Path, optional
        Path to the configuration file. If not provided, uses the default
        location (config/parameters.yaml in the project root).

    Returns
    -------
    Dict[str, Any]
        Parsed and validated YAML configuration as a nested dictionary.

    Raises
    ------
    FileNotFoundError
        If the configuration file does not exist.
    yaml.YAMLError
        If the configuration file is invalid YAML.
    ValueError
        If the configuration fails validation (see validate_config).
    """
    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH

    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    validate_config(config)
    return config


def validate_template_fields(
    template: str,
    context_name: str,
    config_key: str,
) -> None:
    """Validate that all placeholders in a template are supported fields.

    Checks template string placeholders against the centralized whitelist of
    allowed template fields (TemplateField enum). Raises ValueError if any
    unsupported placeholders are found.

    This validation catches configuration errors early (at config load time)
    instead of failing silently during QR generation or PDF encryption.

    Parameters
    ----------
    template : str
        Template string with placeholders (e.g., "{client_id}_{invalid_field}")
    context_name : str
        Human-readable name for error messages (e.g., "QR code payload", "encryption password")
    config_key : str
        Configuration key path for error messages (e.g., "qr.payload_template")

    Raises
    ------
    ValueError
        If template contains unsupported placeholder fields with detailed
        error message listing invalid fields and available options.

    Examples
    --------
    >>> validate_template_fields(
    ...     "{client_id}_{invalid_field}",
    ...     "QR code payload",
    ...     "qr.payload_template"
    ... )
    ValueError: QR code payload template contains unsupported placeholder(s): ['invalid_field']
    Config key: qr.payload_template
    Supported fields: client_id, first_name, last_name, ...
    """
    allowed_fields = TemplateField.all_values()

    try:
        placeholders = extract_template_fields(template)
    except ValueError as exc:
        raise ValueError(
            f"{context_name} template has invalid format syntax: {exc}\n"
            f"Config key: {config_key}"
        ) from exc

    unsupported = placeholders - allowed_fields

    if unsupported:
        raise ValueError(
            f"{context_name} template contains unsupported placeholder(s): {sorted(unsupported)}\n"
            f"Config key: {config_key}\n"
            f"Supported fields: {', '.join(sorted(allowed_fields))}"
        )


def validate_config(config: Dict[str, Any]) -> None:
    """Validate the entire configuration for consistency and required values.

    Validates all conditional and required configuration keys across the
    entire config. Raises clear exceptions if validation fails, allowing
    the pipeline to fail-fast with actionable error messages.

    Parameters
    ----------
    config : Dict[str, Any]
        Configuration dictionary (result of load_config).

    Raises
    ------
    ValueError
        If required configuration is missing or invalid.

    Notes
    -----
    **Validation checks:**

    - **QR Generation:** If qr.enabled=true, requires qr.payload_template (non-empty string)
    - **Typst Compilation:** If typst.bin is set, must be a string
    - **PDF Bundling:** If bundle_size > 0, must be positive integer; group_by must be valid enum
    - **Encryption:** If encryption.enabled=true, requires password.template
    - **Cleanup:** If delete_unencrypted_pdfs is set, must be boolean

    **Validation philosophy:**
    - Infrastructure errors (missing config) raise immediately (fail-fast)
    - All error messages are clear and actionable
    - Config is validated once at load time, not per-step
    """
    # Validate QR config
    qr_config = config.get("qr", {})
    qr_enabled = qr_config.get("enabled", True)

    if qr_enabled:
        payload_template = qr_config.get("payload_template")
        if not payload_template:
            raise ValueError(
                "QR code generation is enabled but qr.payload_template is not specified. "
                "Please define qr.payload_template in config/parameters.yaml "
                "or set qr.enabled to false."
            )

        if not isinstance(payload_template, str):
            raise ValueError(
                f"qr.payload_template must be a string, got {type(payload_template).__name__}"
            )

        # Validate template placeholders against allowed fields
        validate_template_fields(
            payload_template,
            "QR code payload",
            "qr.payload_template",
        )

    # Validate Typst config
    typst_config = config.get("typst", {})
    typst_bin = typst_config.get("bin", "typst")
    if not isinstance(typst_bin, str):
        raise ValueError(f"typst.bin must be a string, got {type(typst_bin).__name__}")

    # Validate Bundling config
    bundling_config = config.get("bundling", {})
    bundle_size = bundling_config.get("bundle_size", 0)

    # First validate type before comparing values
    if bundle_size != 0:  # Only validate if bundle_size is explicitly set
        if not isinstance(bundle_size, int):
            raise ValueError(
                f"bundling.bundle_size must be an integer, got {type(bundle_size).__name__}"
            )
        if bundle_size <= 0:
            raise ValueError(
                f"bundling.bundle_size must be positive, got {bundle_size}"
            )

        # Validate group_by strategy
        group_by = bundling_config.get("group_by")
        from .enums import BundleStrategy

        try:
            if group_by is not None:
                BundleStrategy.from_string(group_by)
        except ValueError as exc:
            raise ValueError(f"Invalid bundling.group_by strategy: {exc}") from exc

    # Validate Encryption config
    encryption_config = config.get("encryption", {})
    encryption_enabled = encryption_config.get("enabled", False)

    if encryption_enabled:
        password_config = encryption_config.get("password", {})
        password_template = password_config.get("template")
        if not password_template:
            raise ValueError(
                "Encryption is enabled but encryption.password.template is not specified. "
                "Please define encryption.password.template in config/parameters.yaml "
                "or set encryption.enabled to false."
            )

        if not isinstance(password_template, str):
            raise ValueError(
                f"encryption.password.template must be a string, "
                f"got {type(password_template).__name__}"
            )

        # Validate template placeholders against allowed fields
        validate_template_fields(
            password_template,
            "Encryption password",
            "encryption.password.template",
        )

    # Validate Cleanup config
    cleanup_config = config.get("cleanup", {})
    delete_unencrypted = cleanup_config.get("delete_unencrypted_pdfs", False)
    if not isinstance(delete_unencrypted, bool):
        raise ValueError(
            f"cleanup.delete_unencrypted_pdfs must be a boolean, "
            f"got {type(delete_unencrypted).__name__}"
        )

    # Validate optional notice_versioning config
    notice_versioning_config = config.get("notice_versioning", {})
    if notice_versioning_config:
        allow_unassigned = notice_versioning_config.get("allow_unassigned")
        if allow_unassigned is not None and not isinstance(allow_unassigned, bool):
            raise ValueError(
                f"notice_versioning.allow_unassigned must be a boolean, "
                f"got {type(allow_unassigned).__name__}"
            )

        extra_manifest_rows = notice_versioning_config.get("extra_manifest_rows")
        if extra_manifest_rows is not None and extra_manifest_rows not in (
            "error",
            "warn",
        ):
            raise ValueError(
                f"notice_versioning.extra_manifest_rows must be 'error' or 'warn', "
                f"got {extra_manifest_rows!r}"
            )
