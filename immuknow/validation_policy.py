"""Evaluate saved findings and bind individual warning acceptance to exact evidence.

Observations stay in entry ``checks``. Every delivery attempt stores a separate
evaluation; accepting a warning never changes either its observation or result.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal

from .data_models import CheckResult
from .render_contract import report_schema
from .structured_input import read_json

POLICY_VERSION = 10


@dataclass(frozen=True)
class RuleDefinition:
    """One check's owner, failure scope and permitted review behavior."""

    code: str
    purpose: str
    evaluator: str
    scope: Literal["original", "encrypted", "batch"] = "original"
    mandatory: bool = False
    adjustable: bool = False


COMPONENT_NAMES = tuple(report_schema()["properties"]["components"]["properties"])


# Integrity findings may never become acceptable warnings, including when an
# authored report labels them as warnings. Only designated checks allow changes
# to their enabled state or severity.
RULES = {
    rule.code: rule
    for rule in (
        RuleDefinition(
            "delivery.notice_length",
            "Every notice in a delivery batch has the configured PDF page count",
            "bundle_pdfs",
            scope="batch",
        ),
        *(
            RuleDefinition(
                item["const"],
                item["description"],
                item["x-evaluator"],
                adjustable=item["x-adjustable"],
            )
            for item in report_schema()["$defs"]["check"]["properties"]["code"]["oneOf"]
        ),
        RuleDefinition(
            "output.readable", "PDF can be opened", "validate_pdfs", mandatory=True
        ),
        RuleDefinition(
            "output.evidence_matches",
            "Evidence matches the selected PDF",
            "validate_pdfs",
            mandatory=True,
        ),
        RuleDefinition(
            "output.client_identity",
            "Visible identity matches the source",
            "validate_pdfs",
            mandatory=True,
        ),
        RuleDefinition(
            "output.text_readable",
            "PDF text can be inspected",
            "validate_pdfs",
            mandatory=True,
        ),
        RuleDefinition(
            "render.evidence_failed",
            "Required render evidence is available",
            "compile_notices",
            mandatory=True,
        ),
        RuleDefinition(
            "rendering.failed",
            "Notice compilation completed",
            "compile_notices",
            mandatory=True,
        ),
        RuleDefinition(
            "rendering.completed",
            "Notice compilation completed",
            "compile_notices",
            mandatory=True,
        ),
        RuleDefinition(
            "encryption.failed",
            "Requested encrypted copy was produced",
            "encrypt_notices",
            scope="encrypted",
            mandatory=True,
        ),
        RuleDefinition(
            "assignment.duplicate_client_id",
            "Source identity is unambiguous",
            "assignment_manifest",
            mandatory=True,
        ),
        RuleDefinition(
            "assignment.missing_assignment",
            "Source row has an explicit assignment",
            "assignment_manifest",
            mandatory=True,
        ),
        RuleDefinition(
            "assignment.ambiguous_assignment",
            "Assignment is unambiguous",
            "assignment_manifest",
            mandatory=True,
        ),
        RuleDefinition(
            "assignment.missing_template",
            "Assigned template exists",
            "assignment_manifest",
            mandatory=True,
        ),
        RuleDefinition(
            "assignment.version_conflict",
            "Source and selected version agree",
            "assignment_manifest",
        ),
        RuleDefinition(
            "assignment.check_unavailable",
            "Selected notice has an applicability check",
            "assignment_manifest",
        ),
        RuleDefinition(
            "assignment.eligibility_conflict",
            "Selected notice applies to supplied facts",
            "assignment_manifest",
        ),
        RuleDefinition(
            "assignment.extra_manifest_row",
            "Manifest rows occur in the source",
            "assignment_manifest",
        ),
        RuleDefinition(
            "data.school_match",
            "School matches the selected reference",
            "validate_schools",
        ),
        RuleDefinition(
            "source.client_id_missing", "External identifier is supplied", "preprocess"
        ),
        RuleDefinition(
            "source.client_id_format",
            "External identifier has the scheme's format",
            "preprocess",
            mandatory=True,
        ),
        RuleDefinition(
            "source.first_name_missing", "First name is supplied", "preprocess"
        ),
        RuleDefinition(
            "source.last_name_missing", "Last name is supplied", "preprocess"
        ),
        RuleDefinition(
            "source.school_name_missing", "School name is supplied", "preprocess"
        ),
        RuleDefinition(
            "source.board_name_missing", "Board name is supplied", "preprocess"
        ),
        RuleDefinition(
            "source.address_incomplete", "Postal address is complete", "preprocess"
        ),
        RuleDefinition(
            "source.age_unknown",
            "Age can be established from supplied dates",
            "preprocess",
        ),
        RuleDefinition(
            "source.overdue_unusable",
            "Supplied forecast can be interpreted",
            "preprocess",
        ),
        RuleDefinition(
            "source.history_invalid",
            "History has valid source syntax",
            "preprocess",
            mandatory=True,
        ),
        RuleDefinition(
            "delivery.group_unknown",
            "Delivery grouping identifier is supplied",
            "bundle_pdfs",
        ),
    )
}

