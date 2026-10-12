"""Python configuration contains factual, execution and delivery choices only."""

from pathlib import Path

import pytest

from immuknow.load_config import load_config, validate_config, validate_template_fields


@pytest.mark.unit
def test_packaged_configuration_has_no_display_or_qr_options():
    config = load_config()
    assert (
        not {
            "qr",
            "preprocess",
            "ignore_agents",
            "chart_diseases_header",
            "notice_versioning",
        }
        & config.keys()
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "key",
    ["qr", "preprocess", "ignore_agents", "chart_diseases_header", "notice_versioning"],
)
def test_retired_display_options_direct_authors_to_settings(key):
    with pytest.raises(ValueError, match="Settings"):
        validate_config({key: {}})


@pytest.mark.unit
@pytest.mark.parametrize("template", ["{unknown}", "{date_of_birth}", "{"])
def test_password_placeholders_reject_unsupported_or_ambiguous_fields(template):
    with pytest.raises(ValueError):
        validate_template_fields(
            template, "encryption password", "encryption.password.template"
        )


@pytest.mark.unit
def test_malformed_configuration_stops_setup(tmp_path: Path):
    path = tmp_path / "parameters.yaml"
    path.write_text("[list, is, not, config]")
    with pytest.raises(ValueError, match="mapping"):
        load_config(path)


@pytest.mark.unit
@pytest.mark.parametrize(
    "section", ["encryption", "typst", "bundling", "school_validation", "pipeline"]
)
def test_malformed_nested_sections_fail_clearly(section):
    with pytest.raises(ValueError, match="mapping"):
        validate_config({section: []})


@pytest.mark.unit
@pytest.mark.parametrize(
    "template",
    ["{client_id:PRIVATE_SPECIFIER}", "{PRIVATE_SPECIFIER}", "PRIVATE_SPECIFIER {"],
)
def test_shared_password_format_errors_are_sanitized(template):
    with pytest.raises(ValueError) as failure:
        validate_config(
            {"encryption": {"enabled": True, "password": {"template": template}}}
        )
    assert "PRIVATE_SPECIFIER" not in str(failure.value)


@pytest.mark.unit
@pytest.mark.parametrize("section", ["school_validation", "encryption"])
def test_enabled_flags_require_boolean_values(section):
    with pytest.raises(ValueError, match="enabled must be a boolean"):
        validate_config({section: {"enabled": "false"}})


@pytest.mark.unit
@pytest.mark.parametrize("value", [False, True, 0.0, -1])
def test_bundle_size_requires_exact_nonnegative_integer(value):
    with pytest.raises(ValueError, match="nonnegative integer"):
        validate_config({"bundling": {"bundle_size": value}})
    validate_config({"bundling": {"bundle_size": 0}})


@pytest.mark.unit
@pytest.mark.parametrize(
    "field,value",
    [("reference_file", None), ("reference_file", " "), ("target_phu", "")],
)
def test_enabled_school_lookup_requires_its_shared_inputs(field, value):
    school = {
        "enabled": True,
        "reference_file": "school_reference.json",
        "target_phu": "Example PHU",
    }
    school[field] = value
    with pytest.raises(ValueError, match=field):
        validate_config({"school_validation": school})
