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
                .cloned()
                .unwrap_or_default();
            let absent = checks
                .iter()
                .filter(|c| c["code"] == format!("component.{name}.absent"))
                .count();
            ensure!(
                !measurements.is_empty() == placed.as_bool().unwrap()
                    && absent == usize::from(placed == false),
                "Contradictory placed component"
            );
            for value in measurements {
                bounds(&value, pages)?;
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
