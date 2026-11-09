//! Summarize effective warnings without parsing human messages or exposing subjects.
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Default)]
pub(crate) struct Count {
    pub occurrences: usize,
    pub rows: BTreeSet<usize>,
}

pub(crate) struct LinkIssue {
    pub id: Option<String>,
    pub code: String,
    pub count: Count,
}

#[derive(Default)]
pub(crate) struct Summary {
    pub link_issues: Vec<LinkIssue>,
    pub other: BTreeMap<String, Count>,
    pub diagnostics: BTreeSet<usize>,
}

fn valid_scope(record: &Value) -> bool {
    let valid_hash = |value: &Value| {
        value.as_str().is_some_and(|s| {
            s.len() == 64
                && s.bytes()
                    .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
        })
    };
    valid_hash(&record["resources"]["sha256"])
        && record["project_resources"]["templates"]
            .as_object()
            .is_some_and(|templates| !templates.is_empty() && templates.values().all(valid_hash))
}

// The same parser supplies both display grouping and the review mutation gate.
// An invalid list is indivisible: no subset receives a reviewable identity.
fn subjects(check: &Value) -> anyhow::Result<Option<Vec<String>>> {
    use anyhow::{Context, ensure};
    let kind = match check["code"].as_str() {
        Some("content.link_https" | "content.link_destination") => "url",
        Some("content.multiple_links") => "url_set",
        _ => return Ok(None),
    };
    let subjects = check["subjects"]
        .as_array()
        .context("Link warning has no structured subjects")?;
    ensure!(
        !subjects.is_empty() && (kind != "url_set" || subjects.len() == 1),
        "Invalid link warning subjects"
    );
    let mut keys = BTreeSet::new();
    for subject in subjects {
        let object = subject.as_object().context("Invalid link subject")?;
        let urls = subject["urls"]
            .as_array()
            .context("Invalid link subject URLs")?;
        ensure!(
            object.len() == 2
                && subject["kind"] == kind
                && (if kind == "url" {
                    urls.len() == 1
                } else {
                    urls.len() >= 2
                })
                && urls.iter().all(Value::is_string),
            "Invalid link subject"
        );
        let mut values: Vec<_> = urls.iter().map(|url| url.as_str().unwrap()).collect();
        values.sort_unstable();
        ensure!(
            values.windows(2).all(|pair| pair[0] != pair[1]),
            "Duplicate link subject destination"
        );
        ensure!(
            keys.insert(serde_json::to_string(&(kind, values))?),
            "Duplicate link subjects"
        );
    }
    Ok(Some(keys.into_iter().collect()))
}

/// Reject incomplete or malformed evidence before a saved-run review mutation.
/// Display remains tolerant of old or incomplete records through `summarize`.
pub(crate) fn reviewable(record: &Value) -> anyhow::Result<Summary> {
    use anyhow::{Context, ensure};
    ensure!(
        valid_scope(record),
        "Saved resource or template fingerprints are missing or invalid"
    );
    let entries = record["entries"]
        .as_array()
        .context("Missing saved entries")?;
    for entry in entries {
        let checks = entry["effective_checks"]
            .as_array()
            .context("Missing effective checks")?;
        for check in checks {
            ensure!(
                check["code"].as_str().is_some_and(|code| !code.is_empty())
                    && matches!(
                        check["status"].as_str(),
                        Some("pass" | "warn" | "fail" | "not_run" | "not_applicable")
                    ),
                "Invalid effective check"
            );
            if check["status"] != "warn" {
                continue;
            }
            subjects(check)?;
        }
    }
    let summary = summarize(record);
    ensure!(
        summary.link_issues.iter().all(|issue| issue.id.is_some()),
        "Invalid warning issue identity"
    );
    Ok(summary)
}

/// Exact subjects are used only as in-memory keys; summary labels contain no URLs.
/// Saved resource and template identities prevent different check implementations
/// from sharing an identity. Legacy warnings without subjects remain code counts.
pub(crate) fn summarize(record: &Value) -> Summary {
    let mut summary = Summary::default();
    let valid_scope = valid_scope(record);
    let scope = crate::hash(
        &serde_json::to_vec(&json!({"resources":record["resources"]["sha256"], "templates":record["project_resources"]["templates"]}))
            .expect("saved resource identity is serializable"),
    );
    let mut links: BTreeMap<(String, String, String), Count> = BTreeMap::new();
    for (index, entry) in record["entries"]
        .as_array()
        .into_iter()
        .flatten()
        .enumerate()
    {
        let row = index + 1;
        if entry["compiler_diagnostics"]
            .as_str()
            .is_some_and(|value| !value.is_empty())
        {
            summary.diagnostics.insert(row);
        }
        let checks = entry.get("effective_checks").unwrap_or(&entry["checks"]);
        for check in checks
            .as_array()
            .into_iter()
            .flatten()
            .filter(|c| c["status"] == "warn")
        {
            let code = check["code"].as_str().unwrap_or("Unknown warning");
            if let Ok(Some(keys)) = subjects(check) {
                for subject_key in keys {
                    let count = links
                        .entry((scope.clone(), code.to_owned(), subject_key))
                        .or_default();
                    count.occurrences += 1;
                    count.rows.insert(row);
                }
            } else {
                let count = summary.other.entry(code.to_owned()).or_default();
                count.occurrences += 1;
                count.rows.insert(row);
            }
        }
    }
    summary.link_issues = links
        .into_iter()
        .map(|((scope, code, subject), count)| {
            let id = valid_scope.then(|| {
                crate::hash(
                    &serde_json::to_vec(&("immuknow-link-issue-v1", &scope, &code, &subject))
                        .expect("issue identity is serializable"),
                )
            });
            LinkIssue { id, code, count }
        })
        .collect();
    summary
}

