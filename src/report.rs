//! Canonical checkpoints and the two immutable CSV views of a saved run.
use anyhow::{Context, Result};
use serde::Serialize;
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::{BufWriter, Read, Write},
    path::Path,
};

const RECORD_HEADERS: &[&str] = &[
    "run_id",
    "record_revision",
    "bundle_attempt",
    "row_key",
    "source_record",
    "client_id",
    "name",
    "school",
    "notice_variant",
    "language",
    "severity",
    "evaluation_state",
    "route",
    "hold_reason",
    "original_status",
    "original_path",
    "original_pages",
    "protected_status",
    "protected_path",
    "bundle_status",
    "bundle_path",
    "bundle_start_page",
    "bundle_end_page",
];
const FINDING_HEADERS: &[&str] = &[
    "run_id",
    "record_revision",
    "bundle_attempt",
    "scope",
    "attempt_number",
    "row_key",
    "client_id",
    "finding_key",
    "origin",
    "code",
    "observed_status",
    "effective_status",
    "disabled",
    "policy_reason",
    "component",
    "page",
    "message",
    "issue_ids",
    "acknowledged_issue_ids",
];

fn text<'a>(v: &'a Value, key: &str) -> &'a str {
    v.get(key).and_then(Value::as_str).unwrap_or("")
}
fn number(v: &Value) -> String {
    v.as_u64()
        .filter(|n| *n > 0)
        .map(|n| n.to_string())
        .unwrap_or_default()
}
// Spreadsheet software can interpret text after leading whitespace/control characters as a formula.
fn safe(s: &str) -> String {
    if s.trim_start_matches(|c: char| c.is_whitespace() || c.is_control())
        .starts_with(['=', '+', '-', '@'])
    {
        format!("'{s}")
    } else {
        s.to_owned()
    }
}
fn field(v: &Value, key: &str) -> String {
    safe(text(v, key))
}
fn path(v: &Value) -> String {
    if v["status"] == "completed" {
        field(v, "path")
    } else {
        String::new()
    }
}
#[derive(Default, Debug, Clone)]
pub struct Summary {
    pub rows: usize,
    pub severity: BTreeMap<String, usize>,
    pub routes: BTreeMap<String, usize>,
    pub codes: BTreeMap<(String, String), BTreeSet<String>>,
    pub diagnostics: usize,
    pub run_findings: usize,
}
#[derive(Serialize)]
struct RecordRow {
    run_id: String,
    record_revision: u64,
    bundle_attempt: String,
    row_key: String,
    source_record: usize,
    client_id: String,
    name: String,
    school: String,
    notice_variant: String,
    language: String,
    severity: String,
    evaluation_state: String,
    route: String,
    hold_reason: String,
    original_status: String,
    original_path: String,
    original_pages: String,
    protected_status: String,
    protected_path: String,
    bundle_status: String,
    bundle_path: String,
    bundle_start_page: String,
    bundle_end_page: String,
}
#[derive(Serialize)]
struct FindingRow {
    run_id: String,
    record_revision: u64,
    bundle_attempt: String,
    scope: String,
    attempt_number: String,
    row_key: String,
    client_id: String,
    finding_key: String,
    origin: String,
    code: String,
    observed_status: String,
    effective_status: String,
    disabled: bool,
    policy_reason: String,
    component: String,
    page: String,
    message: String,
    issue_ids: String,
    acknowledged_issue_ids: String,
}
fn checks(e: &Value) -> Result<Vec<Value>> {
    if e.get("effective_checks").is_some() {
        crate::checks::effective(e)
    } else {
        // A checkpoint may precede policy evaluation; its observations remain visible.
        Ok(e["checks"]
            .as_array()
            .context("Missing observed checks")?
            .clone())
    }
}
fn evaluation(e: &Value, running: bool) -> &'static str {
    if e["blocked_checks"]
        .as_array()
        .is_some_and(|v| !v.is_empty())
    {
        "blocked"
    } else if e["deferred_checks"]
        .as_array()
        .is_some_and(|v| !v.is_empty())
        || (e["original"]["status"] != "completed"
            && (running
                || matches!(
                    e["original"]["status"].as_str(),
                    Some("not_run" | "pending")
                )))
    {
        "pending"
    } else {
        "complete"
    }
}
fn severity(
    e: &Value,
    cs: &[Value],
    running: bool,
    evaluation: &str,
    artifacts: [&str; 3],
) -> &'static str {
    let pending = evaluation == "pending" || artifacts.contains(&"pending");
    if cs.iter().any(|c| {
        c["status"] == "fail"
            || (c["status"] == "not_run"
                && c["disabled"] != true
                && (!running || evaluation == "blocked"))
    }) || evaluation == "blocked"
        || artifacts.contains(&"failed")
        || (!running && pending)
    {
        "error"
    } else if cs.iter().any(|c| c["status"] == "warn")
        || !text(e, "compiler_diagnostics").is_empty()
    {
        "warning"
    } else if pending {
        "pending"
    } else {
        "clear"
    }
}
fn route(e: &Value, running: bool, original_known_unusable: bool) -> &'static str {
    if !e["hold"].is_null() {
        return "withheld";
    }
    if original_known_unusable || (!running && e["original"]["status"] != "completed") {
        return "report_only";
    }
    match text(e, "routing") {
        "deliverable" => "ready",
        "review" => "review",
        "withheld" => "withheld",
        "failed" => "report_only",
        _ => "undecided",
    }
}
fn finding(
    record: &Value,
    entry: &Value,
    c: &Value,
    scope: &str,
    key: String,
    origin: &str,
    attempt: String,
) -> FindingRow {
    FindingRow {
        run_id: field(record, "run_id"),
        record_revision: record["record_revision"].as_u64().unwrap_or(0),
        bundle_attempt: number(&record["active_bundle_attempt"]),
        scope: scope.into(),
        attempt_number: attempt,
        row_key: field(entry, "row_key"),
        client_id: field(entry, "client_id"),
        finding_key: safe(&key),
        origin: origin.into(),
        code: field(c, "code"),
        observed_status: safe(
            c["observed_status"]
                .as_str()
                .unwrap_or_else(|| text(c, "status")),
        ),
        effective_status: field(c, "status"),
        disabled: c["disabled"] == true,
        policy_reason: field(c, "policy_reason"),
        component: field(c, "component"),
        page: number(&c["page"]),
        message: field(c, "message"),
        issue_ids: "[]".into(),
        acknowledged_issue_ids: "[]".into(),
    }
}
fn project(
    record: &Value,
    mut emit_row: impl FnMut(&RecordRow) -> Result<()>,
    mut emit_finding: impl FnMut(&FindingRow) -> Result<()>,
) -> Result<Summary> {
    let mut summary = Summary::default();
    let running = record["status"] == "running";
    let active = crate::warning_review::validate(record)?.active_ids();
    let issue_scope = crate::warnings::issue_scope(record);
    let protection_requested = record["configured_settings"]["encryption"]["enabled"] == true;
    let grouping = record["configured_settings"]["bundling"]["bundle_size"]
        .as_u64()
        .map(|n| n > 0);
    for (i, e) in record["entries"]
        .as_array()
        .into_iter()
        .flatten()
        .enumerate()
    {
        let ev = evaluation(e, running);
        let row_checks = checks(e)?;
        // A failed preparation has no notice to compile. Other source failures
        // can accompany a valid notice and still produce a reviewable original.
        let preparation_failed = e["notice"].is_null()
            && row_checks.iter().any(|check| {
                check["status"] == "fail"
                    && (text(check, "code").starts_with("source.")
                        || text(check, "code").starts_with("assignment."))
            });
        let original_known_unusable = e["original"]["status"] == "failed"
            || preparation_failed
            || row_checks.iter().any(|check| {
                check["status"] == "fail" && check["code"] == "delivery.original_unusable"
            });
        let route = route(e, running, original_known_unusable);
        let row_key = text(e, "row_key");
        let name = e["notice"]["client_data"]["name"].as_str().unwrap_or("");
        let fallback = [
            text(&e["source"], "first_name"),
            text(&e["source"], "last_name"),
        ]
        .into_iter()
        .filter(|s| !s.is_empty())
        .collect::<Vec<_>>()
        .join(" ");
        let school = e["notice"]["school"]["name"]
            .as_str()
            .unwrap_or_else(|| text(&e["source"], "school_name"));
        let bundle = &e["bundle"];
        let original_usable = e["original"]["status"] == "completed"
            && !row_checks
                .iter()
                .any(|c| c["code"] == "delivery.original_unusable");
        // Protection is a dependent artifact: if preparation or rendering failed
        // before an original existed, an unstarted copy was excluded, not failed.
        let protection_excluded = protection_requested
            && original_known_unusable
            && !original_usable
            && matches!(
                e["encryption"]["status"].as_str(),
                Some("not_run" | "not_requested")
            );
        let original_status = match e["original"]["status"].as_str() {
            Some("completed") if original_usable => "completed",
            Some("completed" | "failed") => "failed",
            _ => "pending",
        };
        let protected_status = if record["configured_settings"]["encryption"]["enabled"] == false {
            "not_requested"
        } else if protection_excluded {
            "excluded"
        } else {
            match e["encryption"]["status"].as_str() {
                Some("completed") => "completed",
                Some("failed") => "failed",
                _ => "pending",
            }
        };
        let held = route == "withheld";
        let bundle_status = if held || route == "report_only" {
            "excluded"
        } else if grouping == Some(false) {
            "not_requested"
        } else if bundle["status"] == "failed" {
            "failed"
        } else if bundle["path"].is_string() {
            "completed"
        } else if (grouping == Some(true) && original_usable) || running {
            "pending"
        } else {
            "not_requested"
        };
        let sev = severity(
            e,
            &row_checks,
            running,
            ev,
            [original_status, protected_status, bundle_status],
        );
        summary.rows += 1;
        *summary.severity.entry(sev.into()).or_default() += 1;
        *summary.routes.entry(route.into()).or_default() += 1;
        emit_row(&RecordRow {
            run_id: field(record, "run_id"),
            record_revision: record["record_revision"].as_u64().unwrap_or(0),
            bundle_attempt: number(&record["active_bundle_attempt"]),
            row_key: safe(row_key),
            source_record: i + 1,
            client_id: field(e, "client_id"),
            name: safe(if name.is_empty() { &fallback } else { name }),
            school: safe(school),
            notice_variant: field(&e["assignment"], "version_id"),
            language: field(&e["assignment"], "language"),
            severity: sev.into(),
            evaluation_state: ev.into(),
            route: route.into(),
            hold_reason: field(&e["hold"], "reason"),
            original_status: original_status.into(),
            original_path: if original_usable {
                path(&e["original"])
            } else {
                String::new()
            },
            original_pages: if original_usable {
                number(&e["original"]["pages"])
            } else {
                String::new()
            },
            protected_status: protected_status.into(),
            protected_path: if protected_status == "completed" {
                path(&e["encryption"])
            } else {
                String::new()
            },
            bundle_status: bundle_status.into(),
            bundle_path: if bundle_status == "completed" {
                field(bundle, "path")
            } else {
                String::new()
            },
            bundle_start_page: if bundle_status == "completed" {
                number(&bundle["notice_start_page"])
            } else {
                String::new()
            },
            bundle_end_page: if bundle_status == "completed" {
                number(&bundle["notice_end_page"])
            } else {
                String::new()
            },
        })?;
        for (j, c) in row_checks.iter().enumerate() {
            let observed = c["observed_status"]
                .as_str()
                .unwrap_or_else(|| text(c, "status"));
            let effective = text(c, "status");
            if matches!(observed, "warn" | "fail")
                || matches!(effective, "warn" | "fail")
                || (effective == "not_run" && c["disabled"] != true && !running)
            {
                let mut result = finding(
                    record,
                    e,
                    c,
                    "row",
                    c["finding_key"]
                        .as_str()
                        .map(str::to_owned)
                        .unwrap_or_else(|| format!("check-{:06}", j + 1)),
                    "check",
                    String::new(),
                );
                let ids = crate::warnings::issue_ids(issue_scope.as_deref(), c)?;
                let acknowledged: Vec<_> = ids.iter().filter(|id| active.contains(*id)).collect();
                result.issue_ids = serde_json::to_string(&ids)?;
                result.acknowledged_issue_ids = serde_json::to_string(&acknowledged)?;
                emit_finding(&result)?;
            }
            if matches!(effective, "warn" | "fail") {
                summary
                    .codes
                    .entry((effective.into(), text(c, "code").into()))
                    .or_default()
                    .insert(row_key.into());
            }
        }
        for (artifact, failed, explained, message) in [
            (
                "original",
                e["original"]["status"] == "failed",
                preparation_failed
                    || row_checks.iter().any(|c| {
                        c["status"] == "fail"
                            && matches!(text(c, "code"), "rendering.failed" | "output.readable")
                    }),
                "Original PDF was not produced",
            ),
            (
                "protected",
                protection_requested && e["encryption"]["status"] == "failed",
                row_checks
                    .iter()
                    .any(|c| text(c, "code") == "encryption.failed"),
                "Requested protected PDF was not produced",
            ),
            (
                "bundle",
                bundle_status == "failed",
                false,
                "Bundle assembly failed for this record",
            ),
        ] {
            if failed && !explained {
                let check = json!({"code":format!("artifact.{artifact}_failed"),"status":"fail","message":message});
                summary
                    .codes
                    .entry(("fail".into(), format!("artifact.{artifact}_failed")))
                    .or_default()
                    .insert(row_key.into());
                emit_finding(&finding(
                    record,
                    e,
                    &check,
                    "row",
                    format!("artifact-{artifact}"),
                    "artifact",
                    String::new(),
                ))?;
            }
        }
        if !text(e, "compiler_diagnostics").is_empty() {
            summary.diagnostics += 1;
            let c = json!({"code":"compiler.diagnostics","status":"warn","message":text(e,"compiler_diagnostics")});
            emit_finding(&finding(
                record,
                e,
                &c,
                "row",
                "compiler-000001".into(),
                "compiler",
                String::new(),
            ))?;
        }
    }
    for (i, c) in record["checks"]
        .as_array()
        .into_iter()
        .flatten()
        .enumerate()
    {
        if matches!(text(c, "status"), "warn" | "fail") {
            summary.run_findings += 1;
            emit_finding(&finding(
                record,
                &Value::Null,
                c,
                "run",
                format!("check-{:06}", i + 1),
                "check",
                String::new(),
            ))?;
        }
    }
    if let Some(error) = record["error"].as_str().filter(|error| {
        !record["delivery_attempts"]
            .as_array()
            .into_iter()
            .flatten()
            .any(|attempt| attempt["error"].as_str() == Some(*error))
    }) {
        summary.run_findings += 1;
        emit_finding(&finding(
            record,
            &Value::Null,
            &json!({"code":"run.failed","status":"fail","message":error}),
            "run",
            "run-error".into(),
            "artifact",
            String::new(),
        ))?;
    }
    for (i, attempt) in record["delivery_attempts"]
        .as_array()
        .into_iter()
        .flatten()
        .enumerate()
    {
        if let Some(error) = attempt["error"].as_str() {
            summary.run_findings += 1;
            emit_finding(&finding(
                record,
                &Value::Null,
                &json!({"code":"delivery.attempt_failed","status":"fail","message":error}),
                "attempt",
                format!("attempt-{:06}", i + 1),
                "artifact",
                (i + 1).to_string(),
            ))?;
        }
    }
    Ok(summary)
}
pub fn summary(record: &Value) -> Summary {
    project(record, |_| Ok(()), |_| Ok(())).unwrap_or_default()
}
fn save(dir: &Path, record: &Value) -> Result<()> {
    crate::atomic_write(&dir.join("run.json"), |file| {
        let mut out = BufWriter::with_capacity(64 * 1024, file);
        serde_json::to_writer(&mut out, record)?;
        out.flush()?;
        Ok(())
    })
}
/// Save one semantic checkpoint; exports are invalidated before presentation is written.
pub fn checkpoint(dir: &Path, record: &mut Value) -> Result<()> {
    record["record_revision"] = json!(record["record_revision"].as_u64().unwrap_or(0) + 1);
    record["exports"] = Value::Null;
    save(dir, record)
}
fn hash_file(path: &Path) -> Result<String> {
    use sha2::{Digest, Sha256};
    let mut file = fs::File::open(path)?;
    let mut digest = Sha256::new();
    let mut buffer = [0u8; 64 * 1024];
    loop {
        let n = file.read(&mut buffer)?;
        if n == 0 {
            break;
        }
        digest.update(&buffer[..n]);
    }
    Ok(crate::hex_digest(&digest.finalize()))
}
fn current_valid(dir: &Path, record: &Value) -> bool {
    let e = &record["exports"];
    if e["record_revision"] != record["record_revision"] || e["schema_version"] != 1 {
        return false;
    }
    ["records", "findings"].iter().all(|name| {
        let Some(path) = e[*name]["path"].as_str() else {
            return false;
        };
        if !Path::new(path)
            .components()
            .all(|part| matches!(part, std::path::Component::Normal(_)))
        {
            return false;
        }
        let Some(expected) = e[*name]["sha256"].as_str().filter(|s| {
            s.len() == 64
                && s.bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        }) else {
            return false;
        };
        hash_file(&dir.join(path)).ok().as_deref() == Some(expected)
    })
}
/// Publish a complete immutable pair, then select it in the canonical record.
pub fn publish(dir: &Path, record: &mut Value) -> Result<()> {
    publish_with_hook(dir, record, |_| Ok(())).context(
        "Canonical state was saved, but CSV exports are unavailable; run warnings RUN --refresh",
    )
}
pub(crate) fn publish_with_hook(
    dir: &Path,
    record: &mut Value,
    hook: impl Fn(&str) -> Result<()>,
) -> Result<()> {
    if current_valid(dir, record) {
        return Ok(());
    }
    record["exports"] = Value::Null;
    save(dir, record)?;
    let mut n = 1u64;
    let (staging, published, stem) = loop {
        let stem = format!("reports-{n:04}");
        let staging = dir.join(format!("{stem}.incomplete"));
        let published = dir.join(&stem);
        if !staging.exists() && !published.exists() {
            break (staging, published, stem);
        }
        n += 1;
    };
    fs::create_dir(&staging)?;
    let write = || -> Result<()> {
        let mut records = csv::WriterBuilder::new()
            .has_headers(false)
            .terminator(csv::Terminator::CRLF)
            .from_path(staging.join("records.csv"))?;
        let mut output = csv::WriterBuilder::new()
            .has_headers(false)
            .terminator(csv::Terminator::CRLF)
            .from_path(staging.join("findings.csv"))?;
        records.write_record(RECORD_HEADERS)?;
        output.write_record(FINDING_HEADERS)?;
        project(
            record,
            |row| {
                records.serialize(row)?;
                Ok(())
            },
            |finding| {
                output.serialize(finding)?;
                Ok(())
            },
        )?;
        records.flush()?;
        hook("between_csv_flushes")?;
        output.flush()?;
        drop(records);
        drop(output);
        Ok(())
    };
    write().context(
        "Canonical state was saved, but CSV generation failed; run warnings RUN --refresh",
    )?;
    fs::rename(&staging, &published).context(
        "Canonical state was saved, but CSV publication failed; run warnings RUN --refresh",
    )?;
    hook("after_directory_rename").context(
        "Canonical state was saved, but CSV publication failed; run warnings RUN --refresh",
    )?;
    hook("before_pointer_update").context(
        "Canonical state was saved, but CSV selection failed; run warnings RUN --refresh",
    )?;
    record["exports"] = json!({"schema_version":1,"record_revision":record["record_revision"],
        "records":{"path":format!("{stem}/records.csv"),"sha256":hash_file(&published.join("records.csv"))?},
        "findings":{"path":format!("{stem}/findings.csv"),"sha256":hash_file(&published.join("findings.csv"))?}});
    let revision = record["record_revision"].clone();
    let exports = record["exports"].clone();
    if let Some(attempt) = record["delivery_attempts"]
        .as_array_mut()
        .and_then(|attempts| {
            attempts
                .iter_mut()
                .find(|attempt| attempt["record_revision"] == revision)
        })
    {
        attempt["exports"] = exports;
    }
    if let Err(error) = save(dir, record) {
        record["exports"] = Value::Null;
        return Err(error.context(
            "Canonical state was saved, but CSV selection failed; run warnings RUN --refresh",
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use tempfile::tempdir;

    fn fixture() -> Value {
        json!({"run_schema_version":2,"run_id":"fictional","record_revision":0,"exports":null,"status":"completed_with_warnings",
            "resources":{"sha256":"a".repeat(64)},"project_resources":{"templates":{"notice.typ":"b".repeat(64)}},
            "configured_settings":{"encryption":{"enabled":false},"bundling":{"bundle_size":20}},"active_bundle_attempt":1,
            "entries":[{"row_key":"row-000001","client_id":"001","source":{"first_name":"  =Zoë","last_name":"Example","school_name":"École, Nord"},
                "original":{"status":"completed","path":"originals/1.pdf","pages":2},"encryption":{"status":"not_requested"},
                "routing":"deliverable","bundle":{"path":"bundles-0001/1.pdf","notice_start_page":1,"notice_end_page":2},
                "checks":[{"finding_key":"check-000001","code":"content.link_https","status":"warn","message":"Review, \"link\"\nnext line","subjects":[{"kind":"url","urls":["http://example.test"]}]}],
                "effective_checks":[{"finding_key":"check-000001","status":"warn","disabled":false,"policy_reason":null}],"blocked_checks":[],"deferred_checks":[]}],
            "checks":[],"delivery_attempts":[]})
    }
    #[test]
    fn csv_pair_joins_rows_quotes_unicode_and_escapes_formula_text() {
        let dir = tempdir().unwrap();
        let mut record = fixture();
        checkpoint(dir.path(), &mut record).unwrap();
        publish(dir.path(), &mut record).unwrap();
        let records = dir
            .path()
            .join(record["exports"]["records"]["path"].as_str().unwrap());
        let findings = dir
            .path()
            .join(record["exports"]["findings"]["path"].as_str().unwrap());
        let mut records = csv::Reader::from_path(records).unwrap();
        let row = records
            .deserialize::<BTreeMap<String, String>>()
            .next()
            .unwrap()
            .unwrap();
        assert_eq!(row["client_id"], "001");
        assert_eq!(row["name"], "'  =Zoë Example");
        assert_eq!(row["school"], "École, Nord");
        assert_eq!(row["severity"], "warning");
        assert_eq!(row["bundle_start_page"], "1");
        assert_eq!(row["bundle_end_page"], "2");
        let mut findings = csv::Reader::from_path(findings).unwrap();
        let finding = findings
            .deserialize::<BTreeMap<String, String>>()
            .next()
            .unwrap()
            .unwrap();
        assert_eq!(finding["row_key"], row["row_key"]);
        assert_eq!(finding["message"], "Review, \"link\"\nnext line");
        assert_eq!(
            serde_json::from_str::<Vec<String>>(&finding["issue_ids"])
                .unwrap()
                .len(),
            1
        );
    }
    #[test]
    fn refresh_recovers_each_interrupted_publication_without_revising_state() {
        for stage in [
            "between_csv_flushes",
            "after_directory_rename",
            "before_pointer_update",
        ] {
            let dir = tempdir().unwrap();
            let mut record = fixture();
            record["warning_reviews"] = json!({"schema_version":1,"history":[]});
            checkpoint(dir.path(), &mut record).unwrap();
            let revision = record["record_revision"].clone();
            assert!(
                publish_with_hook(dir.path(), &mut record, |at| if at == stage {
                    anyhow::bail!("injected {stage}")
                } else {
                    Ok(())
                })
                .is_err()
            );
            let mut saved: Value = crate::read_json(&dir.path().join("run.json")).unwrap();
            assert!(saved["exports"].is_null());
            assert_eq!(saved["record_revision"], revision);
            publish(dir.path(), &mut saved).unwrap();
            assert_eq!(saved["record_revision"], revision);
            assert!(current_valid(dir.path(), &saved));
            let exports = saved["exports"].clone();
            publish(dir.path(), &mut saved).unwrap();
            assert_eq!(saved["exports"], exports);
            fs::remove_file(
                dir.path()
                    .join(exports["records"]["path"].as_str().unwrap()),
            )
            .unwrap();
            saved["exports"]["records"]
                .as_object_mut()
                .unwrap()
                .remove("sha256");
            assert!(!current_valid(dir.path(), &saved));
            publish(dir.path(), &mut saved).unwrap();
            assert_ne!(saved["exports"], exports);
            assert_eq!(saved["record_revision"], revision);
        }
    }
    #[test]
    fn pending_failed_artifacts_and_invalid_effective_results_are_not_clear() {
        let mut record = fixture();
        record["status"] = json!("running");
        record["entries"][0]["checks"] = json!([]);
        record["entries"][0]["effective_checks"] = json!([]);
        record["entries"][0]["original"] = json!({"status":"not_run"});
        record["entries"][0]["routing"] = Value::Null;
        assert_eq!(summary(&record).severity["pending"], 1);
        record["status"] = json!("failed");
        assert_eq!(summary(&record).severity["error"], 1);
        record["entries"][0]["original"] =
            json!({"status":"completed","path":"originals/1.pdf","pages":2});
        record["configured_settings"]["encryption"]["enabled"] = json!(true);
        record["entries"][0]["encryption"] = json!({"status":"pending"});
        assert_eq!(summary(&record).severity["error"], 1);
        record["entries"][0]["effective_checks"] = json!([{"finding_key":"unknown","status":"pass","disabled":false,"policy_reason":null}]);
        assert!(project(&record, |_| Ok(()), |_| Ok(())).is_err());
    }
    // A completed v2 saved row with the same fact binding and mandatory checks
    // used by rebundle and warning-review validation.
    fn mixed_row(index: usize) -> Value {
        let key = format!("row-{index:06}");
        let id = if index == 2 || index == 3 {
            "0000000002".to_owned()
        } else {
            format!("{index:010}")
        };
        let notice = json!({"row_key":key,"client_id":id,"template":"notice.en.typ","version_id":"notice","language":"en",
            "client_data":{"name":format!("Fictional {index}")},"school":{"name":"École, Nord"},"forecast_coverage":{"missing_diseases":[],"extra_diseases":[],"unmapped_agents":[]}});
        let mut entry = json!({"row_key":key,"client_id":id,"notice":notice,"source":{"client_id":id},
            "assignment":{"version_id":"notice","language":"en"},
            "original":{"status":"completed","path":format!("originals/{index}.pdf"),"pages":2},
            "encryption":{"status":"completed","path":format!("encrypted/{index}.pdf")},
            "routing":"deliverable","bundle":{"path":"bundles-0001/ready.pdf","notice_start_page":index*2-1,"notice_end_page":index*2},
            "blocked_checks":[],"deferred_checks":[],
            "saved_evidence":{"saved_evidence_version":1,"facts_sha256":crate::hash(&serde_json::to_vec(&notice).unwrap()),
              "identity":{"row_key":key,"client_id":id,"template":"notice.en.typ","version_id":"notice","language":"en"},"page_count":2,"requirements":{"state":"valid"}},
            "checks":[{"code":"notice.requirements","status":"pass"},{"code":"notice.eligibility","status":"pass"},
              {"code":"data.forecast_coverage","status":"pass","measurements":notice["forecast_coverage"]},
              {"code":"content.agent_display","status":"not_applicable"}]});
        match index {
            2 => entry["checks"].as_array_mut().unwrap().extend([
                json!({"code":"layout.repeat","status":"warn","component":"history","page":1,"message":"First page"}),
                json!({"code":"layout.repeat","status":"warn","component":"history","page":2,"message":"Second page"})]),
            3 => {
                entry["checks"].as_array_mut().unwrap().extend([
                    json!({"code":"layout.repeat","status":"warn","page":1,"message":"Review"}),
                    json!({"code":"layout.disabled","status":"warn","message":"Disabled warning"})]);
                entry["hold"] = json!({"reason":"Awaiting review"}); entry["routing"] = json!("withheld"); entry["bundle"] = Value::Null;
            }
            4 => {
                entry.as_object_mut().unwrap().remove("notice"); entry.as_object_mut().unwrap().remove("saved_evidence");
                entry["checks"] = json!([{"code":"source.history_unusable","status":"fail","message":"History could not be prepared"}]);
                entry["original"] = json!({"status":"not_run"});
                entry["encryption"] = json!({"status":"not_run"}); entry["routing"] = json!("failed"); entry["bundle"] = Value::Null;
                entry["deferred_checks"] = json!(["notice.requirements","notice.eligibility","data.forecast_coverage","content.agent_display"]);
            }
            5 => {
                entry["checks"].as_array_mut().unwrap().push(json!({"code":"encryption.failed","stage":"encryption","status":"fail","message":"Protection failed"}));
                entry["encryption"] = json!({"status":"failed","error":"Protection failed"}); entry["routing"] = json!("review");
                entry["bundle"] = json!({"path":"bundles-0001/review.pdf","notice_start_page":1,"notice_end_page":2});
            }
            6 => entry["checks"].as_array_mut().unwrap().push(json!({"code":"layout.disabled","status":"warn","message":"Disabled warning"})),
            7 => {
                entry["checks"] = json!([{"code":"notice.requirements","status":"fail","message":"Invalid requirements"}]);
                entry["saved_evidence"]["requirements"] = json!({"state":"invalid","errors":[{"code":"missing","count":0}]});
                entry["blocked_checks"] = json!([{"code":"notice.eligibility","blocked_by":"notice.requirements","reason":"Invalid notice requirements"},{"code":"data.forecast_coverage","blocked_by":"notice.requirements","reason":"Invalid notice requirements"},{"code":"content.agent_display","blocked_by":"notice.requirements","reason":"Invalid notice requirements"}]);
                entry["routing"] = json!("review"); entry["bundle"] = json!({"path":"bundles-0001/review.pdf","notice_start_page":3,"notice_end_page":4});
            }
            8 => entry["compiler_diagnostics"] = json!("font warning, line one\nline two"),
            _ => (),
        }
        crate::checks::assign(&mut entry).unwrap();
        entry["effective_checks"] = json!(entry["checks"].as_array().unwrap().iter().map(|check| {
            let disabled = check["code"] == "layout.disabled";
            json!({"finding_key":check["finding_key"],"status":if disabled { json!("not_run") } else { check["status"].clone() },"disabled":disabled,"policy_reason":if disabled { json!("Reviewed rule") } else { Value::Null }})
        }).collect::<Vec<_>>());
        entry
    }

    fn mixed_record() -> Value {
        let entries: Vec<_> = (1..=8).map(mixed_row).collect();
        let attempt_rows: Vec<_> = entries.iter().map(|entry| json!({"row_key":entry["row_key"],"effective_checks":entry["effective_checks"],"hold":entry["hold"],"routing":entry["routing"],"bundle":entry["bundle"]})).collect();
        json!({"run_schema_version":2,"run_id":"fictional-mixed","record_revision":7,"exports":null,"status":"completed_with_failures",
            "resources":{"sha256":"a".repeat(64)},"project_resources":{"templates":{"notice.en.typ":"b".repeat(64)}},
            "configured_settings":{"encryption":{"enabled":true},"bundling":{"bundle_size":20}},
            "active_bundle_attempt":1,"entries":entries,
            "checks":[{"code":"setup.warning","status":"warn","message":"Review configuration"}],
            "delivery_attempts":[{"status":"completed_with_failures","rows":attempt_rows,"bundles":[]},
              {"status":"failed","error":"Later bundle attempt failed","planned_members":["row-000001"]}]})
    }

    #[test]
    fn mixed_saved_run_summary_and_csv_use_rows_effective_results_and_attempt_scope() {
        let dir = tempdir().unwrap();
        let mut record = mixed_record();
        crate::checks::validate_record(&record, true)
            .expect("fixture must be a valid saved v2 run");
        let totals = summary(&record);
        assert_eq!(totals.rows, 8);
        assert_eq!(
            totals.severity,
            BTreeMap::from([
                ("clear".into(), 2),
                ("error".into(), 3),
                ("warning".into(), 3)
            ])
        );
        assert_eq!(
            totals.routes,
            BTreeMap::from([
                ("ready".into(), 4),
                ("report_only".into(), 1),
                ("review".into(), 2),
                ("withheld".into(), 1)
            ])
        );
        assert_eq!(
            totals.codes[&("warn".into(), "layout.repeat".into())],
            BTreeSet::from(["row-000002".into(), "row-000003".into()])
        );
        assert!(
            !totals
                .codes
                .contains_key(&("warn".into(), "layout.disabled".into()))
        );
        assert_eq!(
            totals.codes[&("fail".into(), "source.history_unusable".into())],
            BTreeSet::from(["row-000004".into()])
        );
        assert_eq!(
            totals.codes[&("fail".into(), "encryption.failed".into())],
            BTreeSet::from(["row-000005".into()])
        );
        assert_eq!(totals.diagnostics, 1);
        assert_eq!(totals.run_findings, 2);
        publish(dir.path(), &mut record).unwrap();
        let read = |name: &str| -> Vec<BTreeMap<String, String>> {
            let path = dir
                .path()
                .join(record["exports"][name]["path"].as_str().unwrap());
            csv::Reader::from_path(path)
                .unwrap()
                .deserialize()
                .map(Result::unwrap)
                .collect()
        };
        let rows = read("records");
        let findings = read("findings");
        assert_eq!(rows.len(), 8);
        assert_eq!(
            findings.len(),
            11,
            "each actionable occurrence is emitted once"
        );
        assert_eq!(rows[1]["client_id"], rows[2]["client_id"]);
        assert_ne!(rows[1]["row_key"], rows[2]["row_key"]);
        assert_eq!(
            (
                rows[2]["severity"].as_str(),
                rows[2]["route"].as_str(),
                rows[2]["bundle_status"].as_str()
            ),
            ("warning", "withheld", "excluded")
        );
        assert_eq!(
            (
                rows[3]["severity"].as_str(),
                rows[3]["route"].as_str(),
                rows[3]["original_path"].as_str()
            ),
            ("error", "report_only", "")
        );
        assert_eq!(rows[3]["original_status"], "pending");
        assert_eq!(
            rows[3]["protected_status"], "excluded",
            "a dependent copy was never attempted without an original"
        );
        assert_eq!(
            (
                rows[4]["protected_status"].as_str(),
                rows[4]["route"].as_str()
            ),
            ("failed", "review")
        );
        assert_eq!(rows[4]["bundle_start_page"], "1");
        assert_eq!(rows[4]["bundle_end_page"], "2");
        assert_eq!(
            (
                rows[6]["severity"].as_str(),
                rows[6]["evaluation_state"].as_str()
            ),
            ("error", "blocked")
        );
        let repeated: Vec<_> = findings
            .iter()
            .filter(|f| f["row_key"] == "row-000002" && f["code"] == "layout.repeat")
            .collect();
        assert_eq!(repeated.len(), 2);
        assert_ne!(repeated[0]["finding_key"], repeated[1]["finding_key"]);
        assert_eq!(
            (repeated[0]["page"].as_str(), repeated[1]["page"].as_str()),
            ("1", "2")
        );
        let disabled = findings
            .iter()
            .find(|f| f["row_key"] == "row-000006" && f["code"] == "layout.disabled")
            .unwrap();
        assert_eq!(
            (
                disabled["observed_status"].as_str(),
                disabled["effective_status"].as_str(),
                disabled["disabled"].as_str(),
                disabled["policy_reason"].as_str()
            ),
            ("warn", "not_run", "true", "Reviewed rule")
        );
        assert!(
            !findings
                .iter()
                .any(|f| f["row_key"] == "row-000004" && f["code"] == "artifact.protected_failed")
        );
        assert_eq!(
            findings
                .iter()
                .filter(|f| f["origin"] == "compiler" && f["row_key"] == "row-000008")
                .count(),
            1
        );
        assert_eq!(
            findings.iter().find(|f| f["origin"] == "compiler").unwrap()["message"],
            "font warning, line one\nline two"
        );
        assert_eq!(
            findings
                .iter()
                .filter(|f| f["scope"] == "run" && f["code"] == "setup.warning")
                .count(),
            1
        );
        assert_eq!(
            findings
                .iter()
                .filter(|f| f["scope"] == "attempt"
                    && f["attempt_number"] == "2"
                    && f["code"] == "delivery.attempt_failed")
                .count(),
            1
        );
        assert!(findings.iter().all(|f| f["run_id"] == "fictional-mixed"
            && f["record_revision"] == "7"
            && f["bundle_attempt"] == "1"));
    }

    #[test]
    fn partial_and_empty_projections_keep_pending_and_zero_denominators() {
        let mut record = mixed_record();
        record["status"] = json!("running");
        record["active_bundle_attempt"] = Value::Null;
        record["delivery_attempts"] = json!([]);
        let mut pending = mixed_row(1);
        pending["original"] = json!({"status":"not_run"});
        pending["encryption"] = json!({"status":"not_run"});
        pending["routing"] = Value::Null;
        pending["bundle"] = Value::Null;
        pending["checks"] = json!([]);
        pending.as_object_mut().unwrap().remove("effective_checks");
        pending.as_object_mut().unwrap().remove("saved_evidence");
        pending["deferred_checks"] = json!(["notice.requirements"]);
        let mut warned = pending.clone();
        warned["row_key"] = json!("row-000002");
        warned["checks"] =
            json!([{"code":"layout.pending","status":"warn","message":"Already observed"}]);
        record["entries"] = json!([pending, warned]);
        crate::checks::validate_record(&record, false).unwrap();
        let mut rows = Vec::new();
        let summary = project(
            &record,
            |row| {
                rows.push(serde_json::to_value(row)?);
                Ok(())
            },
            |_| Ok(()),
        )
        .unwrap();
        assert_eq!(summary.rows, 2);
        assert_eq!(summary.severity["pending"], 1);
        assert_eq!(summary.severity["warning"], 1);
        assert_eq!(summary.routes["undecided"], 2);
        assert_eq!(rows[0]["evaluation_state"], "pending");
        assert_eq!(rows[1]["evaluation_state"], "pending");
        record["entries"] = json!([]);
        let empty = super::summary(&record);
        assert_eq!(empty.rows, 0);
        assert!(empty.severity.is_empty());
        assert!(empty.routes.is_empty());
    }

    #[test]
    fn failed_initial_bundle_marks_planned_rows_without_inventing_paths() {
        let mut record = mixed_record();
        record["entries"] = json!([mixed_row(1), mixed_row(2)]);
        record["status"] = json!("failed");
        record["active_bundle_attempt"] = Value::Null;
        for entry in record["entries"].as_array_mut().unwrap() {
            entry["bundle"] = json!({"status":"failed","error":"Bundle failed"});
        }
        record["delivery_attempts"] = json!([{"status":"failed","error":"Bundle failed","planned_members":["row-000001","row-000002"]}]);
        crate::checks::validate_record(&record, true).unwrap();
        let mut rows = Vec::new();
        let mut findings = Vec::new();
        let totals = project(
            &record,
            |row| {
                rows.push(serde_json::to_value(row)?);
                Ok(())
            },
            |finding| {
                findings.push(serde_json::to_value(finding)?);
                Ok(())
            },
        )
        .unwrap();
        assert_eq!(totals.severity["error"], 2);
        assert_eq!(
            totals.codes[&("fail".into(), "artifact.bundle_failed".into())].len(),
            2
        );
        assert!(rows.iter().all(|row| row["bundle_status"] == "failed"
            && row["bundle_path"] == ""
            && row["bundle_start_page"] == ""
            && row["bundle_end_page"] == ""));
        assert_eq!(
            findings
                .iter()
                .filter(|finding| finding["code"] == "artifact.bundle_failed")
                .count(),
            2
        );
    }
    #[test]
    fn missing_original_does_not_hide_an_existing_protected_copy() {
        let mut record = mixed_record();
        let entry = &mut record["entries"][0];
        crate::checks::append(entry, json!({"code":"delivery.original_unusable","stage":"delivery","status":"fail","message":"Original no longer available"})).unwrap();
        entry["routing"] = json!("failed");
        entry["bundle"] = Value::Null;
        record["delivery_attempts"][0]["rows"][0]["effective_checks"] =
            record["entries"][0]["effective_checks"].clone();
        let mut rows = Vec::new();
        let mut findings = Vec::new();
        project(
            &record,
            |row| {
                rows.push(serde_json::to_value(row)?);
                Ok(())
            },
            |finding| {
                findings.push(serde_json::to_value(finding)?);
                Ok(())
            },
        )
        .unwrap();
        assert_eq!(rows[0]["original_status"], "failed");
        assert_eq!(rows[0]["original_path"], "");
        assert_eq!(rows[0]["protected_status"], "completed");
        assert_eq!(rows[0]["protected_path"], "encrypted/1.pdf");
        assert!(
            !findings
                .iter()
                .any(|finding| finding["row_key"] == "row-000001"
                    && finding["code"] == "artifact.protected_failed")
        );
    }
    #[test]
    fn global_setup_failure_does_not_invent_an_original_failure_for_each_row() {
        let mut record = mixed_record();
        record["status"] = json!("failed");
        record["error"] = json!("Configuration could not be loaded");
        record["configured_settings"] = Value::Null;
        record["active_bundle_attempt"] = Value::Null;
        record["delivery_attempts"] = json!([]);
        record["checks"] = json!([]);
        for entry in record["entries"].as_array_mut().unwrap() {
            entry["original"] = json!({"status":"not_run"});
            entry["encryption"] = json!({"status":"not_run"});
            entry["checks"] = json!([]);
            entry.as_object_mut().unwrap().remove("effective_checks");
            entry.as_object_mut().unwrap().remove("saved_evidence");
            for field in [
                "notice",
                "assignment",
                "blocked_checks",
                "deferred_checks",
                "compiler_diagnostics",
                "hold",
            ] {
                entry.as_object_mut().unwrap().remove(field);
            }
            entry["bundle"] = Value::Null;
            entry["routing"] = Value::Null;
        }
        crate::checks::validate_record(&record, false).unwrap();
        let mut rows = Vec::new();
        let mut findings = Vec::new();
        let totals = project(
            &record,
            |row| {
                rows.push(serde_json::to_value(row)?);
                Ok(())
            },
            |finding| {
                findings.push(serde_json::to_value(finding)?);
                Ok(())
            },
        )
        .unwrap();
        assert_eq!(totals.rows, 8);
        assert_eq!(totals.severity["error"], 8);
        assert!(rows.iter().all(|row| row["original_status"] == "pending"
            && row["original_path"] == ""
            && row["evaluation_state"] == "pending"
            && row["route"] == "report_only"));
        assert_eq!(
            findings
                .iter()
                .filter(|finding| finding["scope"] == "run" && finding["code"] == "run.failed")
                .count(),
            1
        );
        assert!(
            !findings.iter().any(|finding| finding["scope"] == "row"
                && finding["code"] == "artifact.original_failed")
        );
    }
    #[test]
    fn terminated_unstarted_protection_is_pending_and_excluded_bundle_has_no_range() {
        let mut record = mixed_record();
        record["status"] = json!("failed");
        record["entries"][0]["encryption"] = json!({"status":"not_run"});
        // Exercise the projection guard even if stale page data is present.
        record["entries"][2]["bundle"] =
            json!({"path":"bundles-0001/old.pdf","notice_start_page":5,"notice_end_page":6});
        let mut rows = Vec::new();
        let mut findings = Vec::new();
        let totals = project(
            &record,
            |row| {
                rows.push(serde_json::to_value(row)?);
                Ok(())
            },
            |finding| {
                findings.push(serde_json::to_value(finding)?);
                Ok(())
            },
        )
        .unwrap();
        assert_eq!(rows[0]["severity"], "error");
        assert_eq!(rows[0]["protected_status"], "pending");
        assert!(
            !findings
                .iter()
                .any(|finding| finding["row_key"] == "row-000001"
                    && finding["code"] == "artifact.protected_failed")
        );
        assert_eq!(rows[2]["bundle_status"], "excluded");
        assert_eq!(rows[2]["bundle_path"], "");
        assert_eq!(rows[2]["bundle_start_page"], "");
        assert_eq!(rows[2]["bundle_end_page"], "");
        assert_eq!(totals.rows, 8);
        record["status"] = json!("running");
        record["configured_settings"]["bundling"]["bundle_size"] = json!(0);
        let mut running_rows = Vec::new();
        project(
            &record,
            |row| {
                running_rows.push(serde_json::to_value(row)?);
                Ok(())
            },
            |_| Ok(()),
        )
        .unwrap();
        assert_eq!(running_rows[0]["severity"], "pending");
        assert_eq!(running_rows[0]["protected_status"], "pending");
    }
    #[test]
    fn terminated_before_requested_bundling_reports_pending_delivery() {
        let mut record = mixed_record();
        record["status"] = json!("failed");
        record["error"] = json!("Later processing stopped");
        record["active_bundle_attempt"] = Value::Null;
        record["delivery_attempts"] = json!([]);
        record["entries"] = json!([mixed_row(1)]);
        record["entries"][0]["routing"] = Value::Null;
        record["entries"][0]["bundle"] = Value::Null;
        let mut rows = Vec::new();
        let mut findings = Vec::new();
        let totals = project(
            &record,
            |row| {
                rows.push(serde_json::to_value(row)?);
                Ok(())
            },
            |finding| {
                findings.push(serde_json::to_value(finding)?);
                Ok(())
            },
        )
        .unwrap();
        assert_eq!(totals.severity["error"], 1);
        assert_eq!(rows[0]["evaluation_state"], "complete");
        assert_eq!(rows[0]["route"], "undecided");
        assert_eq!(rows[0]["bundle_status"], "pending");
        assert_eq!(rows[0]["bundle_path"], "");
        assert_eq!(rows[0]["bundle_start_page"], "");
        assert_eq!(rows[0]["bundle_end_page"], "");
        assert!(
            !findings
                .iter()
                .any(|finding| finding["code"] == "artifact.bundle_failed")
        );
        record["status"] = json!("running");
        let mut running_rows = Vec::new();
        let running = project(
            &record,
            |row| {
                running_rows.push(serde_json::to_value(row)?);
                Ok(())
            },
            |_| Ok(()),
        )
        .unwrap();
        assert_eq!(running.severity["pending"], 1);
        assert_eq!(running_rows[0]["bundle_status"], "pending");
        crate::checks::append(
            &mut record["entries"][0],
            json!({"code":"layout.example","status":"warn","message":"Warning already observed"}),
        )
        .unwrap();
        let warned = summary(&record);
        assert_eq!(
            warned.severity["warning"], 1,
            "observed warnings take precedence over pending delivery"
        );
        record["status"] = json!("failed");
        record["configured_settings"]["bundling"]["bundle_size"] = json!(0);
        let mut ungrouped_rows = Vec::new();
        project(
            &record,
            |row| {
                ungrouped_rows.push(serde_json::to_value(row)?);
                Ok(())
            },
            |_| Ok(()),
        )
        .unwrap();
        assert_eq!(ungrouped_rows[0]["bundle_status"], "not_requested");
    }
    #[test]
    fn artifact_statuses_drive_severity_consistently_across_run_states() {
        // status, original, protection requested/status, grouping, bundled, expected severity and artifact statuses
        let cases = [
            (
                "running",
                "not_run",
                false,
                "not_requested",
                false,
                false,
                "pending",
                "pending",
                "not_requested",
                "not_requested",
            ),
            (
                "failed",
                "not_run",
                false,
                "not_requested",
                false,
                false,
                "error",
                "pending",
                "not_requested",
                "excluded",
            ),
            (
                "running",
                "completed",
                true,
                "not_run",
                false,
                false,
                "pending",
                "completed",
                "pending",
                "not_requested",
            ),
            (
                "failed",
                "completed",
                true,
                "not_run",
                false,
                false,
                "error",
                "completed",
                "pending",
                "not_requested",
            ),
            (
                "running",
                "completed",
                false,
                "not_requested",
                true,
                false,
                "pending",
                "completed",
                "not_requested",
                "pending",
            ),
            (
                "failed",
                "completed",
                false,
                "not_requested",
                true,
                false,
                "error",
                "completed",
                "not_requested",
                "pending",
            ),
            (
                "completed",
                "completed",
                true,
                "completed",
                true,
                true,
                "clear",
                "completed",
                "completed",
                "completed",
            ),
            (
                "completed_with_failures",
                "completed",
                true,
                "failed",
                false,
                false,
                "error",
                "completed",
                "failed",
                "not_requested",
            ),
        ];
        for (
            run_status,
            original,
            requested,
            protected,
            grouping,
            bundled,
            expected,
            original_expected,
            protected_expected,
            bundle_expected,
        ) in cases
        {
            let mut record = mixed_record();
            record["status"] = json!(run_status);
            record["entries"] = json!([mixed_row(1)]);
            record["configured_settings"]["encryption"]["enabled"] = json!(requested);
            record["configured_settings"]["bundling"]["bundle_size"] =
                json!(if grouping { 20 } else { 0 });
            let entry = &mut record["entries"][0];
            entry["original"]["status"] = json!(original);
            entry["encryption"]["status"] = json!(protected);
            if !bundled {
                entry["bundle"] = Value::Null;
            }
            if original != "completed" || (grouping && !bundled) {
                entry["routing"] = Value::Null;
            }
            let mut rows = Vec::new();
            project(
                &record,
                |row| {
                    rows.push(serde_json::to_value(row)?);
                    Ok(())
                },
                |_| Ok(()),
            )
            .unwrap();
            let row = &rows[0];
            assert_eq!(
                row["severity"], expected,
                "{run_status}/{original}/{protected}/{grouping}"
            );
            assert_eq!(row["original_status"], original_expected);
            assert_eq!(row["protected_status"], protected_expected);
            assert_eq!(row["bundle_status"], bundle_expected);
        }
    }
    #[test]
    fn artifact_status_priorities_hold_for_running_and_terminated_records() {
        for run_status in ["running", "failed"] {
            for case in [
                "original_failed",
                "protected_failed",
                "bundle_failed",
                "held",
                "completed",
            ] {
                let mut record = mixed_record();
                record["status"] = json!(run_status);
                record["entries"] = json!([mixed_row(1)]);
                let entry = &mut record["entries"][0];
                let (severity, original, protected, bundle) = match case {
                    "original_failed" => {
                        entry["original"] = json!({"status":"failed","error":"Compilation failed"});
                        entry["encryption"] = json!({"status":"not_run"});
                        entry["routing"] = json!("failed");
                        entry["bundle"] = Value::Null;
                        entry.as_object_mut().unwrap().remove("saved_evidence");
                        entry["checks"] = json!([{"code":"rendering.failed","status":"fail","message":"Compilation failed"}]);
                        crate::checks::assign(entry).unwrap();
                        entry["effective_checks"] = json!([{"finding_key":entry["checks"][0]["finding_key"],"status":"fail","disabled":false,"policy_reason":null}]);
                        ("error", "failed", "excluded", "excluded")
                    }
                    "protected_failed" => {
                        entry["encryption"] =
                            json!({"status":"failed","error":"Protection failed"});
                        ("error", "completed", "failed", "completed")
                    }
                    "bundle_failed" => {
                        entry["bundle"] = json!({"status":"failed","error":"Bundle failed"});
                        ("error", "completed", "completed", "failed")
                    }
                    "held" => {
                        entry["hold"] = json!({"reason":"Review"});
                        entry["routing"] = json!("withheld");
                        entry["bundle"] = Value::Null;
                        ("clear", "completed", "completed", "excluded")
                    }
                    "completed" => ("clear", "completed", "completed", "completed"),
                    _ => unreachable!(),
                };
                let mut rows = Vec::new();
                project(
                    &record,
                    |row| {
                        rows.push(serde_json::to_value(row)?);
                        Ok(())
                    },
                    |_| Ok(()),
                )
                .unwrap();
                assert_eq!(rows[0]["severity"], severity, "{run_status}/{case}");
                assert_eq!(rows[0]["original_status"], original, "{run_status}/{case}");
                assert_eq!(
                    rows[0]["protected_status"], protected,
                    "{run_status}/{case}"
                );
                assert_eq!(rows[0]["bundle_status"], bundle, "{run_status}/{case}");
            }
        }
    }
    #[test]
    fn running_checkpoint_distinguishes_known_no_pdf_from_reviewable_source_failure() {
        let mut record = mixed_record();
        record["status"] = json!("running");
        record["active_bundle_attempt"] = Value::Null;
        record["delivery_attempts"] = json!([]);
        let mut compile_failed = mixed_row(1);
        compile_failed["original"] = json!({"status":"failed","error":"Compilation failed"});
        compile_failed["encryption"] = json!({"status":"not_run"});
        compile_failed["routing"] = Value::Null;
        compile_failed["bundle"] = Value::Null;
        compile_failed
            .as_object_mut()
            .unwrap()
            .remove("saved_evidence");
        compile_failed["checks"] =
            json!([{"code":"rendering.failed","status":"fail","message":"Compilation failed"}]);
        compile_failed
            .as_object_mut()
            .unwrap()
            .remove("effective_checks");
        let mut prep_failed = mixed_row(4);
        prep_failed["routing"] = Value::Null;
        prep_failed
            .as_object_mut()
            .unwrap()
            .remove("effective_checks");
        let mut ready = mixed_row(1);
        ready["row_key"] = json!("row-000003");
        ready["notice"]["row_key"] = json!("row-000003");
        ready["deferred_checks"] = json!([
            "notice.requirements",
            "notice.eligibility",
            "data.forecast_coverage",
            "content.agent_display"
        ]);
        ready["original"] = json!({"status":"not_run"});
        ready["encryption"] = json!({"status":"not_run"});
        ready["routing"] = Value::Null;
        ready["bundle"] = Value::Null;
        crate::checks::append(
            &mut ready,
            json!({"code":"source.client_id_format","status":"fail","message":"Invalid ID"}),
        )
        .unwrap();
        // An actual pre-render checkpoint has no saved compiled evidence yet.
        ready.as_object_mut().unwrap().remove("saved_evidence");
        ready.as_object_mut().unwrap().remove("effective_checks");
        record["entries"] = json!([compile_failed, prep_failed, ready]);
        crate::checks::validate_record(&record, false).unwrap();
        let mut rows = Vec::new();
        project(
            &record,
            |row| {
                rows.push(serde_json::to_value(row)?);
                Ok(())
            },
            |_| Ok(()),
        )
        .unwrap();
        for row in &rows[..2] {
            assert_eq!(row["severity"], "error");
            assert_eq!(row["route"], "report_only");
            assert_eq!(row["bundle_status"], "excluded");
            assert_eq!(row["protected_status"], "excluded");
        }
        assert_eq!(rows[2]["severity"], "error");
        assert_eq!(rows[2]["route"], "undecided");
        assert_eq!(rows[2]["original_status"], "pending");
        assert_eq!(rows[2]["protected_status"], "pending");
        assert_eq!(rows[2]["bundle_status"], "pending");
        // A source finding that did not prevent preparation must not hide a
        // distinct explicit original failure without its own check.
        record["entries"][2]["original"] = json!({"status":"failed","error":"Output write failed"});
        let mut findings = Vec::new();
        project(
            &record,
            |_| Ok(()),
            |finding| {
                findings.push(serde_json::to_value(finding)?);
                Ok(())
            },
        )
        .unwrap();
        assert!(
            findings
                .iter()
                .any(|finding| finding["row_key"] == "row-000003"
                    && finding["code"] == "artifact.original_failed")
        );
    }
}
