//! Stable observed occurrences and their compact policy results.
use anyhow::{Context, Result, ensure};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

pub(crate) fn assign(entry: &mut Value) -> Result<()> {
    let mut next = entry["next_finding_sequence"].as_u64().unwrap_or(1);
    let checks = entry["checks"]
        .as_array_mut()
        .context("Missing observed checks")?;
    let mut used = BTreeSet::new();
    for check in checks.iter() {
        if let Some(key) = check.get("finding_key").and_then(Value::as_str) {
            ensure!(
                !key.is_empty() && used.insert(key.to_owned()),
                "Duplicate or empty observed finding key"
            );
            if let Some(n) = key
                .strip_prefix("check-")
                .and_then(|n| n.parse::<u64>().ok())
            {
                next = next.max(n + 1);
            }
        }
    }
    for check in checks.iter_mut() {
        if check.get("finding_key").is_none() {
            while used.contains(&format!("check-{next:06}")) {
                next += 1;
            }
            let key = format!("check-{next:06}");
            used.insert(key.clone());
            check["finding_key"] = json!(key);
            next += 1;
        }
    }
    entry["next_finding_sequence"] = json!(next);
    Ok(())
}

pub(crate) fn effective(entry: &Value) -> Result<Vec<Value>> {
    let observations = entry["checks"]
        .as_array()
        .context("Missing observed checks")?;
    let results = entry["effective_checks"]
        .as_array()
        .context("Missing effective results")?;
    let mut by_key = BTreeMap::new();
    for result in results {
        let key = result["finding_key"]
            .as_str()
            .filter(|s| !s.is_empty())
            .context("Missing effective finding key")?;
        ensure!(
            by_key.insert(key, result).is_none(),
            "Duplicate effective finding key"
        );
        ensure!(
            result["disabled"].is_boolean(),
            "Invalid effective disabled flag"
        );
        ensure!(
            result["policy_reason"].is_null() || result["policy_reason"].is_string(),
            "Invalid effective policy reason"
        );
        ensure!(
            matches!(
                result["status"].as_str(),
                Some("pass" | "warn" | "fail" | "not_run" | "not_applicable")
            ),
            "Invalid effective status"
        );
        ensure!(
            result.as_object().is_some_and(|v| v.keys().all(|k| [
                "finding_key",
                "status",
                "disabled",
                "policy_reason"
            ]
            .contains(&k.as_str()))),
            "Invalid effective result fields"
        );
    }
    let mut joined = Vec::with_capacity(observations.len());
    for observation in observations {
        ensure!(
            observation["code"]
                .as_str()
                .is_some_and(|code| !code.is_empty()),
            "Invalid observed check code"
        );
        ensure!(
            matches!(
                observation["status"].as_str(),
                Some("pass" | "warn" | "fail" | "not_run" | "not_applicable")
            ),
            "Invalid observed check status"
        );
        let key = observation["finding_key"]
            .as_str()
            .filter(|s| !s.is_empty())
            .context("Missing observed finding key")?;
        let result = by_key.remove(key).context("Missing effective result")?;
        let mut check = observation.clone();
        check["observed_status"] = observation["status"].clone();
        check["status"] = result["status"].clone();
        check["disabled"] = result["disabled"].clone();
        check["policy_reason"] = result["policy_reason"].clone();
        joined.push(check);
    }
    ensure!(by_key.is_empty(), "Effective result has no observation");
    Ok(joined)
}
pub(crate) fn append(entry: &mut Value, mut check: Value) -> Result<()> {
    let n = entry["next_finding_sequence"]
        .as_u64()
        .context("Missing next finding sequence")?;
    let key = format!("check-{n:06}");
    ensure!(
        !entry["checks"]
            .as_array()
            .context("Missing observed checks")?
            .iter()
            .any(|c| c["finding_key"] == key),
        "Finding sequence reuses an observed key"
    );
    check["finding_key"] = json!(key);
    let result =
        json!({"finding_key":key,"status":check["status"],"disabled":false,"policy_reason":null});
    entry["checks"].as_array_mut().unwrap().push(check);
    entry["effective_checks"]
        .as_array_mut()
        .context("Missing effective results")?
        .push(result);
    entry["next_finding_sequence"] = json!(n + 1);
    Ok(())
}

