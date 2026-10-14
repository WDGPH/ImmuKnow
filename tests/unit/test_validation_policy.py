"""Individual review decisions bind to exact source, artifact, rules and warnings."""

from copy import deepcopy
from typing import Any

import pytest
from immuknow import validation_policy

from immuknow.validation_policy import (
    REQUIRED_ORIGINAL_CHECKS,
    accept_warnings,
    evaluate_original,
    route_original,
)


def evidence():
    checks: list[dict[str, Any]] = [
        {"code": code, "stage": "output", "status": "pass", "message": "Verified"}
        for code in REQUIRED_ORIGINAL_CHECKS
    ]
    checks += [
        {
            "code": "layout.signature_page",
            "stage": "render",
            "status": "warn",
            "message": "Signature continued",
            "page": 2,
        }
    ]
    entry = {
        "row_key": "row-000001",
        "original": {"sha256": "a" * 64},
        "source": {"row_number": 1},
        "facts": {"sha256": "b" * 64},
        "assignment": {"template": "test.en.typ"},
        "checks": checks,
    }
    record = {
        "run_id": "test-run",
        "input": {"sha256": "c" * 64},
        "resources": {"sha256": "d" * 64},
        "entries": [entry],
        "warning_acceptances": [],
    }
    return record, entry


def test_acceptance_releases_one_warning_without_mutating_observations():
    record, entry = evidence()
    before = deepcopy(entry["checks"])
    evaluation = evaluate_original(record, entry, entry["checks"])
    assert route_original(record, evaluation, withheld=False)["destination"] == "review"
    accept_warnings(
        record,
        {entry["row_key"]: evaluation},
        list(evaluation.warning_tokens.values()),
        "Inspected signature",
    )
    assert (
        route_original(record, evaluation, withheld=False)["destination"] == "delivery"
    )
    assert route_original(record, evaluation, withheld=True)["destination"] == "review"
    assert entry["checks"] == before
    (acceptance,) = record["warning_acceptances"]
    assert acceptance["row_key"] == entry["row_key"]
    assert acceptance["warning_code"] == "layout.signature_page"
    assert acceptance["reason"] == "Inspected signature"


@pytest.mark.parametrize(
    "status", ["fail", "warn", "not_run", "not_applicable", "missing"]
)
def test_mandatory_evidence_cannot_be_waived(status):
    record, entry = evidence()
    if status == "missing":
        entry["checks"].pop(1)
    else:
        entry["checks"][1]["status"] = status
    evaluation = evaluate_original(record, entry, entry["checks"])
    accept_warnings(
        record,
        {entry["row_key"]: evaluation},
        list(evaluation.warning_tokens.values()),
        "Inspected signature",
    )
    assert route_original(record, evaluation, withheld=False)["destination"] == "review"
    assert "output.evidence_matches" in evaluation.failed_checks
    assert all(not key.startswith("output.") for key in evaluation.warning_tokens)


@pytest.mark.parametrize(
    "change", ["pdf", "row", "run", "resources", "facts", "source", "warning"]
)
def test_changed_evidence_invalidates_prior_acceptance(change):
    record, entry = evidence()
    first = evaluate_original(record, entry, entry["checks"])
    tokens = list(first.warning_tokens.values())
    accept_warnings(record, {entry["row_key"]: first}, tokens, "Reviewed")
    if change == "pdf":
        entry["original"]["sha256"] = "e" * 64
    elif change == "row":
        entry["row_key"] = "row-000002"
    elif change == "run":
        record["run_id"] = "another-run"
    elif change == "resources":
        record["resources"]["sha256"] = "e" * 64
    elif change == "facts":
        entry["facts"]["sha256"] = "e" * 64
    elif change == "source":
        entry["source"]["row_number"] = 2
    else:
        entry["checks"][-1]["page"] = 3
    current = evaluate_original(record, entry, entry["checks"])
    assert route_original(record, current, withheld=False)["destination"] == "review"
    with pytest.raises(ValueError, match="stale warning token"):
        accept_warnings(record, {entry["row_key"]: current}, tokens, "Reviewed")
    assert len(record["warning_acceptances"]) == 1


def test_same_rule_on_two_pages_requires_two_individual_acceptances():
    record, entry = evidence()
    entry["checks"].append(entry["checks"][-1] | {"page": 3})
    evaluation = evaluate_original(record, entry, entry["checks"])
    tokens = list(evaluation.warning_tokens.values())
    assert len(tokens) == 2
    accept_warnings(
        record, {entry["row_key"]: evaluation}, tokens[:1], "Page 2 reviewed"
    )
    assert route_original(record, evaluation, withheld=False)["destination"] == "review"
    accept_warnings(
        record, {entry["row_key"]: evaluation}, tokens[1:], "Page 3 reviewed"
    )
    assert (
        route_original(record, evaluation, withheld=False)["destination"] == "delivery"
    )


