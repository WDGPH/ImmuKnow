//! Public warning review commands operate on saved runs without touching artifacts.
use serde_json::{Value, json};
use std::{fs, process::Command};

#[test]
fn acknowledge_refresh_and_revoke_preserve_the_saved_run() {
    let run = tempfile::tempdir().unwrap();
    let record = json!({
        "run_schema_version": 2, "run_id":"fictional-review", "record_revision":0, "exports":null, "status": "completed_with_warnings",
        "resources": {"sha256": "a".repeat(64)},
        "project_resources": {"templates": {"notice.typ": "b".repeat(64)}},
        "entries": [{"row_key":"row-000001", "next_finding_sequence":2,
            "checks":[{"finding_key":"check-000001", "code":"content.link_https", "status":"warn", "subjects":[{"kind":"url", "urls":["http://example.test/?private=1"]}]}],
            "effective_checks":[{"finding_key":"check-000001", "status":"warn", "disabled":false, "policy_reason":null}]
        }], "delivery_attempts": [], "bundles": []
    });
    fs::write(
        run.path().join("run.json"),
        serde_json::to_vec(&record).unwrap(),
    )
    .unwrap();
    fs::write(run.path().join("artifact.pdf"), b"fictional PDF").unwrap();
    let call = |args: &[&str]| {
        Command::new(env!("CARGO_BIN_EXE_immuknow"))
            .args(args)
            .output()
            .unwrap()
    };
    let path = run.path().to_str().unwrap();
    let listing = call(&["warnings", path]);
    assert!(listing.status.success());
    let output = String::from_utf8(listing.stdout).unwrap();
    assert!(!output.contains("private"));
    let id = output.split_whitespace().next().unwrap();
    assert_eq!(id.len(), 64);
    let acknowledged = call(&["acknowledge", path, id, "--reason", "Reviewed"]);
    assert!(
        acknowledged.status.success(),
        "{}",
        String::from_utf8_lossy(&acknowledged.stderr)
    );
    let after_ack: Value =
        serde_json::from_slice(&fs::read(run.path().join("run.json")).unwrap()).unwrap();
    let first_findings = run
        .path()
        .join(after_ack["exports"]["findings"]["path"].as_str().unwrap());
    let refreshed = call(&["warnings", path, "--refresh"]);
    assert!(refreshed.status.success());
    assert!(
        String::from_utf8(refreshed.stdout)
            .unwrap()
            .contains("acknowledged")
    );
    let after_refresh: Value =
        serde_json::from_slice(&fs::read(run.path().join("run.json")).unwrap()).unwrap();
    assert_eq!(
        after_refresh, after_ack,
        "valid refresh reuses its matching CSV pair"
    );
    let csv = fs::read_to_string(&first_findings).unwrap();
    let findings: Vec<std::collections::BTreeMap<String, String>> =
        csv::Reader::from_reader(csv.as_bytes())
            .deserialize()
            .map(Result::unwrap)
            .collect();
    let warning = findings
        .iter()
        .find(|row| row["code"] == "content.link_https")
        .unwrap();
    assert_eq!(
        serde_json::from_str::<Value>(&warning["acknowledged_issue_ids"]).unwrap(),
        json!([id])
    );
    assert!(!run.path().join("report.html").exists());
    let revoked = call(&[
        "acknowledge",
        path,
        id,
        "--revoke",
        "--reason",
        "Review withdrawn",
    ]);
    assert!(revoked.status.success());
    let mut final_record: Value =
        serde_json::from_slice(&fs::read(run.path().join("run.json")).unwrap()).unwrap();
    let history = final_record
        .as_object_mut()
        .unwrap()
        .remove("warning_reviews")
        .unwrap();
    assert_eq!(history["history"].as_array().unwrap().len(), 2);
    assert_eq!(final_record["record_revision"], 2);
    assert_ne!(final_record["exports"], after_ack["exports"]);
    assert!(
        first_findings.is_file(),
        "earlier review export remains immutable"
    );
    final_record["record_revision"] = json!(0);
    final_record["exports"] = Value::Null;
    assert_eq!(final_record, record);
    assert_eq!(
        fs::read(run.path().join("artifact.pdf")).unwrap(),
        b"fictional PDF"
    );
}