/// Validate persisted facts binding and observed/effective coverage before mutation.
pub(crate) fn validate_record(record: &Value, require_effective: bool) -> Result<()> {
    let entries = record["entries"]
        .as_array()
        .context("Missing saved entries")?;
    let mut row_keys = BTreeSet::new();
    for entry in entries {
        let key = entry["row_key"]
            .as_str()
            .filter(|s| !s.is_empty())
            .context("Missing row key")?;
        ensure!(row_keys.insert(key), "Duplicate row key");
        let observed = entry["checks"]
            .as_array()
            .context("Missing observed checks")?;
        let mut observed_keys = BTreeSet::new();
        for check in observed {
            ensure!(
                check["code"].as_str().is_some_and(|code| !code.is_empty()),
                "Invalid observed check code"
            );
            ensure!(
                matches!(
                    check["status"].as_str(),
                    Some("pass" | "warn" | "fail" | "not_run" | "not_applicable")
                ),
                "Invalid observed check status"
            );
            if let Some(key) = check.get("finding_key") {
                let key = key
                    .as_str()
                    .filter(|s| !s.is_empty())
                    .context("Invalid observed finding key")?;
                ensure!(observed_keys.insert(key), "Duplicate observed finding key");
            }
        }
        if require_effective || entry.get("effective_checks").is_some() {
            let joined = effective(entry)?;
            for check in joined.iter().filter(|check| {
                matches!(
                    check["code"].as_str(),
                    Some(
                        "notice.requirements"
                            | "notice.eligibility"
                            | "data.forecast_coverage"
                            | "content.agent_display"
                            | "render.evidence_failed"
                    )
                )
            }) {
                ensure!(
                    check["status"] == check["observed_status"]
                        && check["disabled"] == false
                        && check["policy_reason"].is_null(),
                    "Mandatory check cannot be overridden"
                );
            }
        }
        if require_effective && entry["original"]["status"] == "completed" {
            let observed = entry["checks"]
                .as_array()
                .context("Missing observed checks")?;
            ensure!(
                !observed.is_empty(),
                "Completed original has no saved checks"
            );
            ensure!(
                entry.get("saved_evidence").is_some()
                    || observed
                        .iter()
                        .any(|check| check["code"] == "render.evidence_failed"
                            && check["status"] == "fail"),
                "Completed original has no validated render evidence"
            );
        }
        if let Some(evidence) = entry.get("saved_evidence") {
            ensure!(
                evidence["saved_evidence_version"] == 1,
                "Unsupported saved evidence version"
            );
            let checks = entry["checks"]
                .as_array()
                .context("Missing observed checks")?;
            let one = |code: &str| -> Result<&Value> {
                let found: Vec<_> = checks
                    .iter()
                    .filter(|check| check["code"] == code)
                    .collect();
                ensure!(
                    found.len() == 1,
                    "Missing or repeated required check: {code}"
                );
                Ok(found[0])
            };
            let requirements = one("notice.requirements")?;
            match evidence["requirements"]["state"].as_str() {
                Some("valid") => {
                    ensure!(
                        requirements["status"] == "pass",
                        "Valid requirements lack a passing check"
                    );
                    ensure!(
                        entry["blocked_checks"]
                            .as_array()
                            .is_some_and(Vec::is_empty),
                        "Valid requirements have blocked checks"
                    );
                    one("notice.eligibility")?;
                    let coverage = one("data.forecast_coverage")?;
                    one("content.agent_display")?;
                    ensure!(
                        coverage["measurements"] == entry["notice"]["forecast_coverage"],
                        "Saved coverage differs from prepared facts"
                    );
                }
                Some("invalid") => {
                    ensure!(
                        requirements["status"] == "fail",
                        "Invalid requirements must fail"
                    );
                    let expected = [
                        "notice.eligibility",
                        "data.forecast_coverage",
                        "content.agent_display",
                    ];
                    let blocked = entry["blocked_checks"]
                        .as_array()
                        .context("Missing blocked checks")?;
                    ensure!(
                        blocked.len() == expected.len()
                            && blocked
                                .iter()
                                .zip(expected)
                                .all(|(item, code)| item["code"] == code),
                        "Invalid blocked checks"
                    );
                }
                _ => anyhow::bail!("Invalid saved requirements state"),
            }
            let notice = entry.get("notice").context("Missing saved facts")?;
            ensure!(
                evidence["facts_sha256"].as_str()
                    == Some(crate::hash(&serde_json::to_vec(notice)?).as_str()),
                "Saved evidence facts digest mismatch"
            );
            ensure!(
                evidence["page_count"] == entry["original"]["pages"],
                "Saved evidence page count mismatch"
            );
            for key in ["row_key", "client_id", "template", "version_id", "language"] {
                ensure!(
                    evidence["identity"][key] == notice[key],
                    "Saved evidence identity mismatch: {key}"
                );
            }
            ensure!(
                evidence["identity"]["row_key"] == entry["row_key"]
                    && evidence["identity"]["client_id"] == entry["client_id"],
                "Saved evidence row identity mismatch"
            );
        }
    }
    if require_effective {
        let active = record["active_bundle_attempt"].as_u64();
        for (index, attempt) in record["delivery_attempts"]
            .as_array()
            .into_iter()
            .flatten()
            .enumerate()
        {
            if attempt["status"] == "failed" {
                continue;
            }
            let is_active = active == Some(index as u64 + 1);
            let rows = attempt["rows"]
                .as_array()
                .context("Missing successful attempt rows")?;
            ensure!(
                rows.len() == entries.len(),
                "Attempt row count differs from saved entries"
            );
            let mut seen = BTreeSet::new();
            for row in rows {
                let key = row["row_key"].as_str().context("Missing attempt row key")?;
                ensure!(seen.insert(key), "Duplicate attempt row key");
                let entry = entries
                    .iter()
                    .find(|entry| entry["row_key"] == key)
                    .context("Unknown attempt row key")?;
                let mut observed: Vec<Value> = entry["checks"]
                    .as_array()
                    .context("Missing observed checks")?
                    .iter()
                    .filter(|check| check["stage"] != "delivery")
                    .cloned()
                    .collect();
                if is_active {
                    observed.extend(
                        entry["checks"]
                            .as_array()
                            .unwrap()
                            .iter()
                            .filter(|check| check["stage"] == "delivery")
                            .cloned(),
                    );
                } else {
                    observed.extend(
                        row["delivery_checks"]
                            .as_array()
                            .context("Missing archived delivery observations")?
                            .iter()
                            .cloned(),
                    );
                }
                effective(&json!({"checks":observed,"effective_checks":row["effective_checks"]}))?;
            }
        }
        if let Some(number) = active {
            ensure!(
                number > 0
                    && record["delivery_attempts"]
                        .as_array()
                        .and_then(|attempts| attempts.get(number as usize - 1))
                        .is_some_and(|attempt| attempt["status"] != "failed"),
                "Invalid active bundle attempt"
            );
        }
    }
    Ok(())
}

