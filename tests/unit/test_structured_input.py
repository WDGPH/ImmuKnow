"""Shared files must not hide conflicting fields or unreadable values."""

import pytest

from immuknow.structured_input import parse_json, parse_yaml


@pytest.mark.parametrize(
    "content",
    [
        '{"client_id":"0000000001","client_id":"0000000002"}',
        '[{"rules":{"layout.signature_page":{"enabled":true,"enabled":false}}}]',
    ],
)
def test_json_rejects_repeated_fields_at_every_depth(content):
    with pytest.raises(ValueError, match="Repeated field"):
        parse_json(content)


@pytest.mark.parametrize(
    "content", ['{"value": NaN}', '{"value": Infinity}', '{"value": 1e999}']
)
def test_json_refuses_nonfinite_numbers(content):
    with pytest.raises(ValueError, match="finite"):
        parse_json(content)


@pytest.mark.parametrize(
    "content",
    [
        "rules:\n  signature: warn\n  signature: fail",
        "base: &base {enabled: true}\nrule: {<<: *base, enabled: false}",
        "base: &base {enabled: true}\nrule: {<<: [*base, *base]}",
    ],
)
def test_yaml_rejects_repeated_fields_including_merged_fields(content):
    with pytest.raises(ValueError, match="Repeated field"):
        parse_yaml(content, label="settings.yaml")


@pytest.mark.parametrize(
    "content",
    [
        "value: &value {child: *value}",
        "value: &value [*value]",
        "value: &value {<<: *value}",
    ],
)
def test_yaml_refuses_values_that_refer_back_to_themselves(content):
    with pytest.raises(ValueError, match="refer back"):
        parse_yaml(content, label="settings.yaml")


def test_yaml_aliases_without_conflicts_and_json_bom_are_preserved():
    assert parse_yaml(
        "base: &base {enabled: true}\nrule: {<<: *base, severity: warn}",
        label="settings.yaml",
    ) == {"base": {"enabled": True}, "rule": {"enabled": True, "severity": "warn"}}
    assert parse_json(b'\xef\xbb\xbf{"value":"0000000001"}') == {"value": "0000000001"}


@pytest.mark.parametrize("content", ["value: .nan", "value: .inf", "1: value"])
def test_yaml_refuses_nonfinite_numbers_and_nonstring_field_names(content):
    with pytest.raises(ValueError):
        parse_yaml(content, label="settings.yaml")
