//! Persist a run and render an escaped, browsable HTML report.
use anyhow::{Context, Result};
use serde_json::Value;
use std::{
    fmt::Write,
    io::{BufWriter, Write as IoWrite},
    path::{Component, Path},
};

pub fn escaped(text: &str) -> String {
    let mut escaped = String::with_capacity(text.len());
    let mut start = 0;
    for (index, character) in text.char_indices() {
        let entity = match character {
            '&' => "&amp;",
            '<' => "&lt;",
            '>' => "&gt;",
            '"' => "&quot;",
            '\'' => "&#39;",
            _ => continue,
        };
        escaped.push_str(&text[start..index]);
        escaped.push_str(entity);
        start = index + character.len_utf8();
    }
    escaped.push_str(&text[start..]);
    escaped
}
fn text<'a>(v: &'a Value, key: &str) -> &'a str {
    v[key].as_str().unwrap_or("")
}
fn label(status: &str) -> &str {
    match status {
        "completed_with_failures" => "Completed with failures",
        "completed_with_warnings" => "Completed with warnings",
        "completed" => "Completed",
        "deliverable" => "Ready",
        "review" => "Needs review",
        "withheld" => "Withheld",
        "not_requested" => "Not requested",
        "not_applicable" => "Not applicable",
        "not_run" => "Not run",
        "failed" => "Failed",
        "running" => "In progress",
        "pass" => "Passed",
        "warn" => "Warning",
        "fail" => "Failure",
        "" => "Not decided",
        _ => status,
    }
}
fn artifact(html: &mut String, title: &str, value: &Value) {
    let Some(path) = value["path"].as_str() else {
        return;
    };
    if path.is_empty()
        || path.contains([':', '\\'])
        || !Path::new(path)
            .components()
            .all(|c| matches!(c, Component::Normal(_)))
    {
        return;
    }
    let _ = write!(
        html,
        "<p><a href=\"{}\">{}</a><small>{}</small></p>",
        escaped(path),
        escaped(title),
        escaped(path)
    );
    if let Some(hash) = value["sha256"].as_str() {
        let _ = write!(
            html,
            "<details class=\"evidence\"><summary>File fingerprint</summary><pre>SHA-256 {}</pre></details>",
            escaped(hash)
        );
    }
}
fn effective(entry: &Value) -> &[Value] {
    entry
        .get("effective_checks")
        .unwrap_or(&entry["checks"])
        .as_array()
        .map(Vec::as_slice)
        .unwrap_or(&[])
}
fn count(checks: &[Value], status: &str) -> usize {
    checks.iter().filter(|c| c["status"] == status).count()
}
// Match the bundle decision: an unperformed check blocks unless policy disabled it.
fn blocking(c: &Value) -> bool {
    match text(c, "status") {
        "pass" | "warn" | "not_applicable" => false,
        "not_run" if c["disabled"] == true => false,
        _ => true,
    }
}
fn has_diagnostics(e: &Value) -> bool {
    e["compiler_diagnostics"]
        .as_str()
        .is_some_and(|s| !s.is_empty())
}
fn has_warning(e: &Value) -> bool {
    count(effective(e), "warn") > 0 || has_diagnostics(e)
}
fn message(c: &Value) -> &str {
    if c["code"] == "render.evidence_failed" {
        "The notice could not be verified against its source row or template report."
    } else {
        text(c, "message")
    }
}
fn name(e: &Value) -> String {
    if let Some(name) = e["notice"]["client_data"]["name"]
        .as_str()
        .filter(|s| !s.is_empty())
    {
        return name.to_owned();
    }
    let name = [
        text(&e["source"], "first_name"),
        text(&e["source"], "last_name"),
    ]
    .into_iter()
    .filter(|s| !s.is_empty())
    .collect::<Vec<_>>()
    .join(" ");
    if name.is_empty() {
        "Name unavailable".to_owned()
    } else {
        name
    }
}
fn school(e: &Value) -> &str {
    e["notice"]["school"]["name"]
        .as_str()
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| text(&e["source"], "school_name"))
}
fn client_id(e: &Value) -> &str {
    e["client_id"]
        .as_str()
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| text(&e["source"], "client_id"))
}
fn action(code: &str) -> &str {
    match code {
        "data.school_match" => {
            "Compare the source school name and ID with the school reference; correct the source or reference and run again."
        }
        "delivery.notice_length" => {
            "Review the original PDF and the required page count. Correct the template or page-count setting and rebuild the output."
        }
        "delivery.original_unusable" => "Create the notice again before rebuilding bundles.",
        _ if code.starts_with("delivery.school_identity_")
            || code.starts_with("delivery.board_identity_") =>
        {
            "Review the source school and board names and IDs. Correct missing or conflicting identities and run again; name fallbacks use normalized grouping."
        }
        "encryption.failed" => {
            "Check the encryption settings and required password fields, then create the protected copy again."
        }
        "render.evidence_failed" => {
            "Ask the template maintainer to correct the notice evidence. The original PDF, if available, remains for review."
        }
        "output.readable" => {
            "Ask technical support to inspect the PDF creation error and create the notice again."
        }
        "rendering.failed" => {
            "Ask the template maintainer to review Original PDF error details or Notice creation messages, then correct the template or its inputs."
        }
        _ if code.starts_with("source.") => {
            "Check the corresponding value in the source CSV, correct it if needed, and run again."
        }
        _ if code.starts_with("assignment.") => {
            "Check that the assigned notice is appropriate for this person and the supplied information."
        }
        _ if code.starts_with("layout.") => {
            "Inspect the affected page. Ask the template maintainer to adjust the layout if needed."
        }
        _ if code.starts_with("compiler.") => {
            "Ask the template maintainer to review the notice creation messages and required fonts."
        }
        _ if code.starts_with("content.") => {
            "Review the affected notice content and its source information with the data or template owner."
        }
        _ => "Review this finding and the technical details before using the notice.",
    }
}
fn help_link(code: &str) -> String {
    let anchor = if code.starts_with("component.") && code.ends_with(".absent") {
        "component-absent".to_owned()
    } else {
        code.chars()
            .map(|c| if c.is_ascii_alphanumeric() { c } else { '-' })
            .collect()
    };
    format!("https://docs.phiz.ca/immuknow/latest/user_guide/findings/#{anchor}")
}
fn finding(html: &mut String, c: &Value) {
    let status = text(c, "status");
    let class = match status {
        "fail" => "fail",
        "warn" => "warn",
        "pass" => "pass",
        _ => "",
    };
    let _ = write!(
        html,
        "<li><span class=\"badge {class}\">{}</span>: {}",
        escaped(if status.is_empty() {
            "Unknown check result"
        } else {
            label(status)
        }),
        escaped(message(c))
    );
    if let Some(page) = c["page"].as_u64() {
        let _ = write!(html, " <strong>(notice page {page})</strong>");
    }
    if blocking(c) && !matches!(status, "fail" | "not_run") {
        html.push_str("<p>The check result is missing or unsupported and blocks the normal bundle. Ask technical support to inspect the saved evidence.</p>");
    }
    if blocking(c) && status == "not_run" {
        html.push_str("<p>This check was not performed and blocks the normal bundle. Resolve the check problem before rebuilding output.</p>");
    }
    if matches!(status, "warn" | "fail") {
        let _ = write!(html, "<p>Next: {}</p>", escaped(action(text(c, "code"))));
    }
    if let Some(reason) = c["policy_reason"].as_str() {
        let _ = write!(
            html,
            "<p>Rule changed: {} · Original result: {} · Effective result: {}</p>",
            escaped(reason),
            escaped(label(text(c, "observed_status"))),
            escaped(label(status))
        );
    }
    let _ = write!(
        html,
        "<p><a href=\"{}\">What this check means</a></p>",
        escaped(&help_link(text(c, "code")))
    );
    let _ = write!(
        html,
        "<details class=\"evidence\"><summary>Technical details · {}</summary><pre>{}</pre></details></li>",
        escaped(text(c, "code")),
        escaped(&serde_json::to_string_pretty(c).unwrap_or_default())
    );
}
fn checks(html: &mut String, items: &[Value]) {
    let issues: Vec<_> = items
        .iter()
        .filter(|c| blocking(c) || c["status"] == "warn")
        .collect();
    if !issues.is_empty() {
        html.push_str("<ul>");
        for c in issues.iter().filter(|c| blocking(c)) {
            finding(html, c);
        }
        for c in issues.iter().filter(|c| c["status"] == "warn") {
            finding(html, c);
        }
        html.push_str("</ul>");
    }
    let other: Vec<_> = items
        .iter()
        .filter(|c| !blocking(c) && c["status"] != "warn")
        .collect();
    if !other.is_empty() {
        let _ = write!(
            html,
            "<details><summary>Other checks ({}) · passed, not applicable or disabled</summary><ul>",
            other.len()
        );
        for c in other {
            finding(html, c);
        }
        html.push_str("</ul></details>");
    }
}
fn warning_rows(html: &mut String, rows: &std::collections::BTreeSet<usize>) {
    html.push_str("<details><summary>Show affected source rows</summary><p>");
    for (index, row) in rows.iter().enumerate() {
        if index > 0 {
            html.push_str(", ");
        }
        let _ = write!(html, "<a href=\"#notice-row-{row}\">Source row {row}</a>");
    }
    html.push_str("</p></details>");
}