#[cfg(test)]
mod tests {
    use super::*;

    fn review_record(code: &str, url: &str) -> Value {
        json!({"resources":{"sha256":"a".repeat(64)},"project_resources":{"templates":{"letter.typ":"b".repeat(64)}},"entries":[{"effective_checks":[{"code":code,"status":"warn","subjects":[{"kind":"url","urls":[url]}]}]}]})
    }

    #[test]
    fn identity_is_stable_exact_and_scoped_and_rejects_invalid_evidence() {
        let record = review_record("content.link_https", "http://example.test/a?q=1#x");
        let id = reviewable(&record).unwrap().link_issues[0]
            .id
            .clone()
            .unwrap();
        assert_eq!(id.len(), 64);
        assert_eq!(
            id,
            reviewable(&record).unwrap().link_issues[0]
                .id
                .clone()
                .unwrap()
        );
        for changed in [
            review_record("content.link_destination", "http://example.test/a?q=1#x"),
            review_record("content.link_https", "http://example.test/a?q=2#x"),
            review_record("content.link_https", "http://example.test/a?q=1#y"),
        ] {
            assert_ne!(
                id,
                reviewable(&changed).unwrap().link_issues[0]
                    .id
                    .clone()
                    .unwrap()
            );
        }
        let mut changed = record.clone();
        changed["resources"]["sha256"] = json!("c".repeat(64));
        assert_ne!(
            id,
            reviewable(&changed).unwrap().link_issues[0]
                .id
                .clone()
                .unwrap()
        );
        changed = record.clone();
        changed["project_resources"]["templates"]["letter.typ"] = json!("c".repeat(64));
        assert_ne!(
            id,
            reviewable(&changed).unwrap().link_issues[0]
                .id
                .clone()
                .unwrap()
        );
        changed["project_resources"]["templates"]["letter.typ"] = json!("bad");
        assert!(reviewable(&changed).is_err());
        assert!(summarize(&changed).link_issues[0].id.is_none());
        changed = record.clone();
        changed["entries"][0]["effective_checks"][0]["subjects"]
            .as_array_mut()
            .unwrap()
            .push(json!({"kind":"url", "urls":[]}));
        assert!(reviewable(&changed).is_err());
        assert!(summarize(&changed).link_issues.is_empty());
        assert_eq!(
            summarize(&changed).other["content.link_https"].occurrences,
            1
        );
        changed = record.clone();
        changed["entries"][0]["effective_checks"] = Value::Null;
        assert!(reviewable(&changed).is_err());
    }

    #[test]
    fn exact_subjects_and_effective_status_determine_aggregate_counts() {
        let link = |url: &str| json!({"code":"content.link_https","status":"warn","subjects":[{"kind":"url","urls":[url]}]});
        let set = |urls: Vec<&str>| json!({"code":"content.multiple_links","status":"warn","subjects":[{"kind":"url_set","urls":urls}]});
        let record = json!({"resources":{"sha256":"abc"},"entries":[
            {"effective_checks":[link("http://example.test/?id=1"),set(vec!["https://a.test", "https://b.test"]),{"code":"other","status":"warn"}],"compiler_diagnostics":"font"},
            {"effective_checks":[link("http://example.test/?id=1"),set(vec!["https://b.test", "https://a.test"]),{"code":"other","status":"warn"}]},
            {"effective_checks":[link("http://example.test/?id=2"),set(vec!["https://a.test", "https://c.test"]),{"code":"content.link_https","status":"fail","subjects":[{"kind":"url","urls":["http://example.test/?id=3"]}]}]},
            {"checks":[{"code":"content.link_https","status":"warn","message":"legacy"}]}
        ]});
        let summary = summarize(&record);
        assert_eq!(summary.link_issues.len(), 4);
        let mut counts: Vec<_> = summary
            .link_issues
            .iter()
            .map(|item| (item.count.rows.len(), item.count.occurrences))
            .collect();
        counts.sort_unstable();
        assert_eq!(counts, vec![(1, 1), (1, 1), (2, 2), (2, 2)]);
        assert_eq!(summary.other["other"].rows.len(), 2);
        assert_eq!(summary.other["content.link_https"].rows.len(), 1);
        assert_eq!(summary.diagnostics, BTreeSet::from([1]));
    }
}
