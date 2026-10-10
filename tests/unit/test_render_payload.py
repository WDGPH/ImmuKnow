"""Prepared history facts remain available for shared Typst display choices."""

from copy import deepcopy

import pytest
import yaml

from immuknow.generate_notices import build_notice_data
from immuknow.preprocess import CONFIG_DIR, build_history_items
from immuknow.render_payload import validate_render_payload
from tests.fixtures.sample_input import create_test_input_dataframe
from tests.unit.test_preprocess import build_result

pytestmark = pytest.mark.unit


def prepared_payload(history: str, **defaults):
    frame = create_test_input_dataframe(num_clients=1)
    frame.loc[0, "imms_given"] = history
    config = yaml.safe_load((CONFIG_DIR / "parameters.yaml").read_text())
    config.update(defaults)
    reference = {
        "MMR": ["Measles", "Mumps", "Rubella"],
        "Ig": ["Hepatitis A"],
    }
    client = build_result(frame, reference, ["Not Specified"], config=config)[
        0
    ].clients[0]
    return build_notice_data(client, config)


def test_display_exclusions_do_not_discard_normalized_facts():
    payload = prepared_payload(
        "May 1, 2020 - MMR - Valid; May 1, 2020 - Ig - Invalid; "
        "May 1, 2020 - Not Specified",
        chart_diseases_header=["Measles", "Other"],
        ignore_agents=["Ig"],
    )
    assert payload["history"] == [
        {
            "date_given": "2020-05-01",
            "agent": "MMR",
            "display_name": "MMR",
            "diseases": ["Measles", "Mumps", "Rubella"],
            "validity": "valid",
        },
        {
            "date_given": "2020-05-01",
            "agent": "Ig",
            "display_name": "Ig",
            "diseases": ["Hepatitis A"],
            "validity": "invalid",
        },
    ]
    assert payload["rendering_defaults"]["ignore_agents"] == ["Ig"]
    assert payload["rendering_defaults"]["diseases"] == ["Measles"]
    assert payload["rendering_defaults"]["include_other"] is True
    # Coverage includes the complete source, even the discarded placeholder.
    assert payload["validity_coverage"] == "mixed"


def test_deduplication_keeps_established_status_precedence_and_complete_mappings():
    history = build_history_items(
        "Jun 1, 2021 - MMR - Invalid; May 1, 2020 - MMR - Invalid; "
        "May 1, 2020 - MMR - Valid; May 1, 2020 - MMR; "
        "Jun 1, 2021 - MMR - Valid; Jul 1, 2021 - Uncatalogued #agent",
        [],
        {"MMR": ["Measles", "Mumps", "Rubella"]},
    )
    assert [(item["date_given"], item["validity"]) for item in history] == [
        ("2020-05-01", "unknown"),
        ("2021-06-01", "valid"),
        ("2021-07-01", "unknown"),
    ]
    assert history[-1]["agent"] == "Uncatalogued #agent"
    assert history[-1]["diseases"] == ["Uncatalogued #agent"]
    assert history[0]["diseases"] == ["Measles", "Mumps", "Rubella"]


def test_empty_options_and_false_are_retained_as_explicit_defaults():
    payload = prepared_payload("", chart_diseases_header=[], ignore_agents=[])
    assert payload["rendering_defaults"] == {
        "diseases": [],
        "include_other": False,
        "ignore_agents": [],
        "include_dose": False,
        "show_validity": False,
    }
    assert payload["history"] == []
    assert payload["validity_coverage"] == "all_absent"


def test_coverage_is_cohort_wide_even_when_default_display_is_off():
    frame = create_test_input_dataframe(num_clients=2)
    frame.loc[0, "imms_given"] = "May 1, 2020 - MMR - Valid"
    frame.loc[1, "imms_given"] = "May 1, 2020 - MMR"
    config = yaml.safe_load((CONFIG_DIR / "parameters.yaml").read_text())
    result, _ = build_result(frame, {"MMR": ["Measles"]}, [], config=config)
    assert {client.validity_coverage for client in result.clients} == {"mixed"}
    assert {
        build_notice_data(client, config)["validity_coverage"]
        for client in result.clients
    } == {"mixed"}


def test_known_valid_and_invalid_statuses_are_not_mixed_coverage():
    payload = prepared_payload("May 1, 2020 - MMR - Valid; May 1, 2020 - Ig - Invalid")
    assert payload["validity_coverage"] == "all_present"
    assert [item["validity"] for item in payload["history"]] == ["valid", "invalid"]


@pytest.mark.parametrize("version", [None, True, "1", 0, 2])
def test_unsupported_schema_is_actionable(version):
    payload = prepared_payload("")
    payload["schema_version"] = version
    with pytest.raises(
        ValueError, match="Unsupported rendering schema_version.*expected 1"
    ):
        validate_render_payload(payload)


@pytest.mark.parametrize(
    "path,value,diagnostic",
    [
        (("history", 0, "date_given"), "2020-02-30", "history.0.date_given"),
        (("history", 0, "validity"), "mixed", "history.0.validity"),
        (
            ("rendering_defaults", "show_validity"),
            "false",
            "rendering_defaults.show_validity",
        ),
        (
            ("rendering_defaults", "diseases"),
            ["Measles", "Measles"],
            "rendering_defaults.diseases",
        ),
        (("validity_coverage",), "valid", "validity_coverage"),
    ],
)
def test_malformed_fact_or_default_reports_field(path, value, diagnostic):
    payload = deepcopy(prepared_payload("May 1, 2020 - MMR - Valid"))
    parent = payload
    for part in path[:-1]:
        parent = parent[part]
    parent[path[-1]] = value
    with pytest.raises(ValueError, match=diagnostic):
        validate_render_payload(payload)


def test_missing_history_reports_required_field():
    payload = prepared_payload("")
    del payload["history"]
    with pytest.raises(ValueError, match="history.*required"):
        validate_render_payload(payload)