fn warning_summary(html: &mut String, record: &Value) {
    let summary = crate::warnings::summarize(record);
    let reviews = crate::warning_review::validate(record);
    let active = reviews
        .as_ref()
        .map(|reviews| reviews.active_ids())
        .unwrap_or_default();
    html.push_str("<h2>Warning summary</h2><p>Effective warnings are grouped below. Link issues distinguish exact destinations or destination sets; labels omit addresses. Expand a group to reach each affected source row. Notice creation messages are counted separately.</p>");
    let _ = write!(
        html,
        "<p><strong>{}</strong> distinct structured link issues</p>",
        summary.link_issues.len()
    );
    if reviews.is_ok() {
        let current: std::collections::BTreeSet<_> = summary
            .link_issues
            .iter()
            .filter_map(|issue| issue.id.as_deref())
            .collect();
        let acknowledged = current.iter().filter(|id| active.contains(**id)).count();
        let inactive = active
            .iter()
            .filter(|id| !current.contains(id.as_str()))
            .count();
        let _ = write!(
            html,
            "<p>{acknowledged} acknowledged · {} outstanding · {inactive} inactive acknowledgments</p>",
            summary.link_issues.len() - acknowledged
        );
        html.push_str("<p>Review acknowledgments record attention only; they do not change warnings, delivery decisions, or exit status. Use <code>immuknow warnings RUN</code> to list issue IDs and manage reviews.</p>");
        if inactive > 0 {
            html.push_str("<details><summary>Inactive acknowledgments</summary><p>These reviewed issues no longer have effective warnings. To close a review, use <code>immuknow acknowledge RUN ISSUE_ID --revoke --reason TEXT</code>.</p><ul>");
            for id in active.iter().filter(|id| !current.contains(id.as_str())) {
                let _ = write!(html, "<li><code>{}</code></li>", escaped(id));
            }
            html.push_str("</ul></details>");
        }
    } else {
        html.push_str("<p class=\"fail\">Warning review history is invalid; acknowledgment status is unavailable. Inspect the saved run before changing reviews.</p>");
    }
    if !summary.link_issues.is_empty() {
        html.push_str("<ul>");
        for (index, issue) in summary.link_issues.iter().enumerate() {
            let _ = write!(
                html,
                "<li data-issue-id=\"{}\">Link issue {} · <code>{}</code> · {} affected rows · {} occurrences",
                issue.id.as_deref().unwrap_or(""),
                index + 1,
                escaped(&issue.code),
                issue.count.rows.len(),
                issue.count.occurrences
            );
            if reviews.is_ok() {
                let state = if issue.id.as_ref().is_some_and(|id| active.contains(id)) {
                    "Acknowledged"
                } else {
                    "Outstanding"
                };
                let _ = write!(html, " · {state}");
            }
            if let Some(id) = &issue.id {
                let _ = write!(
                    html,
                    "<small>Issue ID: <code>{}</code></small>",
                    escaped(id)
                );
            } else {
                html.push_str(
                    "<small>Issue ID unavailable; this finding cannot be acknowledged.</small>",
                );
            }
            warning_rows(html, &issue.count.rows);
            html.push_str("</li>");
        }
        html.push_str("</ul>");
    }
    if let Ok(reviews) = &reviews {
        if !reviews.history.is_empty() {
            html.push_str("<details><summary>Warning review history</summary><ul>");
            for event in &reviews.history {
                let action = match event.action {
                    crate::warning_review::Action::Acknowledge => "Acknowledged",
                    crate::warning_review::Action::Revoke => "Revoked",
                };
                let _ = write!(
                    html,
                    "<li>{} · <code>{}</code> · {} · {}</li>",
                    action,
                    escaped(&event.issue_id),
                    escaped(&event.at),
                    escaped(&event.reason)
                );
            }
            html.push_str("</ul></details>");
        }
    }
    if !summary.other.is_empty() {
        html.push_str("<h3>Other warnings by check</h3><p>Counts by check do not identify distinct causes. Older link findings without structured subjects appear here.</p><ul>");
        for (code, count) in &summary.other {
            let _ = write!(
                html,
                "<li><code>{}</code> · {} affected rows · {} occurrences",
                escaped(code),
                count.rows.len(),
                count.occurrences
            );
            warning_rows(html, &count.rows);
            html.push_str("</li>");
        }
        html.push_str("</ul>");
    }
    let _ = write!(
        html,
        "<h3>Notice creation messages</h3><p>{} affected rows</p>",
        summary.diagnostics.len()
    );
    if !summary.diagnostics.is_empty() {
        warning_rows(html, &summary.diagnostics);
    }
}

