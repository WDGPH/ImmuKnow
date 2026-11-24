use std::{fs, path::PathBuf, process::Command};

#[test]
fn failed_run_lists_saved_reports_and_preserves_redirected_stdout() {
    let project = tempfile::Builder::new()
        .prefix("ImmuKnow (sample) ")
        .tempdir()
        .unwrap();
    fs::create_dir(project.path().join("templates")).unwrap();
    fs::write(
        project.path().join("templates/notice.en.typ"),
        "Sample notice",
    )
    .unwrap();
    let output = Command::new(env!("CARGO_BIN_EXE_immuknow"))
        .current_dir(project.path())
        .args([
            "run",
            "missing.csv",
            "--template",
            "templates/notice.en.typ",
            "--progress",
            "plain",
        ])
        .output()
        .unwrap();

    let stdout = String::from_utf8(output.stdout).unwrap();
    let stderr = String::from_utf8(output.stderr).unwrap();
    assert!(!output.status.success(), "{stderr}");
    assert!(
        stderr.contains("Run incomplete — review saved reports"),
        "{stderr}"
    );
    assert!(!stderr.contains("Finished"), "{stderr}");
    assert_eq!(stdout.lines().count(), 1, "{stdout}");
    let record = PathBuf::from(stdout.trim());
    assert_eq!(record, record.canonicalize().unwrap());
    assert!(record.parent().unwrap().extension().unwrap() == "incomplete");
    assert!(
        stderr.contains(&format!(
            "Run record: {}",
            dunce::simplified(&record).display()
        )),
        "{stderr}"
    );
    assert!(
        stderr.contains("Records:") && stderr.contains("Findings:"),
        "{stderr}"
    );
}
