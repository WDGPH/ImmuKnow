//! Shared schemas plus the native report/source association checks.
use anyhow::{Context, Result, ensure};
use serde_json::Value;
use std::path::Path;

pub struct Validator {
    payload: jsonschema::Validator,
    report: jsonschema::Validator,
    schema: Value,
}
impl Validator {
    pub fn new(core: &Path) -> Result<Self> {
        let payload: Value = crate::read_json(&core.join("schemas/rendering.json"))?;
        let schema: Value = crate::read_json(&core.join("typst/report.json"))?;
        Ok(Self {
            payload: jsonschema::options()
                .should_validate_formats(true)
                .build(&payload)?,
            report: jsonschema::validator_for(&schema)?,
            schema,
        })
    }
    pub fn payload(&self, notice: &Value) -> Result<()> {
        self.payload
            .validate(notice)
            .map_err(|e| anyhow::anyhow!("Payload schema: {e}"))?;
        ensure!(
            notice["template"]
                == format!(
                    "{}.{}.typ",
                    notice["version_id"].as_str().unwrap(),
                    notice["language"].as_str().unwrap()
                ),
            "Notice identity mismatch"
        );
        Ok(())
    }
    pub fn report(&self, reports: &Value, notice: &Value, pages: usize) -> Result<Value> {
        let reports = reports.as_array().context("Reports must be an array")?;
        ensure!(
            reports.len() == 1,
            "Expected exactly one immuknow-report summary"
        );
        let r = &reports[0];
        self.report
            .validate(r)
            .map_err(|e| anyhow::anyhow!("Report schema: {e}"))?;
        ensure!(
            r["notice"] == *notice,
            "Report notice differs from prepared input"
        );
        ensure!(
            r["page_count"].as_u64() == Some(pages as u64),
            "Report/PDF page count mismatch"
        );
        for (k, v) in r["identity"].as_object().unwrap() {
            ensure!(
                notice.get(k) == Some(v),
                "Report belongs to another source row"
            );
        }
        let requirements = &r["requirements"];
        if requirements["state"] == "valid" {
            for key in ["row_key", "client_id", "template", "version_id", "language"] {
                ensure!(
                    requirements["declaration"][key] == notice[key],
                    "Requirements belong to another source row"
                );
            }
            let coverage = r["checks"]
                .as_array()
                .unwrap()
                .iter()
                .find(|check| check["code"] == "data.forecast_coverage")
                .context("Missing coverage finding")?;
            ensure!(
                coverage["measurements"] == notice["forecast_coverage"],
                "Coverage finding differs from prepared measurements"
            );
            if requirements["declaration"]["coverage"] == "agents" {
                ensure!(
                    r["measurements"]["overdue_agents"]
                        .as_array()
                        .is_some_and(|v| v.len() == 1),
                    "Agent requirements need exactly one placed agent component or alternative"
                );
            }
        } else {
            let expected = [
                "notice.eligibility",
                "data.forecast_coverage",
                "content.agent_display",
            ];
            let blocked = r["blocked_checks"].as_array().unwrap();
            ensure!(
                blocked.len() == expected.len()
                    && blocked
                        .iter()
                        .zip(expected)
                        .all(|(item, code)| item["code"] == code),
                "Incorrect blocked-check order"
            );
        }
        fn bounds(v: &Value, pages: usize) -> Result<()> {
            for (k, n) in v.as_object().context("Bounds need an object")? {
                if k == "page" || k.ends_with("_page") {
                    ensure!(
                        n.as_u64().is_some_and(|n| n <= pages as u64),
                        "Report page outside notice"
                    );
                }
            }
            if let (Some(first), Some(last)) = (v["first_page"].as_u64(), v["last_page"].as_u64()) {
                ensure!(first <= last, "Report has reversed page range");
            }
            Ok(())
        }
        let checks = r["checks"].as_array().unwrap();
        // Schema validation establishes shape; these checks tie each component
        // and measurement back to the source row and the rendered document.
        for (name, placed) in r["components"].as_object().unwrap() {
            let measurements = r["measurements"][name]
                .as_array()
                .map_or(&[][..], Vec::as_slice);
            let absent_code = format!("component.{name}.absent");
            let absent = checks.iter().filter(|c| c["code"] == absent_code).count();
            ensure!(
                !measurements.is_empty() == placed.as_bool().unwrap()
                    && absent == usize::from(placed == false),
                "Contradictory placed component"
            );
            for value in measurements {
                bounds(value, pages)?;
                if value.get("row_key").is_some() {
                    for key in ["row_key", "client_id"] {
                        ensure!(
                            value[key] == r["identity"][key],
                            "Placed component belongs to another source row"
                        );
                    }
                }
                ensure!(
                    value.get("source_matches") != Some(&Value::Bool(false)),
                    "Placed component changed source data"
                );
                if name == "overdue_agents" {
                    let source = notice["overdue_agents"]
                        .as_array()
                        .context("Missing source agents")?;
                    let excluded = value["excluded_agents"].as_array().unwrap();
                    let displayed = value["displayed_agents"].as_array().unwrap();
                    ensure!(
                        value["page"]
                            .as_u64()
                            .is_some_and(|page| page > 0 && page <= pages as u64),
                        "Agent component page outside notice"
                    );
                    ensure!(
                        value["source_agents"] == notice["overdue_agents"]
                            && value["source_count"].as_u64() == Some(source.len() as u64),
                        "Agent component source differs from prepared facts"
                    );
                    ensure!(
                        value["displayed_count"].as_u64() == Some(displayed.len() as u64),
                        "Agent displayed count is inconsistent"
                    );
                    ensure!(
                        excluded
                            .array_windows()
                            .all(|[first, second]| first.as_str() < second.as_str())
                            && excluded.iter().all(|item| source.contains(item)),
                        "Agent exclusions are not sorted unique source values"
                    );
                    let replacement = value["replacement"].as_str().unwrap();
                    let visible = value["replacement_visible"].as_bool().unwrap();
                    if replacement == "none" {
                        let mut expected: Vec<&Value> = Vec::new();
                        for agent in source {
                            if !excluded.contains(agent) && !expected.contains(&agent) {
                                expected.push(agent);
                            }
                        }
                        ensure!(
                            !visible && displayed.iter().eq(expected),
                            "Agent display differs from filtered source"
                        );
                    } else {
                        ensure!(
                            visible && displayed.is_empty(),
                            "Agent replacement is empty or has displayed agents"
                        );
                        if replacement == "no_records" {
                            ensure!(
                                notice["has_immunization_records"] == false,
                                "No-records replacement contradicts source"
                            );
                        }
                    }
                }
            }
        }
        for c in checks {
            bounds(c, pages)?;
            if let Some(m) = c.get("measurements") {
                bounds(m, pages)?;
            }
            let rule = self.schema["$defs"]["check"]["properties"]["code"]["oneOf"]
                .as_array()
                .unwrap()
                .iter()
                .find(|rule| rule["const"] == c["code"])
                .unwrap();
            let allowed = rule["x-components"].as_array().unwrap();
            ensure!(
                if allowed.is_empty() {
                    c.get("component").is_none()
                } else {
                    allowed.contains(&c["component"])
                },
                "Wrong component for render check"
            );
            if c["code"].as_str().unwrap().starts_with("component.") {
                ensure!(
                    c["status"] == "not_applicable" && c.get("page").is_none(),
                    "Invalid absent component check"
                );
            } else if !allowed.is_empty() {
                let component = c["component"].as_str().unwrap();
                ensure!(
                    r["components"][component] == true && c.get("page").is_some(),
                    "Check missing placed component/page"
                );
            }
        }
        Ok(r.clone())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn shared_contract_cases() -> Result<()> {
        let root = Path::new(env!("CARGO_MANIFEST_DIR"));
        let core = root.join("resources");
        let corpus: Value = crate::read_json(&root.join("tests/fixtures/render-contract.json"))?;
        let validator = Validator::new(&core)?;
        for case in corpus["cases"].as_array().unwrap() {
            let mut values =
                serde_json::json!({"payload":corpus["payload"],"report":corpus["report"]});
            for change in case["changes"].as_array().unwrap() {
                let mut target = &mut values[change["target"].as_str().unwrap()];
                let path = change["path"].as_array().unwrap();
                for key in &path[..path.len() - 1] {
                    target = match key {
                        Value::String(s) => &mut target[s],
                        _ => &mut target[key.as_u64().unwrap() as usize],
                    };
                }
                let key = path.last().unwrap();
                if change["remove"] == true {
                    match key {
                        Value::String(s) => {
                            target.as_object_mut().unwrap().remove(s);
                        }
                        _ => {
                            target
                                .as_array_mut()
                                .unwrap()
                                .remove(key.as_u64().unwrap() as usize);
                        }
                    }
                } else {
                    match key {
                        Value::String(s) => target[s] = change["value"].clone(),
                        _ => target[key.as_u64().unwrap() as usize] = change["value"].clone(),
                    };
                }
            }
            let result = validator.payload(&values["payload"]).and_then(|()| {
                validator.report(
                    &serde_json::json!([values["report"]]),
                    &values["payload"],
                    values["report"]["page_count"].as_u64().unwrap_or(1) as usize,
                )
            });
            assert_eq!(
                result.is_ok(),
                case["valid"].as_bool().unwrap(),
                "case {}: {:?}",
                case["name"],
                result.err()
            );
        }
        Ok(())
    }
}
