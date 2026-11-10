//! Resolve explicit rule settings without changing the observed Typst findings.
use crate::input::Config;
use anyhow::{Context, Result, ensure};
use serde_json::{Map, Value, json};
use std::{collections::BTreeSet, path::Path};

fn changes(value: Option<&Value>, adjustable: &BTreeSet<String>) -> Result<Map<String, Value>> {
    let Some(value) = value else {
        return Ok(Map::new());
    };
    let rules = value
        .as_object()
        .context("validation rules must be an object")?;
    for (code, change) in rules {
        ensure!(
            adjustable.contains(code),
            "Rule {code} cannot be changed; only adjustable render checks support overrides"
        );
        let change = change
            .as_object()
            .context("Rule settings must be an object")?;
        ensure!(
            change
                .keys()
                .all(|k| matches!(k.as_str(), "enabled" | "severity" | "reason")),
            "Unknown rule setting"
        );
        ensure!(
            change.contains_key("enabled") || change.contains_key("severity"),
            "Rule change requires enabled or severity"
        );
        ensure!(
            change
                .get("reason")
                .and_then(Value::as_str)
                .is_some_and(|s| !s.trim().is_empty()),
            "Rule change requires a reason"
        );
        if let Some(v) = change.get("enabled") {
            ensure!(v.is_boolean(), "Rule enabled must be boolean");
        }
        if let Some(v) = change.get("severity") {
            ensure!(
                matches!(v.as_str(), Some("warn" | "fail")),
                "Rule severity must be warn or fail"
            );
        }
    }
    Ok(rules.clone())
}
fn resolve(record: &Value, config: &Config, resources: &Path) -> Result<Vec<Map<String, Value>>> {
    crate::input::validate_bundling(config)?;
    let schema: Value = crate::read_json(&resources.join("typst/report.json"))?;
    // The shared report schema owns which observations may be overridden.
    let adjustable = schema["$defs"]["check"]["properties"]["code"]["oneOf"]
        .as_array()
        .context("Missing render rule definitions")?
        .iter()
        .filter(|r| r["x-adjustable"] == true)
        .filter_map(|r| r["const"].as_str().map(str::to_owned))
        .collect();
    let defaults = changes(config.validation.get("rules"), &adjustable)?;
    let entries = record["entries"]
        .as_array()
        .context("Missing source entries")?;
    let mut result = vec![defaults; entries.len()];
    let clients = config
        .validation
        .get("clients")
        .map(|v| v.as_array().context("validation.clients must be an array"))
        .transpose()?;
    let mut selected = BTreeSet::new();
    for client in clients.into_iter().flatten() {
        let object = client
            .as_object()
            .context("Client policy must be an object")?;
        ensure!(
            object.len() == 2 && object.contains_key("selector") && object.contains_key("rules"),
            "Client policy requires selector and rules"
        );
        let selector = client["selector"]
            .as_object()
            .context("Client selector must be an object")?;
        let matches: Vec<_> = if selector.len() == 2
            && selector.contains_key("scheme")
            && selector.contains_key("value")
        {
            let id = selector["value"]
                .as_str()
                .context("Client selector value must be a string")?;
            ensure!(
                selector["scheme"] == "panorama"
                    && id.len() == 10
                    && id.bytes().all(|b| b.is_ascii_digit()),
                "Panorama selector requires a ten-digit string"
            );
            entries
                .iter()
                .enumerate()
                .filter(|(_, e)| e["client_id"] == id)
                .map(|(i, _)| i)
                .collect()
        } else {
            ensure!(
                selector.len() == 2
                    && selector.contains_key("input_sha256")
                    && selector.contains_key("row_key"),
                "Select a Panorama identifier or input SHA-256 and row key"
            );
            entries
                .iter()
                .enumerate()
                .filter(|(_, e)| {
                    selector["input_sha256"] == record["input"]["sha256"]
                        && selector["row_key"] == e["row_key"]
                })
                .map(|(i, _)| i)
                .collect()
        };
        ensure!(
            matches.len() == 1,
            "Validation selector must match exactly one source row"
        );
        let i = matches[0];
        ensure!(
            selected.insert(i),
            "More than one validation selector matches a source row"
        );
        // Merge individual fields so a client can override one part of a
        // default rule while retaining its other settings.
        for (code, value) in changes(client.get("rules"), &adjustable)? {
            let current = result[i]
                .entry(code)
                .or_insert_with(|| json!({}))
                .as_object_mut()
                .unwrap();
            current.extend(value.as_object().unwrap().clone());
        }
    }
    Ok(result)
}
/// Validate policy and selectors before compilation begins.
pub fn validate(record: &Value, config: &Config, resources: &Path) -> Result<()> {
    resolve(record, config, resources).map(|_| ())
}
/// Keep observations intact and save the decisions used for this bundle attempt.
pub fn apply(record: &mut Value, config: &Config, resources: &Path) -> Result<()> {
    let rules = resolve(record, config, resources)?;
    for (entry, rules) in record["entries"]
        .as_array_mut()
        .unwrap()
        .iter_mut()
        .zip(rules)
    {
        // Delivery observations belong to the previous attempt and are rebuilt below.
        if let Some(checks) = entry["checks"].as_array_mut() {
            checks.retain(|check| check["stage"] != "delivery");
        }
        if entry["encryption"]["status"] == "failed"
            && !entry["checks"].as_array().is_some_and(|checks| {
                checks
                    .iter()
                    .any(|check| check["code"] == "encryption.failed")
            })
        {
            let message = entry["encryption"]["error"]
                .as_str()
                .unwrap_or("Requested encrypted copy was not produced")
                .to_owned();
            entry["checks"].as_array_mut().context("Missing observed checks")?.push(json!({"code":"encryption.failed","stage":"encryption","status":"fail","message":message}));
        }
        crate::checks::assign(entry)?;
        let mut results = Vec::new();
        for check in entry["checks"]
            .as_array()
            .context("Missing observed checks")?
        {
            let mut result = json!({"finding_key":check["finding_key"],"status":check["status"],"disabled":false,"policy_reason":null});
            if let Some(rule) = rules.get(check["code"].as_str().unwrap_or("")) {
                result["policy_reason"] = rule["reason"].clone();
                if rule["enabled"] == false {
                    result["status"] = json!("not_run");
                    result["disabled"] = json!(true);
                } else if matches!(check["status"].as_str(), Some("warn" | "fail")) {
                    if let Some(severity) = rule.get("severity") {
                        result["status"] = severity.clone();
                    }
                }
            }
            results.push(result);
        }
        entry["effective_checks"] = json!(results);
    }
    Ok(())
}
