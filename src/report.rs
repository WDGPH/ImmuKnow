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
fn status(v: &Value, key: &str, pending: bool) -> String {
    match text(v, key) {
        "completed" | "failed" | "pending" | "not_requested" | "excluded" => {
            text(v, key).to_owned()
        }
        "not_run" | "" if pending => "pending".into(),
        _ => "not_requested".into(),
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
        || (running && e["original"]["status"] != "completed")
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
    protection_requested: bool,
) -> &'static str {
    if cs.iter().any(|c| {
        c["status"] == "fail"
            || (c["status"] == "not_run"
                && c["disabled"] != true
                && (!running || evaluation == "blocked"))
    }) || evaluation == "blocked"
        || e["original"]["status"] == "failed"
        || e["encryption"]["status"] == "failed"
        || e["bundle"]["status"] == "failed"
        || (!running && protection_requested && e["encryption"]["status"] != "completed")
        || (!running && (evaluation == "pending" || e["original"]["status"] != "completed"))
    {
        "error"
    } else if cs.iter().any(|c| c["status"] == "warn")
        || !text(e, "compiler_diagnostics").is_empty()
    {
        "warning"
    } else if evaluation == "pending"
        || (running
            && (e["original"]["status"] != "completed" || e["encryption"]["status"] == "pending"))
    {
        "pending"
    } else {
        "clear"
    }
}
fn route(e: &Value, running: bool) -> &'static str {
    if !e["hold"].is_null() {
        return "withheld";
    }
    if !running && e["original"]["status"] != "completed" {
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
        let sev = severity(e, &row_checks, running, ev, protection_requested);
        let route = route(e, running);
        summary.rows += 1;
        *summary.severity.entry(sev.into()).or_default() += 1;
        *summary.routes.entry(route.into()).or_default() += 1;
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
        let held = route == "withheld";
        let bundle_status = if held || route == "report_only" {
            "excluded"
        } else if grouping == Some(false) {
            "not_requested"
        } else if bundle["status"] == "failed" {
            "failed"
        } else if bundle["path"].is_string() {
            "completed"
        } else if running {
            "pending"
        } else {
            "not_requested"
        };
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
            original_status: if !running && !original_usable {
                "failed".into()
            } else {
                status(&e["original"], "status", running)
            },
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
            protected_status: if !protection_requested
                && record["configured_settings"]["encryption"]["enabled"] == false
            {
                "not_requested".into()
            } else if protection_requested && !running && e["encryption"]["status"] != "completed" {
                "failed".into()
            } else {
                status(&e["encryption"], "status", running)
            },
            protected_path: path(&e["encryption"]),
            bundle_status: bundle_status.into(),
            bundle_path: if bundle_status == "completed" {
                field(bundle, "path")
            } else {
                String::new()
            },
            bundle_start_page: number(&bundle["notice_start_page"]),
            bundle_end_page: number(&bundle["notice_end_page"]),
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
                !running && e["original"]["status"] != "completed",
                row_checks.iter().any(|c| {
                    matches!(text(c, "code"), "rendering.failed" | "output.readable")
                        || (c["status"] == "fail"
                            && (text(c, "code").starts_with("source.")
                                || text(c, "code").starts_with("assignment.")))
                }),
                "Original PDF was not produced",
            ),
            (
                "protected",
                protection_requested && !running && e["encryption"]["status"] != "completed",
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
        serde_json::to_writer_pretty(&mut out, record)?;
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
}
