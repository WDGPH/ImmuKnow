//! Saved-run review of distinct structured warning subjects.
use anyhow::{Context, Result, ensure};
use chrono::{DateTime, SecondsFormat, Utc};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{collections::BTreeSet, path::Path, time::SystemTime};

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub(crate) enum Action {
    Acknowledge,
    Revoke,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Event {
    pub(crate) issue_id: String,
    pub(crate) action: Action,
    pub(crate) reason: String,
    pub(crate) at: String,
}

#[derive(Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Reviews {
    schema_version: u8,
    pub(crate) history: Vec<Event>,
}

impl Reviews {
    pub(crate) fn active_ids(&self) -> BTreeSet<String> {
        let mut active = BTreeSet::new();
        for event in &self.history {
            match event.action {
                Action::Acknowledge => {
                    active.insert(event.issue_id.clone());
                }
                Action::Revoke => {
                    active.remove(&event.issue_id);
                }
            }
        }
        active
    }
}

fn valid_id(id: &str) -> bool {
    id.len() == 64
        && id
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

/// Validate an optional audit before any saved-run mutation.
pub(crate) fn validate(record: &Value) -> Result<Reviews> {
    let Some(value) = record.get("warning_reviews") else {
        return Ok(Reviews {
            schema_version: 1,
            history: Vec::new(),
        });
    };
    let reviews: Reviews =
        serde_json::from_value(value.clone()).context("Invalid warning review history")?;
    ensure!(
        reviews.schema_version == 1,
        "Unsupported warning review version"
    );
    let mut active = BTreeSet::new();
    for event in &reviews.history {
        ensure!(valid_id(&event.issue_id), "Invalid warning review issue ID");
        ensure!(
            !event.reason.trim().is_empty(),
            "Warning review reason must not be blank"
        );
        let time =
            DateTime::parse_from_rfc3339(&event.at).context("Invalid warning review timestamp")?;
        ensure!(
            time.offset().local_minus_utc() == 0,
            "Warning review timestamp must be UTC"
        );
        match event.action {
            Action::Acknowledge => ensure!(
                active.insert(&event.issue_id),
                "Warning review history has repeated acknowledgment"
            ),
            Action::Revoke => ensure!(
                active.remove(&event.issue_id),
                "Warning review history revokes an inactive issue"
            ),
        }
    }
    Ok(reviews)
}

fn read_completed(dir: &Path) -> Result<Value> {
    let record: Value = crate::read_json(&dir.join("run.json"))?;
    ensure!(
        record["run_schema_version"] == 1,
        "Unsupported run record version"
    );
    ensure!(
        matches!(
            record["status"].as_str(),
            Some("completed" | "completed_with_warnings" | "completed_with_failures")
        ),
        "Run is not complete"
    );
    Ok(record)
}

/// List current warnings and active acknowledgments from the authoritative record.
pub fn list(run: &Path, refresh: bool) -> Result<()> {
    let dir = run.canonicalize()?;
    let _lock = crate::pipeline::lock(&dir)?;
    let record = read_completed(&dir)?;
    let reviews = validate(&record)?;
    if refresh {
        crate::report::write(&dir, &record)?;
    }
    let mut active = reviews.active_ids();
    let summary = crate::warnings::summarize(&record);
    for issue in &summary.link_issues {
        let id = issue.id.as_deref().unwrap_or("unavailable");
        let acknowledged = issue.id.as_ref().is_some_and(|id| active.remove(id));
        println!(
            "{}  {}  {} row(s)  {}",
            id,
            issue.code,
            issue.count.rows.len(),
            if acknowledged {
                "acknowledged"
            } else {
                "outstanding"
            }
        );
    }
    for id in active {
        println!("{id}  inactive  acknowledged (use --revoke to close)");
    }
    for (code, count) in summary.other {
        println!("{code}  {} row(s)  other warnings", count.rows.len());
    }
    println!(
        "Notice creation messages: {} row(s)",
        summary.diagnostics.len()
    );
    Ok(())
}

/// Append a review event without changing findings, routing or bundle attempts.
pub fn acknowledge(run: &Path, issue: &str, reason: &str, revoke: bool) -> Result<()> {
    ensure!(valid_id(issue), "Issue ID must be a full lowercase SHA-256");
    ensure!(
        !reason.trim().is_empty(),
        "Warning review requires a nonempty reason"
    );
    let dir = run.canonicalize()?;
    let _lock = crate::pipeline::lock(&dir)?;
    let mut record = read_completed(&dir)?;
    let mut reviews = validate(&record)?;
    let active = reviews.active_ids().contains(issue);
    if revoke {
        ensure!(active, "Issue is not acknowledged");
    } else {
        let summary = crate::warnings::reviewable(&record)?;
        ensure!(!active, "Issue is already acknowledged");
        ensure!(
            summary
                .link_issues
                .iter()
                .any(|item| item.id.as_deref() == Some(issue)),
            "Issue is not a current effective URL warning"
        );
    }
    reviews.history.push(Event {
        issue_id: issue.to_owned(),
        action: if revoke {
            Action::Revoke
        } else {
            Action::Acknowledge
        },
        reason: reason.to_owned(),
        at: DateTime::<Utc>::from(SystemTime::now()).to_rfc3339_opts(SecondsFormat::Secs, true),
    });
    record["warning_reviews"] = json!(reviews);
    crate::report::write(&dir, &record)?;
    println!(
        "Warning review {}.",
        if revoke { "revoked" } else { "recorded" }
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use tempfile::tempdir;

    fn saved() -> Value {
        json!({
            "run_schema_version": 1, "status": "completed_with_warnings",
            "resources": {"sha256": "a".repeat(64)},
            "project_resources": {"templates": {"notice.typ": "b".repeat(64)}},
            "entries": [{"row_key": "row-000001", "checks": [], "effective_checks": [
                {"code": "content.link_https", "status": "warn", "subjects": [{"kind": "url", "urls": ["http://example.test/?private=1"]}]}
            ]}], "delivery_attempts": [], "bundles": []
        })
    }
    fn event(id: &str, action: &str) -> Value {
        json!({"issue_id": id, "action": action, "reason": "Reviewed", "at": "2026-11-01T10:00:00Z"})
    }
    #[test]
    fn strict_history_rejects_bad_fields_timestamps_and_transitions() {
        let id = "a".repeat(64);
        let mut record = saved();
        let cases = vec![
            json!({"schema_version": 2, "history": []}),
            json!({"schema_version": 1, "history": [], "extra": true}),
            json!({"schema_version": 1, "history": [event(&id, "revoke")]}),
            json!({"schema_version": 1, "history": [event(&id, "acknowledge"), event(&id, "acknowledge")]}),
            json!({"schema_version": 1, "history": [{"issue_id":id,"action":"acknowledge","reason":" ","at":"2026-11-01T10:00:00Z"}]}),
            json!({"schema_version": 1, "history": [{"issue_id":id,"action":"acknowledge","reason":"review","at":"2026-11-01T10:00:00+01:00"}]}),
            json!({"schema_version": 1, "history": [{"issue_id":"ABC","action":"acknowledge","reason":"review","at":"bad"}]}),
        ];
        for case in cases {
            record["warning_reviews"] = case;
            assert!(validate(&record).is_err());
        }
    }

    #[test]
    fn review_changes_only_audit_and_can_revoke_stale_issue() {
        let dir = tempdir().unwrap();
        let record = saved();
        let id = crate::warnings::reviewable(&record).unwrap().link_issues[0]
            .id
            .clone()
            .unwrap();
        fs::write(
            dir.path().join("run.json"),
            serde_json::to_vec(&record).unwrap(),
        )
        .unwrap();
        fs::write(dir.path().join("artifact.pdf"), b"fictional PDF").unwrap();
        acknowledge(dir.path(), &id, "Reviewed link", false).unwrap();
        assert!(acknowledge(dir.path(), &id, "Again", false).is_err());
        let mut after: Value = crate::read_json(&dir.path().join("run.json")).unwrap();
        let audit = after
            .as_object_mut()
            .unwrap()
            .remove("warning_reviews")
            .unwrap();
        assert_eq!(after, record);
        assert_eq!(
            fs::read(dir.path().join("artifact.pdf")).unwrap(),
            b"fictional PDF"
        );
        after["warning_reviews"] = audit;
        after["entries"][0]["effective_checks"][0]["status"] = json!("pass");
        // Revocation closes an audit decision even when current subjects or
        // resource fingerprints are no longer usable for new acknowledgments.
        after["resources"] = Value::Null;
        fs::write(
            dir.path().join("run.json"),
            serde_json::to_vec(&after).unwrap(),
        )
        .unwrap();
        list(dir.path(), true).unwrap();
        acknowledge(dir.path(), &id, "No longer applies", true).unwrap();
        let final_record: Value = crate::read_json(&dir.path().join("run.json")).unwrap();
        assert!(!validate(&final_record).unwrap().active_ids().contains(&id));
        assert_eq!(
            final_record["warning_reviews"]["history"]
                .as_array()
                .unwrap()
                .len(),
            2
        );
        assert!(acknowledge(dir.path(), &id, "Again", true).is_err());
        assert!(acknowledge(dir.path(), &id, "Stale", false).is_err());
    }

    #[test]
    fn rejects_unknown_ids_and_malformed_effective_checks_without_writes() {
        let dir = tempdir().unwrap();
        let mut record = saved();
        record["entries"][0]["effective_checks"] = Value::Null;
        let bytes = serde_json::to_vec(&record).unwrap();
        fs::write(dir.path().join("run.json"), &bytes).unwrap();
        assert!(acknowledge(dir.path(), &"c".repeat(64), "Review", false).is_err());
        assert_eq!(fs::read(dir.path().join("run.json")).unwrap(), bytes);
    }

    #[test]
    fn lock_and_invalid_history_prevent_saved_run_mutations() {
        let dir = tempdir().unwrap();
        let mut record = saved();
        let id = crate::warnings::reviewable(&record).unwrap().link_issues[0]
            .id
            .clone()
            .unwrap();
        record["warning_reviews"] = json!({"schema_version": 1, "history": [event(&id, "revoke")]});
        let bytes = serde_json::to_vec(&record).unwrap();
        fs::write(dir.path().join("run.json"), &bytes).unwrap();
        assert!(crate::pipeline::rebundle(dir.path(), None, &[], None, &[], 1).is_err());
        assert_eq!(fs::read(dir.path().join("run.json")).unwrap(), bytes);
        assert!(!dir.path().join("bundles-0001").exists());
        let lock = crate::pipeline::lock(dir.path()).unwrap();
        assert!(list(dir.path(), false).is_err());
        drop(lock);
    }

    #[test]
    fn failed_record_save_keeps_the_previous_audit() {
        let dir = tempdir().unwrap();
        let record = saved();
        let id = crate::warnings::reviewable(&record).unwrap().link_issues[0]
            .id
            .clone()
            .unwrap();
        let bytes = serde_json::to_vec(&record).unwrap();
        fs::write(dir.path().join("run.json"), &bytes).unwrap();
        fs::create_dir(dir.path().join("run.partial")).unwrap();
        let error = acknowledge(dir.path(), &id, "Reviewed", false).unwrap_err();
        assert!(!format!("{error:#}").contains("record saved"));
        assert_eq!(fs::read(dir.path().join("run.json")).unwrap(), bytes);
        assert!(!dir.path().join("report.html").exists());
        fs::remove_dir(dir.path().join("run.partial")).unwrap();
        acknowledge(dir.path(), &id, "Reviewed", false).unwrap();
        let updated: Value = crate::read_json(&dir.path().join("run.json")).unwrap();
        assert_eq!(
            updated["warning_reviews"]["history"]
                .as_array()
                .unwrap()
                .len(),
            1
        );
    }
    #[test]
    fn failed_html_publication_keeps_review_and_refresh_recovers() {
        let dir = tempdir().unwrap();
        let record = saved();
        let id = crate::warnings::reviewable(&record).unwrap().link_issues[0]
            .id
            .clone()
            .unwrap();
        fs::write(
            dir.path().join("run.json"),
            serde_json::to_vec(&record).unwrap(),
        )
        .unwrap();
        fs::create_dir(dir.path().join("report.html")).unwrap();
        let error = acknowledge(dir.path(), &id, "Reviewed", false).unwrap_err();
        assert!(format!("{error:#}").contains("saved"));
        let updated: Value = crate::read_json(&dir.path().join("run.json")).unwrap();
        assert!(validate(&updated).unwrap().active_ids().contains(&id));
        fs::remove_dir(dir.path().join("report.html")).unwrap();
        list(dir.path(), true).unwrap();
        assert!(dir.path().join("report.html").is_file());
    }
}
