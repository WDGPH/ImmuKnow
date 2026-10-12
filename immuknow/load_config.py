"""Configuration loading utilities for the immunization pipeline.

Provides a centralized way to load and validate the parameters.yaml
configuration file across all pipeline scripts.
"""

from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml

from .bundle_pdfs import BundleGrouping
from .client_placeholders import (
    CLIENT_PLACEHOLDERS,
    extract_template_fields,
    validate_and_format_template,
)

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = (
    Path(str(files("immuknow").joinpath("config"))) / "parameters.yaml"
)


def load_config(config_path: Path | None = None) -> dict[str, Any]:
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
        raw = yaml.safe_load(f)
        config = {} if raw is None else raw

    validate_config(config)
    return config


def validate_template_fields(
    template: str,
    context_name: str,
    config_key: str,
) -> None:
    """Validate that all placeholders in a template are supported fields.

    Checks template string placeholders against the centralized whitelist of
    allowed password placeholders. Raises ValueError if any
    unsupported placeholders are found.

    This validation catches configuration errors early (at config load time)
    instead of failing silently during PDF encryption.

    Parameters
    ----------
    template : str
        Template string with placeholders (e.g., "{client_id}_{invalid_field}")
    context_name : str
        Human-readable name for error messages (e.g., "encryption password")
    config_key : str
        Configuration key path for error messages (e.g., "encryption.password.template")

    Raises
    ------
    ValueError
        If fields or formatting are invalid. Diagnostics name supported fields
        without repeating secret template text.

    Examples
    --------
    >>> validate_template_fields(
    ...     "{client_id}_{invalid_field}",
    ...     "encryption password",
    ...     "encryption.password.template"
    ... )
    ValueError: Encryption password template contains unsupported placeholders.
    Config key: encryption.password.template
    Supported fields: client_id, first_name, last_name, ...
    """
    allowed_fields = CLIENT_PLACEHOLDERS

    try:
        placeholders = extract_template_fields(template)
    except ValueError:
        raise ValueError(
            f"{config_key}: invalid password template syntax; check braces and formatting"
        ) from None

    unsupported = placeholders - allowed_fields

    if "date_of_birth" in placeholders:
        raise ValueError(
            f"{config_key}: {{date_of_birth}} is retired because its display format "
            "depends on notice localization. Use {date_of_birth_iso} or "
            "{date_of_birth_iso_compact} explicitly."
        )

    if unsupported:
        raise ValueError(
            f"{context_name} template contains unsupported placeholders.\n"
            f"Config key: {config_key}\n"
            f"Supported fields: {', '.join(sorted(allowed_fields))}"
        )
    # Configured passwords contain strings only. Validate formatting before any
    # source row is encrypted, without including secret text in error details.
    validate_and_format_template(
        template, {field: "" for field in allowed_fields}, allowed_fields
    )


def validate_config(config: dict[str, Any]) -> None:
    """Reject malformed run settings and retired display or destructive cleanup options."""
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a mapping")

    retired = {
        "qr",
        "preprocess",
        "chart_diseases_header",
        "ignore_agents",
        "notice_versioning",
        "pdf_validation",
        "cleanup",
    } & config.keys()
    if retired:
        raise ValueError(
            "Retired Python configuration: "
            + ", ".join(sorted(retired))
            + ". Put display and QR options in the authored Settings file."
        )

    for section in ("typst", "bundling", "encryption", "school_validation", "pipeline"):
        if section in config and not isinstance(config[section], dict):
            raise ValueError(f"{section} must be a mapping")
    encryption = config.get("encryption", {})
    if "password" in encryption and not isinstance(encryption["password"], dict):
        raise ValueError("encryption.password must be a mapping")
    pipeline = config.get("pipeline", {})
    if "before_run" in pipeline:
        raise ValueError("pipeline.before_run is retired; previous runs are retained")
    after_run = pipeline.get("after_run", {})
    if not isinstance(after_run, dict):
        raise ValueError("pipeline.after_run must be a mapping")
    if "remove_unencrypted_pdfs" in after_run:
        raise ValueError(
            "remove_unencrypted_pdfs is retired; original PDFs are retained"
        )
    if not isinstance(after_run.get("remove_artifacts", False), bool):
        raise ValueError("pipeline.after_run.remove_artifacts must be a boolean")
    for section in ("encryption", "school_validation"):
        if type(config.get(section, {}).get("enabled", False)) is not bool:
            raise ValueError(f"{section}.enabled must be a boolean")
    school = config.get("school_validation", {})
    if school.get("enabled", False):
        for field in ("reference_file", "target_phu"):
            value = school.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"school_validation.{field} must be a nonempty string when enabled"
                )
    if "unmatched_behavior" in school:
        raise ValueError(
            "school_validation.unmatched_behavior is retired; unmatched rows warn and remain"
        )

    # Validate Typst config
    typst_config = config.get("typst", {})
    typst_bin = typst_config.get("bin", "typst")
    if not isinstance(typst_bin, str):
        raise ValueError(f"typst.bin must be a string, got {type(typst_bin).__name__}")

    # Validate Bundling config
    bundling_config = config.get("bundling", {})
    bundle_size = bundling_config.get("bundle_size", 0)

    if type(bundle_size) is not int or bundle_size < 0:
        raise ValueError("bundling.bundle_size must be a nonnegative integer")
    group_by = bundling_config.get("group_by")
    try:
        if group_by is not None:
            BundleGrouping.from_string(group_by)
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
