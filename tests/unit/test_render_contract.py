"""Native and browser validators share examples of supported and invalid evidence."""

import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import ValidationError

from immuknow.render_contract import validate_render_report
from immuknow.render_payload import validate_render_payload

CASES = json.loads(
    (Path(__file__).parents[1] / "fixtures/render-contract.json").read_text()
)
pytestmark = pytest.mark.unit


@pytest.mark.parametrize("case", CASES["cases"], ids=lambda case: case["name"])
def test_shared_render_contract_cases(case):
    values = deepcopy({"payload": CASES["payload"], "report": CASES["report"]})
    for change in case["changes"]:
        target = values[change["target"]]
        for key in change["path"][:-1]:
            target = target[key]
        key = change["path"][-1]
        if change.get("remove"):
            target.pop(key)
        else:
            target[key] = change["value"]

    def validate():
        validate_render_payload(values["payload"])
        validate_render_report(
            values["report"],
            {
                key: values["payload"][key]
                for key in (
                    "row_key",
                    "template",
                    "client_id",
                    "version_id",
                    "language",
                )
            },
        )

    if case["valid"]:
        validate()
    else:
        with pytest.raises((ValueError, ValidationError)):
            validate()


@pytest.mark.parametrize("number", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_measurements_are_not_accepted(number):
    report = deepcopy(CASES["report"])
    report["measurements"]["header"][0]["title_height_pt"] = number
    with pytest.raises(ValueError):
        validate_render_report(report, report["identity"])