def test_unknown_or_malformed_evidence_is_never_a_clean_result():
    record, entry = evidence()
    entry["checks"][-1]["status"] = "clean"
    with pytest.raises(ValueError, match="Invalid check status"):
        evaluate_original(record, entry, entry["checks"])
    entry["checks"][-1].update(status="pass", code="authored.unknown")
    with pytest.raises(ValueError, match="Unknown check rule"):
        evaluate_original(record, entry, entry["checks"])


def test_acceptance_request_is_atomic_and_requires_a_reason():
    record, entry = evidence()
    evaluation = evaluate_original(record, entry, entry["checks"])
    tokens = list(evaluation.warning_tokens.values())
    for requested, reason in [(tokens, " "), (tokens + ["stale"], "Reviewed")]:
        with pytest.raises(ValueError):
            accept_warnings(record, {entry["row_key"]: evaluation}, requested, reason)
        assert record["warning_acceptances"] == []


def test_rule_revision_invalidates_acceptance_without_erasing_prior_evaluation(
    monkeypatch,
):
    record, entry = evidence()
    first = evaluate_original(record, entry, entry["checks"])
    before = first.to_dict()
    accept_warnings(
        record,
        {entry["row_key"]: first},
        list(first.warning_tokens.values()),
        "Reviewed",
    )
    monkeypatch.setattr(
        validation_policy, "POLICY_VERSION", validation_policy.POLICY_VERSION + 1
    )
    current = evaluate_original(record, entry, entry["checks"])
    assert current.rules_sha256 != first.rules_sha256
    assert route_original(record, current, withheld=False)["destination"] == "review"
    assert first.to_dict() == before
    assert record["warning_acceptances"]


def test_acceptance_for_one_row_never_releases_another_with_the_same_warning():
    record, first = evidence()
    second = deepcopy(first)
    second["row_key"] = "row-000002"
    record["entries"].append(second)
    evaluations = {
        entry["row_key"]: evaluate_original(record, entry, entry["checks"])
        for entry in record["entries"]
    }
    accept_warnings(
        record,
        evaluations,
        list(evaluations[first["row_key"]].warning_tokens.values()),
        "First row reviewed",
    )
    assert (
        route_original(record, evaluations[first["row_key"]], withheld=False)[
            "destination"
        ]
        == "delivery"
    )
    assert (
        route_original(record, evaluations[second["row_key"]], withheld=False)[
            "destination"
        ]
        == "review"
    )


def test_encryption_failure_does_not_invalidate_print_original():
    record, entry = evidence()
    entry["checks"] = entry["checks"][:-1] + [
        {
            "code": "encryption.failed",
            "stage": "delivery",
            "status": "fail",
            "message": "Password unavailable",
        }
    ]
    evaluation = evaluate_original(record, entry, entry["checks"])
    assert (
        route_original(record, evaluation, withheld=False)["destination"] == "delivery"
    )


@pytest.mark.parametrize(
    "change,status",
    [({}, "warn"), ({"severity": "fail"}, "fail"), ({"enabled": False}, "not_run")],
)
@pytest.mark.parametrize(
    "code",
    [
        "output.qr_destination",
        "output.unrecorded_link",
        "content.link_https",
        "content.multiple_links",
        "layout.client_details_in_window",
        "layout.envelope_window_missing",
    ],
)
def test_destination_and_window_warnings_can_be_configured(change, status, code):
    record, entry = evidence()
    entry["checks"][-1] = {
        "code": code,
        "stage": "output" if code.startswith("output.") else "render",
        "status": "warn",
        "message": "Check the placed content.",
    }
    policy = (
        {"rules": {code: {**change, "reason": "Local notice requirements"}}}
        if change
        else {}
    )
    settings = validation_policy.resolve_policy(policy, record)[entry["row_key"]]
    result = evaluate_original(record, entry, entry["checks"], settings)
    assert result.results[-1]["status"] == status


