//! Create numbered bundle sets from the saved original PDFs.
use anyhow::{Context, Result, ensure};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::{Component, Path, PathBuf},
};
use unicode_normalization::UnicodeNormalization;

// Names are compared consistently, without guessing that different names refer to
// the same institution. NFC retains accents while ignoring case and extra spaces.
fn normalized_name(value: &str) -> String {
    value
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .nfc()
        .collect::<String>()
        .to_lowercase()
}

fn institution(entry: &Value, field: &str) -> (String, String) {
    let node = &entry["notice"][field];
    (
        node["id"].as_str().unwrap_or("").trim().to_owned(),
        normalized_name(node["name"].as_str().unwrap_or("")),
    )
}

// A conflict is determined across the entire run, not only a single route or chunk.
fn conflicting_ids(entries: &[Value], field: &str) -> BTreeSet<String> {
    let mut names: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for entry in entries {
        let (id, name) = institution(entry, field);
        if !id.is_empty() && !name.is_empty() {
            names.entry(id).or_default().insert(name);
        }
    }
    names
        .into_iter()
        .filter_map(|(id, names)| (names.len() > 1).then_some(id))
        .collect()
}

fn group_institution(
    entry: &Value,
    field: &str,
    conflicts: &BTreeSet<String>,
    board_conflicts: &BTreeSet<String>,
) -> (String, Option<Value>) {
    let (id, name) = institution(entry, field);
    let row = entry["row_key"].as_str().unwrap_or("");
    if !id.is_empty() && conflicts.contains(&id) {
        let key = if name.is_empty() {
            format!("unknown:{row}")
        } else {
            json!(["conflict", id, name]).to_string()
        };
        return (
            key,
            Some(
                json!({"code":format!("delivery.{field}_identity_conflict"),"stage":"delivery","status":"fail","message":format!("The same {field} ID has conflicting names; review this group")}),
            ),
        );
    }
    if !id.is_empty() {
        return (format!("id:{id}"), None);
    }
    if name.is_empty() {
        return (
            format!("unknown:{row}"),
            Some(
                json!({"code":format!("delivery.{field}_identity_missing"),"stage":"delivery","status":"fail","message":format!("The {field} has no usable ID or name; review this notice")}),
            ),
        );
    }
    // Qualify a school name by its board when available, avoiding collisions
    // between schools of the same name in different boards.
    let board = if field == "school" {
        let (id, name) = institution(entry, "board");
        if !id.is_empty() && board_conflicts.contains(&id) {
            if name.is_empty() {
                json!(["unknown", row]).to_string()
            } else {
                json!(["conflict", id, name]).to_string()
            }
        } else if !id.is_empty() {
            json!(["id", id]).to_string()
        } else {
            json!(["name", name]).to_string()
        }
    } else {
        String::new()
    };
    (
        json!(["name", board, name]).to_string(),
        Some(
            json!({"code":format!("delivery.{field}_identity_fallback"),"stage":"delivery","status":"warn","message":format!("The {field} ID is missing; grouping by normalized name")}),
        ),
    )
}

fn sort_key(entry: &Value) -> (bool, String, bool, String, String) {
    let name = normalized_name(
        entry["notice"]["client_data"]["last_name"]
            .as_str()
            .unwrap_or(""),
    );
    let dob = entry["notice"]["client_data"]["date_of_birth_iso"]
        .as_str()
        .unwrap_or("");
    let valid_dob = chrono::NaiveDate::parse_from_str(dob, "%Y-%m-%d")
        .ok()
        .filter(|date| date.format("%Y-%m-%d").to_string() == dob);
    (
        name.is_empty(),
        name,
        valid_dob.is_none(),
        valid_dob.map(|date| date.to_string()).unwrap_or_default(),
        entry["row_key"].as_str().unwrap_or("").to_owned(),
    )
}

