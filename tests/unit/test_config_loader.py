"""Configuration checks for the supported notice workflow."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from immuknow.config_loader import load_config, validate_config


@pytest.mark.unit
def test_packaged_configuration_loads_for_a_complete_run() -> None:
    config = load_config()
    assert "chart_diseases_header" in config
    assert "pdf_validation" in config
    assert "notice_versioning" in config


@pytest.mark.unit
def test_custom_configuration_loads_from_selected_path(tmp_path: Path) -> None:
    path = tmp_path / "parameters.yaml"
    path.write_text(
        "qr:\n  enabled: false\nnotice_versioning:\n  extra_manifest_rows: error\n",
        encoding="utf-8",
    )
    loaded = load_config(path)
    assert loaded["qr"]["enabled"] is False
    assert loaded["notice_versioning"]["extra_manifest_rows"] == "error"


@pytest.mark.unit
def test_missing_configuration_file_fails_with_its_path(tmp_path: Path) -> None:
    path = tmp_path / "missing.yaml"
    with pytest.raises(FileNotFoundError, match="missing.yaml"):
        load_config(path)


@pytest.mark.unit
def test_invalid_yaml_fails_before_a_run(tmp_path: Path) -> None:
    path = tmp_path / "parameters.yaml"
    path.write_text("qr: [unclosed", encoding="utf-8")
    with pytest.raises(yaml.YAMLError):
        load_config(path)


@pytest.mark.unit
def test_valid_qr_encryption_and_bundling_configuration() -> None:
    validate_config(
        {
            "qr": {
                "enabled": True,
                "payload_template": (
                    "https://example.ca/?id={client_id}"
                    "&dob={date_of_birth_iso}&lang={language_code}"
                ),
            },
            "encryption": {
                "enabled": True,
                "password": {"template": "{date_of_birth_iso_compact}"},
            },
            "bundling": {"bundle_size": 100, "group_by": "school"},
            "notice_versioning": {"extra_manifest_rows": "warn"},
        }
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "section,setting,message",
    [
        ("qr", {"enabled": True}, "qr.payload_template"),
        (
            "qr",
            {"enabled": True, "payload_template": ["not", "text"]},
            "qr.payload_template",
        ),
        (
            "qr",
            {"enabled": True, "payload_template": "https://e.ca/{unknown}"},
            "unknown",
        ),
        (
            "qr",
            {"enabled": True, "payload_template": "{client_id"},
            "qr.payload_template",
        ),
        ("encryption", {"enabled": True}, "encryption.password.template"),
        (
            "encryption",
            {"enabled": True, "password": {"template": ["bad"]}},
            "encryption.password.template",
        ),
        (
            "encryption",
            {"enabled": True, "password": {"template": "{secret}"}},
            "secret",
        ),
        (
            "encryption",
            {"enabled": True, "password": {"template": "{client_id"}},
            "encryption.password.template",
        ),
        ("typst", {"bin": []}, "typst.bin"),
        ("bundling", {"bundle_size": -1}, "bundling.bundle_size"),
        ("bundling", {"bundle_size": "10"}, "bundling.bundle_size"),
        ("bundling", {"bundle_size": 1, "group_by": "language"}, "bundling.group_by"),
        ("bundling", {"bundle_size": 1, "group_by": 123}, "bundling.group_by"),
        (
            "cleanup",
            {"delete_unencrypted_pdfs": "yes"},
            "cleanup.delete_unencrypted_pdfs",
        ),
    ],
)
def test_invalid_delivery_settings_fail_with_actionable_key(
    section: str, setting: dict, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_config({"qr": {"enabled": False}, section: setting})


@pytest.mark.unit
@pytest.mark.parametrize(
    "section,setting",
    [
        ("qr", {"enabled": True, "payload_template": "https://e.ca/{date_of_birth}"}),
        (
            "encryption",
            {"enabled": True, "password": {"template": "{date_of_birth}"}},
        ),
    ],
)
def test_ambiguous_birth_date_placeholder_names_iso_alternatives(
    section: str, setting: dict
) -> None:
    with pytest.raises(ValueError) as error:
        validate_config({"qr": {"enabled": False}, section: setting})
    message = str(error.value)
    assert "{date_of_birth}" in message
    assert "{date_of_birth_iso}" in message
    assert "{date_of_birth_iso_compact}" in message


@pytest.mark.unit
@pytest.mark.parametrize("retired_value", [True, False, None])
def test_retired_allow_unassigned_setting_is_rejected(retired_value: object) -> None:
    with pytest.raises(ValueError, match="notice_versioning.allow_unassigned"):
        validate_config(
            {
                "qr": {"enabled": False},
                "notice_versioning": {"allow_unassigned": retired_value},
            }
        )


@pytest.mark.unit
@pytest.mark.parametrize("policy", ["warn", "error"])
def test_extra_manifest_row_policy_remains_configurable(policy: str) -> None:
    validate_config(
        {
            "qr": {"enabled": False},
            "notice_versioning": {"extra_manifest_rows": policy},
        }
    )


@pytest.mark.unit
def test_extra_manifest_row_policy_rejects_unknown_value() -> None:
    with pytest.raises(ValueError, match="notice_versioning.extra_manifest_rows"):
        validate_config(
            {
                "qr": {"enabled": False},
                "notice_versioning": {"extra_manifest_rows": "ignore"},
            }
        )


@pytest.mark.unit
def test_disabled_optional_features_ignore_unused_settings() -> None:
    """Disabled QR, encryption, and bundling do not validate unused templates."""
    validate_config(
        {
            "qr": {"enabled": False, "payload_template": "{unknown}"},
            "encryption": {"enabled": False, "password": {"template": "{unknown}"}},
            "bundling": {"bundle_size": 0, "group_by": "unknown"},
        }
    )


@pytest.mark.unit
def test_qr_is_enabled_by_default_and_requires_a_payload() -> None:
    """An omitted QR section must not silently disable QR generation."""
    with pytest.raises(ValueError, match="qr.payload_template"):
        validate_config({})


@pytest.mark.unit
def test_supported_qr_fields_and_repeated_placeholders() -> None:
    """The full documented QR field set stays accepted without changing values."""
    fields = [
        "client_id",
        "first_name",
        "last_name",
        "name",
        "date_of_birth_iso",
        "date_of_birth_iso_compact",
        "school",
        "board",
        "street_address",
        "city",
        "province",
        "postal_code",
        "language_code",
        "client_id",
    ]
    validate_config(
        {
            "qr": {
                "enabled": True,
                "payload_template": "https://example.ca/?"
                + "&".join(f"f{i}={{{field}}}" for i, field in enumerate(fields)),
            }
        }
    )


@pytest.mark.unit
def test_unsupported_qr_field_error_lists_supported_options() -> None:
    with pytest.raises(ValueError) as error:
        validate_config({"qr": {"enabled": True, "payload_template": "{unknown}"}})
    message = str(error.value)
    assert "qr.payload_template" in message
    assert "unknown" in message
    assert "date_of_birth_iso" in message


@pytest.mark.unit
def test_bundling_error_names_available_strategies() -> None:
    with pytest.raises(ValueError) as error:
        validate_config(
            {
                "qr": {"enabled": False},
                "bundling": {"bundle_size": 1, "group_by": "language"},
            }
        )
    message = str(error.value)
    assert "bundling.group_by" in message
    assert "school" in message
    assert "board" in message


@pytest.mark.unit
def test_encryption_is_checked_after_valid_qr_configuration() -> None:
    with pytest.raises(ValueError, match="encryption.password.template"):
        validate_config(
            {
                "qr": {
                    "enabled": True,
                    "payload_template": "https://example.ca/{client_id}",
                },
                "encryption": {"enabled": True, "password": {"template": "{unknown}"}},
            }
        )


@pytest.mark.unit
@pytest.mark.parametrize("group_by", [None, "size", "school", "board"])
def test_supported_bundle_groupings_are_accepted(group_by: str | None) -> None:
    validate_config(
        {
            "qr": {"enabled": False},
            "bundling": {"bundle_size": 25, "group_by": group_by},
        }
    )


@pytest.mark.unit
@pytest.mark.parametrize("ignored_agents", ["Ig", None, [1], [""]])
def test_invalid_history_exclusions_fail_before_a_run(ignored_agents) -> None:
    with pytest.raises(ValueError, match="ignore_agents must be a list"):
        validate_config({"qr": {"enabled": False}, "ignore_agents": ignored_agents})
