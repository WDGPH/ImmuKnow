"""Python configuration contains factual, execution and delivery choices only."""

from pathlib import Path

import pytest

from immuknow.load_config import load_config, validate_config, validate_template_fields
from immuknow.load_config import parse_config


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


@pytest.mark.parametrize(
    "value", [0, -1, True, "30", None, float("inf"), float("nan"), 86401]
)
def test_native_deadlines_require_finite_positive_seconds(value):
    with pytest.raises(ValueError, match="typst.timeouts_seconds.compile"):
        validate_config({"typst": {"timeouts_seconds": {"compile": value}}})


@pytest.mark.parametrize("settings", [None, [], {"compille": 10}])
def test_native_deadlines_reject_malformed_or_unknown_settings(settings):
    with pytest.raises(ValueError, match="typst.timeouts_seconds"):
        validate_config({"typst": {"timeouts_seconds": settings}})


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
@pytest.mark.parametrize("value", [None, "", " "])
def test_enabled_school_lookup_requires_a_target_phu(value):
    school = {
        "enabled": True,
        "reference_file": "school_reference.json",
        "target_phu": value,
    }
    with pytest.raises(ValueError, match="target_phu"):
        validate_config({"school_validation": school})


@pytest.mark.unit
@pytest.mark.parametrize(
    "reference", [{}, {"reference_file": None}, {"reference_file": " "}]
)
def test_enabled_school_lookup_accepts_an_unset_reference_file(reference):
    validate_config(
        {
            "school_validation": {
                "enabled": True,
                "target_phu": "Example PHU",
                **reference,
            }
        }
    )


@pytest.mark.parametrize(
    "config",
    [
        {"date_as_off": "2026-01-01"},
        {"typst": {"timeout": 60}},
        {"bundling": {"bundle_szie": 10}},
        {"encryption": {"enabled": False, "pasword": {}}},
        {"encryption": {"password": {"templat": "private-value"}}},
        {"school_validation": {"enabled": False, "unknown": 1}},
        {"pipeline": {"after_run": {"unknown": False}}},
        {"pipeline": {"unknown": {}}},
    ],
)
def test_unknown_settings_cannot_be_silently_ignored(config):
    with pytest.raises(ValueError, match="Unknown"):
        validate_config(config)


@pytest.mark.parametrize(
    "config",
    [
        {"encryption": {"enabled": False, "password": {"template": 123}}},
        {"school_validation": {"enabled": False, "column_prefix": False}},
        {"school_validation": {"enabled": False, "reference_file": []}},
        {"typst": {"font_path": []}},
        {"typst": {"bin": " "}},
        {"date_as_of": False},
        {"date_as_of": None},
        {"date_as_of": "2026-02-30"},
        {"date_of_delivery": "20260102"},
        {"bundling": {1: 10}},
        {"bundling": {"group_by": "district"}},
        {"encryption": {"enabled": False, "password": "private-value"}},
        {"encryption": {"enabled": True, "password": {}}},
        {"pipeline": {"after_run": []}},
        {"pipeline": {"after_run": {"remove_artifacts": "yes"}}},
    ],
)
def test_wrong_types_and_dates_are_refused_even_when_feature_is_disabled(config):
    with pytest.raises(ValueError):
        validate_config(config)


def test_empty_dates_and_named_grouping_are_accepted():
    validate_config(
        {"date_as_of": "", "date_of_delivery": "", "bundling": {"group_by": "school"}}
    )


def test_parameter_errors_do_not_copy_password_values():
    for content in (
        "encryption:\n  password:\n    template: [PRIVATE_VALUE\n",
        "encryption:\n  password:\n    template: PRIVATE_VALUE\n    template: OTHER_PRIVATE_VALUE\n",
    ):
        with pytest.raises(ValueError) as failure:
            parse_config(content)
        assert "PRIVATE_VALUE" not in str(failure.value)


def test_yaml_dates_must_be_quoted_and_repeated_fields_are_rejected():
    assert parse_config('date_as_of: "2026-01-01"')["date_as_of"] == "2026-01-01"
    with pytest.raises(ValueError, match="quoted"):
        parse_config("date_as_of: 2026-01-01")
    with pytest.raises(ValueError, match="Repeated field: enabled"):
        parse_config("encryption:\n  enabled: true\n  enabled: false")


@pytest.mark.parametrize(
    "settings",
    [
        None,
        {"enabled": "true"},
        {"enabled": True},
        {"enabled": True, "count": 2},
        {"enabled": True, "count": 2, "unit": "sheets"},
        {"enabled": True, "count": True, "unit": "pages"},
        {"enabled": True, "count": 0, "unit": "pages"},
        {"enabled": True, "count": 1.5, "unit": "pages"},
        {"enabled": False, "count": "2"},
        {"enabled": False, "severity": "warn"},
        {"enabled": True, "count": 2, "unit": "pages", "pad": True},
    ],
)
def test_fixed_notice_length_rejects_missing_or_ambiguous_settings(settings):
    with pytest.raises(ValueError, match="validation.notice_length"):
        validate_config(
            {"bundling": {"bundle_size": 10}, "validation": {"notice_length": settings}}
        )


def test_fixed_notice_length_requires_bundling_and_rejects_client_exceptions():
    length = {"enabled": True, "count": 2, "unit": "pages"}
    with pytest.raises(ValueError, match="requires bundling"):
        validate_config({"validation": {"notice_length": length}})
    validate_config(
        {"bundling": {"bundle_size": 10}, "validation": {"notice_length": length}}
    )
    with pytest.raises(ValueError, match="Rule cannot be adjusted"):
        validate_config(
            {
                "validation": {
                    "clients": [
                        {
                            "selector": {"scheme": "panorama", "value": "0000000001"},
                            "rules": {
                                "delivery.notice_length": {
                                    "enabled": False,
                                    "reason": "Exception",
                                }
                            },
                        }
                    ]
                }
            }
        )