struct BundleJob {
    number: usize,
    route: String,
    group: Vec<String>,
    indices: Vec<usize>,
    name: crate::filenames::Name,
}
fn relative_original(dir: &Path, entry: &Value) -> Result<PathBuf> {
    let path = Path::new(
        entry["original"]["path"]
            .as_str()
            .context("Missing original PDF path")?,
    );
    ensure!(
        path.components().all(|c| matches!(c, Component::Normal(_)))
            && path.starts_with("originals"),
        "Invalid original PDF path"
    );
    Ok(dir.join(path))
}
pub(crate) fn severity(entry: &Value) -> &'static str {
    let mut warning = false;
    if let Some(checks) = entry
        .get("effective_checks")
        .unwrap_or(&entry["checks"])
        .as_array()
    {
        for c in checks {
            match c["status"].as_str() {
                Some("not_run") if c["disabled"] == true => (),
                Some("fail" | "not_run") | None => return "fail",
                Some("warn") => warning = true,
                Some("pass" | "not_applicable") => (),
                _ => return "fail",
            }
        }
    } else {
        return "fail";
    }
    if entry
        .get("compiler_diagnostics")
        .and_then(Value::as_str)
        .is_some_and(|s| !s.is_empty())
    {
        warning = true;
    }
    if warning { "warn" } else { "pass" }
}
/// Summarize the most severe finding across notices and bundles.
pub fn outcome(record: &Value) -> &'static str {
    let mut warning = false;
    for e in record["entries"].as_array().into_iter().flatten() {
        if e["original"]["status"] != "completed"
            || e["encryption"]["status"] == "failed"
            || severity(e) == "fail"
        {
            return "completed_with_failures";
        }
        warning |= severity(e) == "warn";
    }
    for c in record["checks"].as_array().into_iter().flatten() {
        if c["status"] == "fail" {
            return "completed_with_failures";
        }
        warning |= c["status"] == "warn";
    }
    if warning {
        "completed_with_warnings"
    } else {
        "completed"
    }
}

/// Build one new bundle set. Record changes become visible only after all files exist.
pub fn bundle(
    dir: &Path,
    record: &mut Value,
    config: &crate::input::Config,
    workers: usize,
) -> Result<()> {
    bundle_with_progress(dir, record, config, workers, &mut |_, _| {})
}