REQUIRED_ORIGINAL_CHECKS = (
    "output.readable",
    "output.evidence_matches",
    "output.client_identity",
)


def policy_snapshot() -> dict[str, Any]:
    """Keep the rule definitions used for each delivery attempt."""
    return {
        "version": POLICY_VERSION,
        "rules": [asdict(rule) for rule in RULES.values()],
    }


def default_settings() -> dict[str, dict[str, Any]]:
    return {
        code: {
            "enabled": True,
            "severity": "warn",
            "sources": {"enabled": "default", "severity": "default"},
            "reasons": {"enabled": "", "severity": ""},
        }
        for code, rule in RULES.items()
        if rule.adjustable
    }


def _validate_rule_changes(changes: Any) -> None:
    if not isinstance(changes, dict):
        raise ValueError("validation.rules must be an object")
    for code, change in changes.items():
        if code not in RULES or not RULES[code].adjustable:
            raise ValueError(f"Rule cannot be adjusted: {code}")
        if not isinstance(change, dict) or set(change) - {
            "enabled",
            "severity",
            "reason",
        }:
            raise ValueError(f"Invalid rule settings: {code}")
        if not ({"enabled", "severity"} & change.keys()):
            raise ValueError(f"Rule needs enabled or severity: {code}")
        if "enabled" in change and type(change["enabled"]) is not bool:
            raise ValueError(f"Rule enabled must be a boolean: {code}")
        if "severity" in change and change["severity"] not in ("warn", "fail"):
            raise ValueError(f"Rule severity must be warn or fail: {code}")
        if not isinstance(change.get("reason"), str) or not change["reason"].strip():
            raise ValueError(f"Rule change requires a reason: {code}")