pub(crate) fn remove_delivery(entry: &mut Value) -> Result<()> {
    let checks = entry["checks"]
        .as_array_mut()
        .context("Missing observed checks")?;
    let mut removed = BTreeSet::new();
    checks.retain(|c| {
        let delivery = c["stage"] == "delivery";
        if delivery && let Some(k) = c["finding_key"].as_str() {
            removed.insert(k.to_owned());
        }
        !delivery
    });
    entry["effective_checks"]
        .as_array_mut()
        .context("Missing effective results")?
        .retain(|c| {
            !c["finding_key"]
                .as_str()
                .is_some_and(|k| removed.contains(k))
        });
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn delivery_keys_do_not_rebind_and_prior_results_resolve() {
        let mut entry = json!({"checks":[{"code":"encryption.failed","stage":"encryption","status":"fail","message":"Protection failed"}]});
        assign(&mut entry).unwrap();
        entry["effective_checks"] = json!([{"finding_key":entry["checks"][0]["finding_key"],"status":"fail","disabled":false,"policy_reason":null}]);
        append(&mut entry, json!({"code":"delivery.notice_length","stage":"delivery","status":"warn","message":"Review length"})).unwrap();
        let old_observed = entry["checks"].clone();
        let old_results = entry["effective_checks"].clone();
        let old_key = entry["checks"][1]["finding_key"].clone();
        for _ in 0..2 {
            remove_delivery(&mut entry).unwrap();
            append(&mut entry, json!({"code":"delivery.original_unusable","stage":"delivery","status":"fail","message":"Original unavailable"})).unwrap();
            assert_ne!(entry["checks"][1]["finding_key"], old_key);
            assert_eq!(
                entry["checks"][0]["finding_key"],
                old_observed[0]["finding_key"]
            );
        }
        let old = json!({"checks":old_observed,"effective_checks":old_results});
        let resolved = effective(&old).unwrap();
        assert_eq!(resolved[0]["message"], "Protection failed");
        assert_eq!(resolved[1]["message"], "Review length");
        let mut broken = old.clone();
        broken["effective_checks"][1]["finding_key"] =
            broken["effective_checks"][0]["finding_key"].clone();
        assert!(effective(&broken).is_err());
    }
    #[test]
    fn completed_original_requires_bound_evidence_or_explicit_rejection() {
        let mut entry = json!({"row_key":"row-000001","client_id":"1","original":{"status":"completed","pages":1},"checks":[{"finding_key":"check-000001","code":"example","status":"pass"}],"effective_checks":[{"finding_key":"check-000001","status":"pass","disabled":false,"policy_reason":null}]});
        let mut record = json!({"entries":[entry]});
        assert!(validate_record(&record, true).is_err());
        entry = record["entries"][0].clone();
        entry["checks"][0]["code"] = json!("render.evidence_failed");
        entry["checks"][0]["status"] = json!("fail");
        entry["effective_checks"][0]["status"] = json!("fail");
        record["entries"][0] = entry;
        assert!(validate_record(&record, true).is_ok());
        record["entries"][0]["checks"] = json!([]);
        record["entries"][0]["effective_checks"] = json!([]);
        assert!(validate_record(&record, true).is_err());
    }
    #[test]
    fn saved_evidence_requires_every_mandatory_occurrence_and_matching_coverage() {
        let notice = json!({"row_key":"row-000001","client_id":"1","template":"notice.typ","version_id":"v1","language":"en","forecast_coverage":{"missing_diseases":[]}});
        let mut entry = json!({"row_key":"row-000001","client_id":"1","notice":notice,"original":{"status":"completed","pages":1},"blocked_checks":[],
            "saved_evidence":{"saved_evidence_version":1,"facts_sha256":crate::hash(&serde_json::to_vec(&notice).unwrap()),"identity":{"row_key":"row-000001","client_id":"1","template":"notice.typ","version_id":"v1","language":"en"},"page_count":1,"requirements":{"state":"valid"}},
            "checks":[{"code":"notice.requirements","status":"pass"},{"code":"notice.eligibility","status":"pass"},{"code":"data.forecast_coverage","status":"pass","measurements":{"missing_diseases":[]}},{"code":"content.agent_display","status":"not_applicable"}]});
        assign(&mut entry).unwrap();
        entry["effective_checks"] = json!(entry["checks"].as_array().unwrap().iter().map(|c| json!({"finding_key":c["finding_key"],"status":c["status"],"disabled":false,"policy_reason":null})).collect::<Vec<_>>());
        let record = json!({"entries":[entry]});
        assert!(validate_record(&record, true).is_ok());
        let mut missing = record.clone();
        missing["entries"][0]["checks"]
            .as_array_mut()
            .unwrap()
            .remove(1);
        missing["entries"][0]["effective_checks"]
            .as_array_mut()
            .unwrap()
            .remove(1);
        assert!(validate_record(&missing, true).is_err());
        let mut wrong = record;
        wrong["entries"][0]["checks"][2]["measurements"] = json!({});
        assert!(validate_record(&wrong, true).is_err());
    }
}
