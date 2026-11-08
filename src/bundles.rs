//! Create numbered bundle sets from the saved original PDFs.
use anyhow::{Context, Result, ensure};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::{Component, Path, PathBuf},
};

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
    let fields = crate::input::grouping_fields(&config.bundling.group_by)?;
    let fixed = crate::input::fixed_pages(config)?;
    // Work on a copy so a failed bundle attempt leaves the saved decisions intact.
    let mut entries = record["entries"]
        .as_array()
        .context("Missing run entries")?
        .clone();
    let mut groups: BTreeMap<(String, Vec<String>), Vec<usize>> = BTreeMap::new();
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
        // Readable notices with failures stay available in a separate review bundle.
        let route = if severity(e) == "fail" || e["encryption"]["status"] == "failed" {
            "review"
        } else {
            "deliverable"
        };
        e["routing"] = json!(route);
        let key = fields
            .iter()
            .map(|f| match f.as_str() {
                "school" | "board" => e["notice"][f]["id"].as_str().unwrap_or("").to_owned(),
                "language" => e["assignment"]["language"]
                    .as_str()
                    .or_else(|| e["notice"]["language"].as_str())
                    .unwrap_or("")
                    .to_owned(),
                _ => pages.to_string(),
            })
            .collect();
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
        for ((route, group), indices) in groups {
            let size = if config.bundling.bundle_size == 0 {
                indices.len().max(1)
            } else {
                config.bundling.bundle_size
            };
            for chunk in indices.chunks(size) {
                serial += 1;
                jobs.push((serial, route.clone(), group.clone(), chunk.to_vec()));
            }
        }
        let work = |(number, route, group, indices): (usize, String, Vec<String>, Vec<usize>)| -> Result<(usize, String, Vec<String>, Vec<usize>, usize, String)> {
            let name = format!("{}-{number:04}.pdf", if route == "review" { "review" } else { "bundle" });
            let paths = indices.iter().map(|i| relative_original(dir, &entries[*i])).collect::<Result<Vec<_>>>()?;
            let dest = staging.join(&name);
            let (pages, hash) = crate::pdf::merge_with_hash(&paths, &dest)?;
            Ok((number, route, group, indices, pages, hash))
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
                        results.insert(item.0, item);
                        progress(results.len(), total);
                    }
                }
                drop(sender);
                for result in receiver {
                    let item = result?;
                    results.insert(item.0, item);
                    progress(results.len(), total);
                }
                Ok(())
            },
        )?;
        let mut bundles = Vec::new();
        for (number, route, group, indices, pages, hash) in results.into_values() {
            let stem = format!(
                "{}-{number:04}",
                if route == "review" {
                    "review"
                } else {
                    "bundle"
                }
            );
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
            bundles.push(json!({"path":path,"csv":format!("{prefix}/{stem}.csv"),"route":route,"group":group,"pages":pages,"members":members,"sha256":hash}));
        }
        Ok(bundles)
    })();
    match result {
        Ok(bundles) => {
            fs::rename(&staging, &published)?;
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