def validate_policy(policy: Any) -> None:
    """Reject unknown controls and incomplete row selectors before rendering."""
    if not isinstance(policy, dict) or set(policy) - {
        "rules",
        "clients",
        "notice_length",
    }:
        raise ValueError(
            "validation must contain only rules, clients and notice_length"
        )
    notice_length_settings(policy)
    _validate_rule_changes(policy.get("rules", {}))
    clients = policy.get("clients", [])
    if not isinstance(clients, list):
        raise ValueError("validation.clients must be a list")
    for client in clients:
        if not isinstance(client, dict) or set(client) != {"selector", "rules"}:
            raise ValueError("Each validation client needs a selector and rules")
        selector = client["selector"]
        if not isinstance(selector, dict):
            raise ValueError("Validation selector must be an object")
        if set(selector) == {"scheme", "value"}:
            if (
                selector["scheme"] != "panorama"
                or not isinstance(selector["value"], str)
                or not re.fullmatch(r"[0-9]{10}", selector["value"])
            ):
                raise ValueError("Panorama selector requires a ten-digit string")
        elif set(selector) == {"input_sha256", "row_key"}:
            if (
                not isinstance(selector["input_sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", selector["input_sha256"])
                or not isinstance(selector["row_key"], str)
                or not re.fullmatch(r"row-[0-9]{6,}", selector["row_key"])
            ):
                raise ValueError(
                    "Row selector requires the input SHA-256 and source row key"
                )
        else:
            raise ValueError(
                "Select a Panorama identifier or an input SHA-256 and row key"
            )
        _validate_rule_changes(client["rules"])


def notice_length_settings(policy: dict) -> dict[str, Any]:
    """A run-wide page count, disabled unless explicitly requested; never guessed."""
    value = policy.get("notice_length", {})
    if not isinstance(value, dict) or set(value) - {"enabled", "count", "unit"}:
        raise ValueError("validation.notice_length allows only enabled, count and unit")
    enabled = value.get("enabled", False)
    if type(enabled) is not bool:
        raise ValueError("validation.notice_length.enabled must be a boolean")
    if (enabled or "count" in value) and (
        type(value.get("count")) is not int or value["count"] < 1
    ):
        raise ValueError("validation.notice_length.count must be a positive integer")
    if (enabled or "unit" in value) and value.get("unit") != "pages":
        raise ValueError('validation.notice_length.unit must be "pages"')
    return {"enabled": enabled, "count": value.get("count"), "unit": "pages"}


def resolve_policy(policy: dict, record: dict) -> dict[str, dict[str, dict[str, Any]]]:
    """Apply defaults, run settings, then one explicit selection per source row."""
    validate_policy(policy)
    resolved = {entry["row_key"]: default_settings() for entry in record["entries"]}

    def apply(settings: dict, changes: dict, source: str) -> None:
        for code, change in changes.items():
            for field in ("enabled", "severity"):
                if field in change:
                    settings[code][field] = change[field]
                    settings[code]["sources"][field] = source
                    settings[code]["reasons"][field] = change["reason"].strip()

    for settings in resolved.values():
        apply(settings, policy.get("rules", {}), "run")
    selected = set()
    for client in policy.get("clients", []):
        selector = client["selector"]
        if "scheme" in selector:
            matches = [
                entry["row_key"]
                for entry in record["entries"]
                if entry.get("client_id") == selector["value"]
            ]
        else:
            matches = [
                key
                for key in resolved
                if key == selector["row_key"]
                and record["input"].get("sha256") == selector["input_sha256"]
            ]
        if len(matches) != 1:
            raise ValueError("Validation selector must match exactly one source row")
        key = matches[0]
        if key in selected:
            raise ValueError(f"More than one validation selector matches {key}")
        selected.add(key)
        apply(resolved[key], client["rules"], "row")
    return resolved


def read_policy(path: Path) -> dict:
    """Read settings without silently replacing repeated JSON fields."""

    policy = read_json(path)
    validate_policy(policy)
    return policy


def fingerprint(value: Any) -> str:
    """Hash sorted JSON; nonfinite measurements are invalid evidence."""
    return sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class Evaluation:
    """Immutable snapshot of observations, rule identity and resolved results."""

    run_id: str
    row_key: str
    pdf_sha256: str
    evidence_sha256: str
    rules_sha256: str
    settings: dict[str, dict[str, Any]]
    observations: list[dict[str, Any]]
    results: list[dict[str, Any]]
    warning_tokens: dict[str, str]
    failed_checks: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WarningAcceptance:
    """One operator decision for a warning on one unchanged evaluated PDF."""

    token: str
    run_id: str
    row_key: str
    pdf_sha256: str
    evidence_sha256: str
    rules_sha256: str
    warning_code: str
    warning_id: str
    reason: str
    accepted_at: str


def evaluate_original(
    record: dict,
    entry: dict,
    observations: list[dict],
    settings: dict[str, dict[str, Any]] | None = None,
) -> Evaluation:
    """Refuse unknown evidence and enforce mandatory checks at the release boundary."""
    settings = default_settings() if settings is None else settings
    if set(settings) != set(default_settings()):
        raise ValueError(
            "Resolved rule settings must contain exactly the adjustable rules"
        )
    results = []
    for observation in observations:
        if not isinstance(observation, dict):
            raise ValueError("Check evidence must be an object")
        code, status = observation.get("code"), observation.get("status")
        if not isinstance(code, str) or code not in RULES:
            raise ValueError(f"Unknown check rule: {code!r}; checking must be renewed")
        if status not in ("pass", "warn", "fail", "not_applicable", "not_run"):
            raise ValueError(
                f"Invalid check status for {code}; checking must be renewed"
            )
        if any(
            not isinstance(observation.get(key), str) or not observation[key]
            for key in ("stage", "message")
        ):
            raise ValueError(
                f"Malformed check evidence for {code}; checking must be renewed"
            )
        rule = RULES[code]
        if rule.scope == "batch":
            raise ValueError(
                f"Batch checks cannot be supplied as notice evidence: {code}"
            )
        result = deepcopy(observation)
        selected = (
            settings.get(code) if rule.adjustable and not rule.mandatory else None
        )
        if selected is not None and not selected["enabled"]:
            result["status"] = "not_run"
            result["message"] = "Check disabled: " + selected["reasons"]["enabled"]
        elif status == "not_run" or (rule.mandatory and status == "warn"):
            result["status"] = "fail"
            result["message"] += (
                " Required checking is incomplete; this result cannot be waived."
            )
        elif selected is not None and status in ("warn", "fail"):
            result["status"] = selected["severity"]
        results.append(result)
    for code, selected in settings.items():
        if not selected["enabled"] and not any(r["code"] == code for r in results):
            results.append(
                CheckResult(
                    code,
                    "render",
                    "not_run",
                    "Check disabled: " + selected["reasons"]["enabled"],
                ).to_dict()
            )
    for code in REQUIRED_ORIGINAL_CHECKS:
        observed = [result for result in results if result["code"] == code]
        if not observed or any(result["status"] != "pass" for result in observed):
            if not any(result["status"] == "fail" for result in observed):
                results.append(
                    CheckResult(
                        code,
                        "output",
                        "fail",
                        "Required PDF evidence is missing or incomplete; generate and check a new notice.",
                    ).to_dict()
                )
    rules_hash = fingerprint({"definitions": policy_snapshot(), "settings": settings})
    evidence_hash = fingerprint(
        {
            "run_id": record["run_id"],
            "row_key": entry["row_key"],
            "original": entry["original"],
            "source": entry["source"],
            "facts": entry["facts"],
            "assignment": entry["assignment"],
            "resources": record["resources"],
            "input": record["input"].get("sha256"),
            "rules": rules_hash,
            "observations": observations,
            "render_summary": entry.get("render_summary"),
            "results": results,
        }
    )
    warnings = {
        f"{result['code']}:{index + 1}": result["code"]
        for index, result in enumerate(results)
        if result["status"] == "warn" and RULES[result["code"]].scope == "original"
    }
    failures = sorted(
        {
            result["code"]
            for result in results
            if result["status"] == "fail" and RULES[result["code"]].scope == "original"
        }
    )
    return Evaluation(
        record["run_id"],
        entry["row_key"],
        entry["original"]["sha256"],
        evidence_hash,
        rules_hash,
        deepcopy(settings),
        deepcopy(observations),
        results,
        {
            code: fingerprint(
                {"evidence": evidence_hash, "warning_set": warnings, "code": code}
            )
            for code in warnings
        },
        failures,
    )


def accept_warnings(
    record: dict,
    evaluations: dict[str, Evaluation],
    tokens: list[str],
    reason: str | None,
) -> None:
    """Accept exactly the requested current warning tokens, or change nothing."""
    if not tokens:
        return
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Accepting a warning requires a nonempty review reason")
    if len(tokens) != len(set(tokens)):
        raise ValueError("A warning token may be accepted only once per request")
    available = {
        token: (evaluation, code)
        for evaluation in evaluations.values()
        for code, token in evaluation.warning_tokens.items()
    }
    pending = []
    for token in tokens:
        if token not in available:
            raise ValueError(
                "Unknown or stale warning token; inspect the current evaluation before accepting it"
            )
        evaluation, code = available[token]
        pending.append(
            asdict(
                WarningAcceptance(
                    token,
                    evaluation.run_id,
                    evaluation.row_key,
                    evaluation.pdf_sha256,
                    evaluation.evidence_sha256,
                    evaluation.rules_sha256,
                    code.rsplit(":", 1)[0],
                    code,
                    reason.strip(),
                    datetime.now(timezone.utc).isoformat(),
                )
            )
        )
    existing = record.setdefault("warning_acceptances", [])
    for acceptance in pending:
        if not any(item["token"] == acceptance["token"] for item in existing):
            existing.append(acceptance)


def route_original(record: dict, evaluation: Evaluation, *, withheld: bool) -> dict:
    """Make new and saved-run delivery use the same failure-aware decision."""
    accepted = {
        item["token"]
        for item in record.get("warning_acceptances", [])
        if item["run_id"] == evaluation.run_id
        and item["row_key"] == evaluation.row_key
        and item["pdf_sha256"] == evaluation.pdf_sha256
        and item["evidence_sha256"] == evaluation.evidence_sha256
        and item["rules_sha256"] == evaluation.rules_sha256
    }
    unresolved = [
        code
        for code, token in evaluation.warning_tokens.items()
        if token not in accepted
    ]
    if evaluation.failed_checks:
        reason = "Failed checks"
    elif withheld:
        reason = "Operator withheld this original"
    elif unresolved:
        reason = "Warnings awaiting individual acceptance"
    else:
        reason = "All required checks passed and warnings were accepted"
    return {
        "destination": "review"
        if evaluation.failed_checks or withheld or unresolved
        else "delivery",
        "reason": reason,
        "failed_checks": evaluation.failed_checks,
        "unresolved_warnings": unresolved,
        "accepted_warnings": [
            code
            for code, token in evaluation.warning_tokens.items()
            if token in accepted
        ],
        "evaluation_sha256": evaluation.evidence_sha256,
        "withheld": withheld,
    }
