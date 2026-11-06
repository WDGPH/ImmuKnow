//! Persist a run and render an escaped, browsable HTML report.
use anyhow::Result;
use serde_json::Value;
use std::{
    fmt::Write,
    path::{Component, Path},
};

pub fn escaped(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#39;")
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
        "not_run" => "Not run",
        "failed" => "Failed",
        "running" => "In progress",
        _ => status,
    }
}
fn artifact(html: &mut String, label: &str, value: &Value) {
    let Some(path) = value["path"].as_str() else {
        return;
    };
    // Only link relative run artifacts; never turn record content into a URL scheme.
    if !Path::new(path)
        .components()
        .all(|c| matches!(c, Component::Normal(_)))
    {
        return;
    }
    let _ = write!(
        html,
        "<p><a href=\"{}\">{}</a>",
        escaped(path),
        escaped(label)
    );
    if let Some(hash) = value["sha256"].as_str() {
        let _ = write!(html, " · SHA-256 {}", escaped(hash));
    }
    html.push_str("</p>");
}
fn checks(html: &mut String, checks: &Value) {
    let Some(items) = checks.as_array() else {
        return;
    };
    if items.is_empty() {
        return;
    }
    html.push_str("<ul>");
    for c in items {
        let _ = write!(
            html,
            "<li><strong>{}</strong> · {}: {}</li>",
            escaped(text(c, "status")),
            escaped(text(c, "code")),
            escaped(text(c, "message"))
        );
        if let Some(reason) = c["policy_reason"].as_str() {
            let _ = write!(
                html,
                "<li>Rule reason: {} · original result: {}</li>",
                escaped(reason),
                escaped(text(c, "observed_status"))
            );
        }
    }
    html.push_str("</ul>");
}
pub fn write(dir: &Path, record: &Value) -> Result<()> {
    let json = serde_json::to_vec_pretty(record)?;
    let mut html = String::from(
        "<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><title>ImmuKnow run report</title><style>body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem}details{border-top:1px solid #ccc;padding:1rem 0}summary{cursor:pointer}li{margin:.4rem 0}a{overflow-wrap:anywhere}</style><h1>ImmuKnow run report</h1>",
    );
    let entries = record["entries"].as_array();
    let _ = write!(
        html,
        "<p>Status: <strong>{}</strong> · {} source rows</p>",
        escaped(label(text(record, "status"))),
        entries.map_or(0, Vec::len)
    );
    if let Some(error) = record["error"].as_str() {
        let _ = write!(html, "<p>Error: {}</p>", escaped(error));
    }
    html.push_str("<h2>Run checks</h2>");
    checks(&mut html, &record["checks"]);
    html.push_str("<h2>Bundles</h2>");
    if let Some(bundles) = record["bundles"].as_array() {
        for b in bundles {
            let bundle_label = match text(b, "route") {
                "deliverable" => "Ready notices bundle",
                "review" => "Review bundle",
                _ => "Bundle",
            };
            artifact(&mut html, bundle_label, b);
            if let Some(path) = b["csv"].as_str() {
                artifact(
                    &mut html,
                    "Bundle findings CSV",
                    &serde_json::json!({"path":path}),
                );
            }
            let _ = write!(
                html,
                "<p>{} pages · {} notices</p>",
                b["pages"].as_u64().unwrap_or(0),
                b["members"].as_array().map_or(0, Vec::len)
            );
        }
    }
    html.push_str("<h2>Source rows</h2>");
    if let Some(entries) = entries {
        for e in entries {
            let _ = write!(
                html,
                "<details><summary>{} · {} · {}</summary>",
                escaped(text(e, "row_key")),
                escaped(text(e, "client_id")),
                escaped(label(text(e, "routing")))
            );
            let _ = write!(
                html,
                "<p>Original PDF: {} · Encrypted copy: {}</p>",
                escaped(label(text(&e["original"], "status"))),
                escaped(label(text(&e["encryption"], "status")))
            );
            artifact(&mut html, "Original PDF", &e["original"]);
            artifact(&mut html, "Encrypted PDF", &e["encryption"]);
            artifact(&mut html, "Bundle PDF", &e["bundle"]);
            if let (Some(start), Some(end)) = (
                e["bundle"]["notice_start_page"].as_u64(),
                e["bundle"]["notice_end_page"].as_u64(),
            ) {
                let _ = write!(html, "<p>Bundle pages: {start}–{end}</p>");
            }
            for field in ["original", "encryption"] {
                if let Some(error) = e[field]["error"].as_str() {
                    let _ = write!(html, "<p>{}: {}</p>", escaped(field), escaped(error));
                }
            }
            if let Some(diagnostics) = e["compiler_diagnostics"].as_str() {
                if !diagnostics.is_empty() {
                    let _ = write!(
                        html,
                        "<p>Notice creation messages: {}</p>",
                        escaped(diagnostics)
                    );
                }
            }
            if let Some(reason) = e["hold"]["reason"].as_str() {
                let _ = write!(html, "<p>Withheld: {}</p>", escaped(reason));
            }
            checks(&mut html, e.get("effective_checks").unwrap_or(&e["checks"]));
            html.push_str("</details>");
        }
    }
    html.push_str("</html>");
    crate::atomic(&dir.join("run.json"), &json)?;
    crate::atomic(&dir.join("report.html"), html.as_bytes())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn escapes_untrusted_content() {
        assert_eq!(
            escaped("<x a=\"'&\">"),
            "&lt;x a=&quot;&#39;&amp;&quot;&gt;"
        );
    }
}