fn route(entry: &Value) -> &str {
    match text(entry, "routing") {
        "deliverable" => "deliverable",
        "review" => "review",
        "withheld" => "withheld",
        "failed" => "failed",
        _ => "undecided",
    }
}
fn entry_details(html: &mut String, e: &Value) {
    html.push_str("<details><summary>Findings and files</summary>");
    let decision = match route(e) {
        "deliverable" => {
            "Eligible for the normal bundle under the effective rules. Warnings may still need attention; check the actual file links below."
        }
        "review" => {
            "Excluded from the normal bundle. The readable original is assigned to review; resolve the failures before sending."
        }
        "withheld" => {
            "Excluded from both normal and review bundles. Release the hold with the saved-run command when appropriate; checks will still apply."
        }
        "failed" => {
            "No usable original is available for bundling. Resolve the creation or file problem and create the notice again."
        }
        _ => {
            "No delivery decision was recorded. Check the run error and creation outcome before using any files."
        }
    };
    let _ = write!(html, "<p>{decision}</p>");
    if let Some(reason) = e["hold"]["reason"].as_str() {
        let _ = write!(html, "<p>Hold reason: {}</p>", escaped(reason));
    }
    checks(html, effective(e));
    if has_diagnostics(e) {
        html.push_str("<p class=\"warn\"><strong>Notice creation messages recorded.</strong> Inspect the PDF and expand Notice creation messages below. These messages also count toward warning-row filters.</p>");
    }
    let _ = write!(
        html,
        "<p>Original PDF: {} · Encrypted copy: {}</p>",
        escaped(label(text(&e["original"], "status"))),
        escaped(label(text(&e["encryption"], "status")))
    );
    artifact(html, "Original PDF (not encrypted)", &e["original"]);
    artifact(html, "Encrypted PDF", &e["encryption"]);
    artifact(html, "Bundle PDF (not encrypted)", &e["bundle"]);
    if let (Some(start), Some(end)) = (
        e["bundle"]["notice_start_page"].as_u64(),
        e["bundle"]["notice_end_page"].as_u64(),
    ) {
        let _ = write!(html, "<p>Bundle pages: {start}–{end}</p>");
    }
    for field in ["original", "encryption"] {
        if let Some(error) = e[field]["error"].as_str() {
            let _ = write!(
                html,
                "<details><summary>{} error details</summary><pre>{}</pre></details>",
                escaped(if field == "original" {
                    "Original PDF"
                } else {
                    "Encrypted copy"
                }),
                escaped(error)
            );
        }
    }
    if let Some(diagnostics) = e["compiler_diagnostics"].as_str().filter(|s| !s.is_empty()) {
        let _ = write!(
            html,
            "<details><summary>Notice creation messages</summary><pre>{}</pre></details>",
            escaped(diagnostics)
        );
    }
    html.push_str("</details>");
}
pub fn write(dir: &Path, record: &Value) -> Result<()> {
    let mut html = String::from(
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>ImmuKnow run report</title><style>",
    );
    html.push_str(include_str!("report.css"));
    html.push_str("</style></head><body><main><h1>ImmuKnow run report</h1>");
    let entries = record["entries"]
        .as_array()
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    let _ = write!(
        html,
        "<p>Status: <strong>{}</strong> · {} source rows</p>",
        escaped(label(text(record, "status"))),
        entries.len()
    );
    if let Some(error) = record["error"].as_str() {
        let _ = write!(
            html,
            "<p class=\"fail\"><strong>Run error:</strong> {}</p>",
            escaped(error)
        );
    }
    html.push_str("<div class=\"counts\" aria-label=\"Source rows by delivery decision\">");
    for (key, name) in [
        ("deliverable", "Ready"),
        ("review", "Needs review"),
        ("withheld", "Withheld"),
        ("failed", "Failed"),
        ("undecided", "Not decided"),
    ] {
        let n = entries.iter().filter(|e| route(e) == key).count();
        let _ = write!(
            html,
            "<div class=\"count\"><strong>{n}</strong>{name}</div>"
        );
    }
    html.push_str("</div>");
    let warned = entries.iter().filter(|e| has_warning(e)).count();
    let _ = write!(
        html,
        "<p>{warned} of {} source rows have effective warnings or notice creation messages (these overlap the delivery counts above). Ready means eligible under the effective rules; it does not mean warning-free.</p>",
        entries.len()
    );
    html.push_str("<p class=\"muted\">Review findings and representative PDFs before sending. These checks validate supplied information and document output; the source system assesses immunization status. Link checks examine address formats, not whether destinations are reachable.</p>");
    warning_summary(&mut html, record);
    if let Some(items) = record["checks"].as_array().filter(|c| !c.is_empty()) {
        html.push_str("<h2>Run checks</h2>");
        checks(&mut html, items);
    }
    html.push_str("<h2>Bundles</h2><p>Bundles use original PDFs and are <strong>not encrypted</strong>. Encrypted copies are separate files for each person.</p>");
    let bundles = record["bundles"]
        .as_array()
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    if bundles.is_empty() {
        html.push_str("<p>No bundles recorded. Review run errors and individual files below; a Ready decision alone does not confirm a bundle was produced.</p>");
    }
    html.push_str("<div class=\"bundles\">");
    for (i, b) in bundles.iter().enumerate() {
        html.push_str("<div class=\"bundle\">");
        let title = format!(
            "{} {}",
            if b["route"] == "deliverable" {
                "Ready notices bundle"
            } else {
                "Review bundle"
            },
            i + 1
        );
        artifact(&mut html, &title, b);
        if let Some(path) = b["csv"].as_str() {
            artifact(
                &mut html,
                "Bundle findings CSV",
                &serde_json::json!({"path":path}),
            );
        }
        let _ = write!(
            html,
            "<p>{} pages · {} notices</p></div>",
            b["pages"].as_u64().unwrap_or(0),
            b["members"].as_array().map_or(0, Vec::len)
        );
    }
    html.push_str("</div><h2>Notices</h2><p>Failure blocks the normal bundle. Warning permits inclusion under the effective rules. Not applicable means the check does not apply; Not run blocks the normal bundle unless the check was explicitly disabled by policy.</p><div id=\"controls\" class=\"controls\" hidden><label for=\"search\">Search names, IDs, schools or findings<input id=\"search\" type=\"search\"></label><label for=\"filter\">Show<select id=\"filter\"><option value=\"all\">All source rows</option><option value=\"review\">Needs review</option><option value=\"failed\">Failed</option><option value=\"warnings\">With warnings (any decision)</option><option value=\"withheld\">Withheld</option><option value=\"deliverable\">Ready</option><option value=\"undecided\">Not decided</option></select></label></div><p id=\"shown\" role=\"status\" aria-live=\"polite\"></p><noscript><p>All source rows are shown. Use your browser’s Find command to search.</p></noscript><p id=\"no-matches\" hidden>No matching source rows. Clear the search or change the filter.</p><table><caption>Source rows and effective findings</caption><thead><tr><th scope=\"col\">Person / source row</th><th scope=\"col\">School / notice</th><th scope=\"col\">Delivery decision</th><th scope=\"col\">Findings and files</th></tr></thead><tbody>");
    for (index, e) in entries.iter().enumerate() {
        let findings = effective(e);
        let warnings = count(findings, "warn");
        let available = e.get("effective_checks").unwrap_or(&e["checks"]).is_array();
        let failures = if available {
            findings.iter().filter(|c| blocking(c)).count().to_string()
        } else {
            "unavailable".to_owned()
        };
        let _ = write!(
            html,
            "<tr id=\"notice-row-{}\" data-route=\"{}\" data-warnings=\"{}\"><td data-label=\"Person / source row\"><strong>{}</strong><small>Client ID: {}</small><small>{}</small></td><td data-label=\"School / notice\">{}<small>{}</small></td><td data-label=\"Delivery decision\"><strong>{}</strong><small>Blocking findings: {failures} · Warnings: {warnings}</small></td><td data-label=\"Findings and files\">",
            index + 1,
            route(e),
            has_warning(e),
            escaped(&name(e)),
            escaped(client_id(e)),
            escaped(text(e, "row_key")),
            escaped(school(e)),
            escaped(text(&e["assignment"], "template")),
            escaped(label(text(e, "routing")))
        );
        if has_diagnostics(e) {
            html.push_str("<p class=\"warn\">Notice creation messages recorded</p>");
        }
        if !available {
            html.push_str(
                "<p>Check results unavailable. Review the run error and technical evidence.</p>",
            );
        } else if let Some(first) = findings
            .iter()
            .find(|c| blocking(c))
            .or_else(|| findings.iter().find(|c| c["status"] == "warn"))
        {
            let _ = write!(html, "<p>{}</p>", escaped(message(first)));
        } else if let Some(reason) = e["hold"]["reason"].as_str() {
            let _ = write!(html, "<p>{}</p>", escaped(reason));
        } else if findings.is_empty() {
            html.push_str(
                "<p>No check results recorded. Review the run status and creation outcome.</p>",
            );
        } else if !has_diagnostics(e) {
            html.push_str("<p>No effective blocking findings or warnings recorded.</p>");
        }
        entry_details(&mut html, e);
        html.push_str("</td></tr>");
    }
    html.push_str("</tbody></table><p><a href=\"run.json\">Run record (JSON)</a> contains observed checks, effective results, artifact outcomes and recorded delivery attempts.</p></main><script>");
    html.push_str(include_str!("report.js"));
    html.push_str("</script></body></html>");
    crate::atomic_write(&dir.join("run.json"), |writer| {
        let mut writer = BufWriter::with_capacity(64 * 1024, writer);
        serde_json::to_writer_pretty(&mut writer, record)?;
        writer.flush()?;
        Ok(())
    })?;
    crate::atomic(&dir.join("report.html"), html.as_bytes())
        .context("Run record saved, but HTML report refresh failed")
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn warning_review_status_and_history_are_visible_and_escaped() {
        let mut record = serde_json::json!({"resources":{"sha256":"a".repeat(64)},"project_resources":{"templates":{"letter.typ":"b".repeat(64)}},"entries":[{"effective_checks":[{"code":"content.link_https","status":"warn","subjects":[{"kind":"url","urls":["http://example.test/?id=secret"]}]}]}]});
        let id = crate::warnings::reviewable(&record).unwrap().link_issues[0]
            .id
            .clone()
            .unwrap();
        record["warning_reviews"] = serde_json::json!({"schema_version":1,"history":[{"issue_id":id,"action":"acknowledge","reason":"<reviewed>","at":"2026-01-01T00:00:00Z"}]});
        let mut html = String::new();
        warning_summary(&mut html, &record);
        assert!(html.contains("1 acknowledged · 0 outstanding"));
        assert!(html.contains(" · Acknowledged"));
        assert!(html.contains("&lt;reviewed&gt;"));
        assert!(!html.contains("id=secret"));
        record["entries"][0]["effective_checks"][0]["status"] = serde_json::json!("fail");
        html.clear();
        warning_summary(&mut html, &record);
        assert!(html.contains("1 inactive acknowledgments"));
    }

    #[test]
    fn summary_hides_destinations_and_links_to_affected_rows() {
        let record = serde_json::json!({"entries":[
            {"effective_checks":[{"code":"content.link_https","status":"warn","subjects":[{"kind":"url","urls":["http://example.test/?private=secret"]}]}]},
            {"effective_checks":[{"code":"content.link_https","status":"warn","subjects":[{"kind":"url","urls":["http://example.test/?private=secret"]}]}],"compiler_diagnostics":"separate"}
        ]});
        let mut html = String::new();
        warning_summary(&mut html, &record);
        assert!(html.contains("1</strong> distinct structured link issues"));
        assert!(html.contains("2 affected rows · 2 occurrences"));
        assert!(html.contains("href=\"#notice-row-1\""));
        assert!(html.contains("href=\"#notice-row-2\""));
        assert!(!html.contains("private=secret"));
        assert!(html.contains("Notice creation messages</h3><p>1 affected rows"));
    }

    #[test]
    fn escapes_untrusted_content() {
        assert_eq!(
            escaped("<x a=\"'&\">"),
            "&lt;x a=&quot;&#39;&amp;&quot;&gt;"
        );
        assert_eq!(
            escaped("L'élève 😄 <&amp;>"),
            "L&#39;élève 😄 &lt;&amp;amp;&gt;"
        );
    }

    #[test]
    fn report_preserves_identity_policy_and_safe_evidence() {
        let dir = tempfile::tempdir().unwrap();
        let observed = serde_json::json!({"code":"content.link_https","status":"warn","message":"Link needs review"});
        let record = serde_json::json!({
            "status":"completed_with_failures",
            "entries":[
                {"row_key":"row-000001","source":{"first_name":"<Alice>","last_name":"Example","client_id":"0000000001","school_name":"Example Academy"},
                 "checks":[observed],"effective_checks":[
                    {"code":"content.link_https","status":"not_run","disabled":true,"observed_status":"warn","policy_reason":"Approved alternative","message":"Link needs review"},
                    {"code":"render.evidence_failed","status":"fail","message":"Expected exactly one immuknow-report summary"}],
                 "routing":"review","original":{"status":"completed","path":"javascript:alert(1)"}},
                {"row_key":"row-000002","source":{"first_name":"Bob"},"checks":[],"original":{"status":"not_run"}}
            ],"checks":[],"bundles":[]
        });
        write(dir.path(), &record).unwrap();
        let html = std::fs::read_to_string(dir.path().join("report.html")).unwrap();
        assert!(html.contains("&lt;Alice&gt; Example"));
        assert!(html.contains("Client ID: 0000000001"));
        assert!(html.contains("Example Academy"));
        assert!(!html.contains("href=\"javascript:"));
        assert!(html.contains("data-route=\"review\" data-warnings=\"false\""));
        assert!(html.contains("Original result: Warning · Effective result: Not run"));
        assert!(html.contains("No check results recorded"));
        assert!(html.contains("The notice could not be verified"));
        assert!(html.contains("Expected exactly one immuknow-report summary"));
        assert!(html.contains("findings/#content-link-https"));
        assert!(
            html.find("The notice could not be verified").unwrap()
                < html.find("Other checks (1)").unwrap()
        );
        let saved: Value =
            serde_json::from_slice(&std::fs::read(dir.path().join("run.json")).unwrap()).unwrap();
        assert_eq!(saved, record);
    }
    #[test]
    fn unperformed_check_is_prominent_unless_explicitly_disabled() {
        let mut html = String::new();
        let items = serde_json::json!([
            {"code":"layout.history_width","status":"pass","message":"Fits"},
            {"code":"content.link_https","status":"not_run","message":"Unable to check"},
            {"code":"layout.signature_page","status":"warn","message":"Signature moved"}
        ]);
        checks(&mut html, items.as_array().unwrap());
        assert!(html.contains("blocks the normal bundle"));
        assert!(html.find("Unable to check").unwrap() < html.find("Signature moved").unwrap());
        assert!(html.find("Signature moved").unwrap() < html.find("Other checks (1)").unwrap());
        assert_eq!(
            help_link("component.qr.absent"),
            "https://docs.phiz.ca/immuknow/latest/user_guide/findings/#component-absent"
        );
    }

    #[test]
    fn diagnostics_and_unavailable_evidence_cannot_look_clean() {
        let dir = tempfile::tempdir().unwrap();
        let record = serde_json::json!({"entries":[
            {"row_key":"row-000001","routing":"deliverable","checks":[],"compiler_diagnostics":"Font warning"},
            {"row_key":"row-000002","routing":"review","checks":[{"code":"compiler.warning","status":"unexpected","message":"Unknown result"}]},
            {"row_key":"row-000003","routing":"review"}
        ]});
        write(dir.path(), &record).unwrap();
        let html = std::fs::read_to_string(dir.path().join("report.html")).unwrap();
        assert!(html.contains("data-route=\"deliverable\" data-warnings=\"true\""));
        assert!(
            html.contains("1 of 3 source rows have effective warnings or notice creation messages")
        );
        assert!(html.contains("Notice creation messages recorded"));
        assert!(html.contains("The check result is missing or unsupported"));
        assert!(html.contains("Blocking findings: unavailable"));
        assert!(html.contains("Check results unavailable"));
    }
}