def test_rule_precedence_and_each_field_reason():
    record, entry = evidence()
    entry["client_id"] = "0000000001"
    policy = {
        "rules": {
            "layout.signature_page": {
                "severity": "fail",
                "reason": "Keep signatures together",
            }
        },
        "clients": [
            {
                "selector": {"scheme": "panorama", "value": "0000000001"},
                "rules": {
                    "layout.signature_page": {
                        "enabled": False,
                        "reason": "Separate signature approved",
                    }
                },
            }
        ],
    }
    settings = validation_policy.resolve_policy(policy, record)[entry["row_key"]]
    selected = settings["layout.signature_page"]
    assert selected["severity"] == "fail"
    assert selected["sources"] == {"enabled": "row", "severity": "run"}
    assert selected["reasons"] == {
        "enabled": "Separate signature approved",
        "severity": "Keep signatures together",
    }
    before = deepcopy(entry["checks"])
    evaluation = evaluate_original(record, entry, entry["checks"], settings)
    assert evaluation.results[-1]["status"] == "not_run"
    assert entry["checks"] == before
    assert (
        route_original(record, evaluation, withheld=False)["destination"] == "delivery"
    )
    assert settings["layout.address_outside_window"]["severity"] == "warn"


def test_policy_change_invalidates_acceptance_and_keeps_prior_results():
    record, entry = evidence()
    first = evaluate_original(record, entry, entry["checks"])
    before = first.to_dict()
    tokens = list(first.warning_tokens.values())
    accept_warnings(record, {entry["row_key"]: first}, tokens, "Reviewed")
    policy = {
        "rules": {
            "layout.signature_page": {"severity": "fail", "reason": "Require one page"}
        }
    }
    settings = validation_policy.resolve_policy(policy, record)[entry["row_key"]]
    current = evaluate_original(record, entry, entry["checks"], settings)
    assert current.failed_checks == ["layout.signature_page"]
    assert route_original(record, current, withheld=False)["destination"] == "review"
    with pytest.raises(ValueError, match="stale"):
        accept_warnings(record, {entry["row_key"]: current}, tokens, "Reviewed")
    assert first.to_dict() == before


@pytest.mark.parametrize(
    "change",
    [
        {"enabled": "false", "reason": "Reviewed"},
        {"severity": "pass", "reason": "Reviewed"},
        {"severity": "warn", "reason": " "},
        {"threshold": 3, "reason": "Reviewed"},
        {"reason": "Reviewed"},
    ],
)
def test_invalid_rule_changes_are_refused(change):
    with pytest.raises(ValueError):
        validation_policy.validate_policy({"rules": {"layout.signature_page": change}})


@pytest.mark.parametrize(
    "code",
    [
        "output.evidence_matches",
        "output.client_identity",
        "output.readable",
        "assignment.duplicate_client_id",
        "source.history_invalid",
        "unknown.rule",
    ],
)
def test_integrity_and_unknown_rules_cannot_be_changed(code):
    with pytest.raises(ValueError, match="cannot be adjusted"):
        validation_policy.validate_policy(
            {"rules": {code: {"enabled": False, "reason": "Reviewed"}}}
        )


def test_explicit_source_row_selector_works_without_external_id_and_refuses_ambiguity():
    record, entry = evidence()
    change = {
        "selector": {
            "input_sha256": record["input"]["sha256"],
            "row_key": entry["row_key"],
        },
        "rules": {"layout.signature_page": {"enabled": False, "reason": "Reviewed"}},
    }
    settings = validation_policy.resolve_policy({"clients": [change]}, record)
    assert not settings[entry["row_key"]]["layout.signature_page"]["enabled"]
    with pytest.raises(ValueError, match="More than one"):
        validation_policy.resolve_policy({"clients": [change, change]}, record)
    change["selector"]["input_sha256"] = "e" * 64
    with pytest.raises(ValueError, match="exactly one"):
        validation_policy.resolve_policy({"clients": [change]}, record)
    entry["client_id"] = "0000000001"
    record["entries"].append(dict(entry, row_key="row-000002"))
    change["selector"] = {"scheme": "panorama", "value": "0000000001"}
    with pytest.raises(ValueError, match="exactly one"):
        validation_policy.resolve_policy({"clients": [change]}, record)


def test_enabled_rule_without_measurement_cannot_be_downgraded_to_warning():
    record, entry = evidence()
    entry["checks"][-1]["status"] = "not_run"
    evaluation = evaluate_original(record, entry, entry["checks"])
    assert evaluation.failed_checks == ["layout.signature_page"]


def test_policy_file_refuses_repeated_fields(tmp_path):
    path = tmp_path / "rules.json"
    path.write_text('{"rules": {}, "rules": {}}')
    with pytest.raises(ValueError, match="Repeated field"):
        validation_policy.read_policy(path)