pub(crate) fn bundle_with_progress(
    dir: &Path,
    record: &mut Value,
    config: &crate::input::Config,
    workers: usize,
    progress: &mut impl FnMut(usize, usize),
) -> Result<()> {
    config.filenames.validate()?;
    let fields = crate::input::grouping_fields(&config.bundling.group_by)?;
    let fixed = crate::input::fixed_pages(config)?;
    // Work on a copy so a failed bundle attempt leaves the saved decisions intact.
    let mut entries = record["entries"]
        .as_array()
        .context("Missing run entries")?
        .clone();
    let mut groups: BTreeMap<(String, Vec<String>), Vec<usize>> = BTreeMap::new();
    let school_conflicts = conflicting_ids(&entries, "school");
    let board_conflicts = conflicting_ids(&entries, "board");
    let mut row_keys = BTreeSet::new();
    for (i, e) in entries.iter_mut().enumerate() {
        let key = e["row_key"].as_str().context("Missing row key")?.to_owned();
        ensure!(row_keys.insert(key), "Duplicate row key");
        e["bundle"] = Value::Null;
        for name in ["checks", "effective_checks"] {
            if let Some(checks) = e[name].as_array_mut() {
                checks.retain(|c| {
                    c["code"] != "delivery.notice_length"
                        && c["code"] != "delivery.original_unusable"
                        && !c["code"].as_str().is_some_and(|code| {
                            ["delivery.school_identity_", "delivery.board_identity_"]
                                .iter()
                                .any(|prefix| code.starts_with(prefix))
                        })
                });
            }
        }
        if e.get("effective_checks").is_none() {
            e["effective_checks"] = e["checks"].clone();
        }
        if e["original"]["status"] != "completed" {
            e["routing"] = json!("failed");
            continue;
        }
        if e.get("hold").is_some_and(|hold| !hold.is_null()) {
            e["routing"] = json!("withheld");
            continue;
        }
        let path = relative_original(dir, e)?;
        let pages = e["original"]["pages"].as_u64().filter(|n| *n > 0);
        let Some(pages) = pages.filter(|_| path.is_file()) else {
            e["effective_checks"].as_array_mut().unwrap().push(json!({"code":"delivery.original_unusable","stage":"delivery","status":"fail","message":"Original PDF is missing or unreadable"}));
            e["routing"] = json!("failed");
            continue;
        };
        if let Some(expected) = fixed {
            if pages != expected {
                e["effective_checks"].as_array_mut().unwrap().push(json!({"code":"delivery.notice_length","stage":"delivery","status":"fail","message":format!("Expected {expected} pages; found {pages}")}));
            }
        }
        let mut key = Vec::new();
        for field in &fields {
            let value = match field.as_str() {
                "school" | "board" if config.bundling.bundle_size > 0 => {
                    let conflicts = if field == "school" {
                        &school_conflicts
                    } else {
                        &board_conflicts
                    };
                    let (value, check) = group_institution(e, field, conflicts, &board_conflicts);
                    if let Some(check) = check {
                        // These findings are recomputed for every new attempt; policy cannot
                        // waive them and the observed and effective records both retain them.
                        e["checks"]
                            .as_array_mut()
                            .context("Missing observed checks")?
                            .push(check.clone());
                        e["effective_checks"]
                            .as_array_mut()
                            .context("Missing effective checks")?
                            .push(check);
                    }
                    value
                }
                "school" | "board" => String::new(),
                "language" => e["assignment"]["language"]
                    .as_str()
                    .or_else(|| e["notice"]["language"].as_str())
                    .unwrap_or("")
                    .to_owned(),
                "notice_variant" => e["assignment"]["version_id"]
                    .as_str()
                    .unwrap_or("")
                    .to_owned(),
                _ => pages.to_string(),
            };
            key.push(value);
        }
        // Readable notices with failures stay available in a separate review bundle.
        let route = if severity(e) == "fail" || e["encryption"]["status"] == "failed" {
            "review"
        } else {
            "deliverable"
        };
        e["routing"] = json!(route);
        groups.entry((route.to_owned(), key)).or_default().push(i);
    }
    if config.bundling.bundle_size == 0 {
        progress(0, 0);
        record["entries"] = Value::Array(entries);
        record["bundles"] = json!([]);
        return Ok(());
    }
    let mut attempt = 1usize;
    let (staging, published, prefix) = loop {
        let prefix = format!("bundles-{attempt:04}");
        let final_path = dir.join(&prefix);
        let tmp = dir.join(format!("{prefix}.incomplete"));
        if !final_path.exists() && !tmp.exists() {
            fs::create_dir(&tmp)?;
            break (tmp, final_path, prefix);
        }
        attempt += 1;
    };
    let result = (|| -> Result<Vec<Value>> {
        let mut jobs = Vec::new();
        let mut serial = 0usize;
        let mut names = crate::filenames::Names::default();
        for ((route, group), mut indices) in groups {
            if config.bundling.sort_by == "last_name_dob" {
                indices.sort_by_cached_key(|&index| sort_key(&entries[index]));
            }
            for (chunk_number, chunk) in indices.chunks(config.bundling.bundle_size).enumerate() {
                serial += 1;
                let fallback = format!(
                    "{}-{serial:04}",
                    if route == "review" {
                        "review"
                    } else {
                        "bundle"
                    }
                );
                let template = config.filenames.bundle_template(route == "review");
                let values = if template.is_some() {
                    crate::filenames::bundle_values(&entries, chunk, chunk_number + 1, &route)
                } else {
                    BTreeMap::new()
                };
                let name = names.resolve(template.as_deref(), &values, &fallback, &fallback);
                jobs.push(BundleJob {
                    number: serial,
                    route: route.clone(),
                    group: group.clone(),
                    indices: chunk.to_vec(),
                    name,
                });
            }
        }
        let work = |job: BundleJob| -> Result<(BundleJob, usize, String)> {
            let paths = job
                .indices
                .iter()
                .map(|i| relative_original(dir, &entries[*i]))
                .collect::<Result<Vec<_>>>()?;
            let dest = staging.join(format!("{}.pdf", job.name.stem));
            let (pages, hash) = crate::pdf::merge_with_hash(&paths, &dest)?;
            Ok((job, pages, hash))
        };
        let mut results = BTreeMap::new();
        let total = jobs.len();
        progress(0, total);
        crate::pool::with_pool(
            workers.max(1).min(jobs.len().max(1)),
            work,
            |sender, receiver| {
                for job in jobs {
                    sender.send(job).context("Bundle worker stopped")?;
                    // Collect ready receipts while submitting larger sets too.
                    for result in receiver.try_iter() {
                        let item = result?;
                        results.insert(item.0.number, item);
                        progress(results.len(), total);
                    }
                }
                drop(sender);
                for result in receiver {
                    let item = result?;
                    results.insert(item.0.number, item);
                    progress(results.len(), total);
                }
                Ok(())
            },
        )?;
        let mut bundles = Vec::new();
        for (job, pages, hash) in results.into_values() {
            let BundleJob {
                route,
                group,
                indices,
                name,
                ..
            } = job;
            let stem = name.stem;
            let path = format!("{prefix}/{stem}.pdf");
            let mut csv = csv::Writer::from_path(staging.join(format!("{stem}.csv")))?;
            csv.write_record([
                "row_key",
                "client_id",
                "notice_start_page",
                "notice_end_page",
                "route",
                "check_code",
                "status",
                "message",
            ])?;
            let mut cursor = 1u64;
            let mut members = Vec::new();
            for i in indices {
                let e = &mut entries[i];
                let count = e["original"]["pages"]
                    .as_u64()
                    .context("Missing original page count")?;
                e["bundle"] = json!({"path":path,"notice_start_page":cursor,"notice_end_page":cursor+count-1});
                members.push(e["row_key"].clone());
                for c in e["effective_checks"].as_array().unwrap() {
                    csv.write_record([
                        e["row_key"].as_str().unwrap_or(""),
                        e["client_id"].as_str().unwrap_or(""),
                        &cursor.to_string(),
                        &(cursor + count - 1).to_string(),
                        &route,
                        c["code"].as_str().unwrap_or(""),
                        c["status"].as_str().unwrap_or(""),
                        c["message"].as_str().unwrap_or(""),
                    ])?;
                }
                cursor += count;
            }
            csv.flush()?;
            ensure!(pages as u64 == cursor - 1, "Bundle page count mismatch");
            bundles.push(json!({"path":path,"csv":format!("{prefix}/{stem}.csv"),"route":route,"group":group,"pages":pages,"members":members,"sha256":hash,"filename_warning":name.warning}));
        }
        Ok(bundles)
    })();
    match result {
        Ok(bundles) => {
            fs::rename(&staging, &published)?;
            let mut checks = record["checks"].as_array().cloned().unwrap_or_default();
            checks.retain(|c| c["code"] != "output.filename_fallback");
            for bundle in &bundles {
                if let Some(message) = bundle["filename_warning"].as_str() {
                    checks.push(crate::filenames::warning(
                        message,
                        bundle["path"].as_str().unwrap(),
                    ));
                }
            }
            record["checks"] = Value::Array(checks);
            record["entries"] = Value::Array(entries);
            record["bundles"] = Value::Array(bundles);
            Ok(())
        }
        Err(error) => {
            let _ = fs::remove_dir_all(&staging);
            Err(error)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn findings_keep_warning_and_failure_distinct() {
        let mut record = json!({"entries":[{"original":{"status":"completed"},"encryption":{"status":"not_requested"},"checks":[{"status":"warn"}]}]});
        assert_eq!(outcome(&record), "completed_with_warnings");
        record["entries"][0]["checks"][0]["status"] = json!("fail");
        assert_eq!(outcome(&record), "completed_with_failures");
        record["entries"][0]["checks"][0]["status"] = json!("not_run");
        assert_eq!(outcome(&record), "completed_with_failures");
    }

    #[test]
    fn grouping_validation_and_fixed_length() -> Result<()> {
        assert_eq!(
            crate::input::grouping_fields(&json!(["School", "page_count"]))?,
            vec!["school", "page_count"]
        );
        assert!(crate::input::grouping_fields(&json!(["school", "SCHOOL"])).is_err());
        let mut c = crate::input::Config::default();
        c.bundling.bundle_size = 100;
        c.validation.insert(
            "notice_length".into(),
            json!({"enabled":true,"count":3,"unit":"pages"}),
        );
        assert_eq!(crate::input::fixed_pages(&c)?, Some(3));
        c.validation.insert(
            "notice_length".into(),
            json!({"enabled":true,"count":0,"unit":"pages"}),
        );
        assert!(crate::input::fixed_pages(&c).is_err());
        Ok(())
    }
}
