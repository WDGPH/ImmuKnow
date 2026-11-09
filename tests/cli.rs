//! End-to-end coverage of the public executable and portable run artifacts.
use serde_json::{Value, json};
use std::{
    fs,
    path::{Path, PathBuf},
    process::{Command, Output, Stdio},
};
use tempfile::TempDir;

fn cli(cwd: &Path, args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_immuknow"))
        .current_dir(cwd)
        .args(args)
        .output()
        .unwrap()
}
fn success(output: &Output) {
    assert!(
        output.status.success(),
        "status: {}\nstdout: {}\nstderr: {}",
        output.status,
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
}
fn copy_tree(source: &Path, destination: &Path) {
    fs::create_dir_all(destination).unwrap();
    for item in fs::read_dir(source).unwrap() {
        let item = item.unwrap();
        let to = destination.join(item.file_name());
        if item.file_type().unwrap().is_dir() {
            copy_tree(&item.path(), &to);
        } else {
            fs::copy(item.path(), to).unwrap();
        }
    }
}
fn p(path: &Path) -> &str {
    path.to_str().unwrap()
}

#[test]
fn native_project_journey_without_python_or_uv() {
    let fixture = Project::new();
    let project = fixture.root.join("Relocated projet Élodie");
    copy_tree(&fixture.config, &project.join("config"));
    copy_tree(&fixture.templates, &project.join("templates"));
    fs::remove_dir_all(project.join("templates/lib/immuknow")).unwrap();
    let input = project.join("input/sample");
    fs::create_dir_all(&input).unwrap();
    let mut reader = csv::Reader::from_path(&fixture.csv).unwrap();
    let mut writer = csv::Writer::from_path(input.join("sample_students.csv")).unwrap();
    writer.write_record(reader.headers().unwrap()).unwrap();
    writer
        .write_record(&reader.records().next().unwrap().unwrap())
        .unwrap();
    writer.flush().unwrap();
    fs::write(
        input.join("sample_assignments.json"),
        serde_json::to_vec(&json!([
            {"client_id":"0000000001","template":"overdue_agents_v1.en.typ"}
        ]))
        .unwrap(),
    )
    .unwrap();
    let native = |args: &[&str]| {
        Command::new(env!("CARGO_BIN_EXE_immuknow"))
            .current_dir(&fixture.root)
            .env("PATH", "")
            .args(args)
            .output()
            .unwrap()
    };
    let root = p(&project);
    assert!(
        !native(&["project", "check", "--project", root])
            .status
            .success()
    );
    success(&native(&["project", "sync", "--project", root]));
    success(&native(&["project", "sync", "--project", root]));
    let authored = project.join("templates/overdue_agents_v1.en.typ");
    let before = fs::read(&authored).unwrap();
    let library = project.join("templates/lib/immuknow");
    fs::write(library.join("unexpected.typ"), "Extra file").unwrap();
    assert!(
        !native(&["project", "check", "--project", root])
            .status
            .success()
    );
    assert!(
        !native(&["project", "sync", "--project", root])
            .status
            .success()
    );
    assert!(library.join("unexpected.typ").exists());
    success(&native(&[
        "project",
        "sync",
        "--project",
        root,
        "--replace",
    ]));
    assert!(!library.join("unexpected.typ").exists());
    assert_eq!(fs::read(&authored).unwrap(), before);
    success(&native(&["project", "check", "--project", root]));
    let checked = native(&["project", "check", "--project", root, "--sample"]);
    success(&checked);
    assert!(!String::from_utf8_lossy(&checked.stderr).contains("report.html"));
    assert!(!project.join("runs").exists());
    let prepared = native(&["prepare", "--sample", "--project", root]);
    success(&prepared);
    let value: Value = serde_json::from_slice(&prepared.stdout).unwrap();
    assert_eq!(value["entries"].as_array().unwrap().len(), 1);
    let output = project.join("runs");
    success(&native(&[
        "run",
        "--sample",
        "--project",
        root,
        "--output",
        p(&output),
        "--progress",
        "off",
    ]));
    let [run]: [PathBuf; 1] = fs::read_dir(&output)
        .unwrap()
        .map(|e| e.unwrap().path())
        .collect::<Vec<_>>()
        .try_into()
        .unwrap();
    let record: Value = serde_json::from_slice(&fs::read(run.join("run.json")).unwrap()).unwrap();
    assert!(matches!(
        record["status"].as_str(),
        Some("completed" | "completed_with_warnings")
    ));
    assert_eq!(record["entries"][0]["original"]["status"], "completed");
    assert!(!project.join(".venv").exists());

    fs::write(project.join("sample.json"), r#"{"csv":"input/sample/sample_students.csv","assignments":"input/sample/sample_assignments.json"}"#).unwrap();
    success(&native(&["prepare", "--sample", "--project", root]));
    assert!(
        !native(&[
            "run",
            "--sample",
            "--project",
            root,
            "--template",
            "anything.typ"
        ])
        .status
        .success()
    );
    assert!(
        !native(&["run", "--sample", "--project", root, "clients.csv"])
            .status
            .success()
    );
    for invalid in [
        "../input.csv",
        "/input.csv",
        "C:/input.csv",
        "..\\input.csv",
        "",
        "missing.csv",
    ] {
        fs::write(
            project.join("sample.json"),
            serde_json::to_vec(
                &json!({"csv": invalid,"assignments":"input/sample/sample_assignments.json"}),
            )
            .unwrap(),
        )
        .unwrap();
        assert!(
            !native(&["prepare", "--sample", "--project", root])
                .status
                .success(),
            "accepted {invalid}"
        );
    }
    fs::write(project.join("sample.json"), r#"{"csv":"input/sample/sample_students.csv","csv":"input/sample/sample_students.csv","assignments":"input/sample/sample_assignments.json"}"#).unwrap();
    assert!(
        !native(&["prepare", "--sample", "--project", root])
            .status
            .success()
    );

    #[cfg(unix)]
    {
        fs::remove_dir_all(&library).unwrap();
        std::os::unix::fs::symlink(&fixture.templates, &library).unwrap();
        assert!(
            !native(&["project", "sync", "--project", root, "--replace"])
                .status
                .success()
        );
        assert!(
            !native(&["project", "check", "--project", root])
                .status
                .success()
        );
        fs::write(
            project.join("sample.json"),
            r#"{"csv":"linked.csv","assignments":"input/sample/sample_assignments.json"}"#,
        )
        .unwrap();
        std::os::unix::fs::symlink(&fixture.csv, project.join("linked.csv")).unwrap();
        assert!(
            !native(&["prepare", "--sample", "--project", root])
                .status
                .success()
        );
    }
}
struct Project {
    _temp: TempDir,
    root: PathBuf,
    config: PathBuf,
    templates: PathBuf,
    csv: PathBuf,
    assignments: PathBuf,
    runs: PathBuf,
}

#[test]
fn optional_deadlines_reach_prepared_facts_and_bad_order_preserves_source_rows() {
    let project = Project::new();
    let parameters = project.config.join("parameters.yaml");
    let original = fs::read_to_string(&parameters).unwrap();
    fs::write(
        &parameters,
        format!("{original}\ndate_due: '2025-04-20'\ndate_of_suspension: '2025-05-01'\n"),
    )
    .unwrap();
    let prepared = cli(
        &project.root,
        &[
            "prepare",
            p(&project.csv),
            "--template",
            p(&project.templates.join("overdue_agents_v1.en.typ")),
            "--config",
            p(&project.config),
        ],
    );
    success(&prepared);
    let record: Value = serde_json::from_slice(&prepared.stdout).unwrap();
    for entry in record["entries"].as_array().unwrap() {
        assert_eq!(entry["notice"]["date_due"], "2025-04-20");
        assert_eq!(entry["notice"]["date_of_suspension"], "2025-05-01");
    }
    // A due date is optional; skipping it still compares delivery to suspension.
    fs::write(
        &parameters,
        format!("{original}\ndate_of_suspension: '2025-04-07'\n"),
    )
    .unwrap();
    let failed = project.run();
    assert!(!failed.status.success());
    assert!(
        String::from_utf8_lossy(&failed.stderr)
            .contains("date_of_suspension must be after date_of_delivery")
    );
    let (_, record) = project.record();
    assert_eq!(record["entries"].as_array().unwrap().len(), 5);
}
impl Project {
    fn new() -> Self {
        let temp = tempfile::tempdir().unwrap();
        let root = temp.path().to_path_buf();
        let resources = root.join("exported resources");
        success(&cli(&root, &["resources", "--output", p(&resources)]));
        assert!(!resources.join("config").exists());
        let config = root.join("project config");
        copy_tree(
            &Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/config"),
            &config,
        );
        let templates = root.join("unbranded templates");
        copy_tree(
            &Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/templates"),
            &templates,
        );
        copy_tree(&resources.join("typst"), &templates.join("lib/immuknow"));
        let csv = root.join("input.csv");
        let mut w = csv::Writer::from_path(&csv).unwrap();
        w.write_record([
            "school_name",
            "client_id",
            "first_name",
            "last_name",
            "date_of_birth",
            "board_name",
            "street_address_line_1",
            "street_address_line_2",
            "city",
            "province",
            "postal_code",
            "overdue_disease",
            "overdue_agent",
            "imms_given",
        ])
        .unwrap();
        for i in 1..=5 {
            w.write_record([
                "School - 001",
                &format!("{i:010}"),
                "Alice",
                "Example",
                "2015-01-02",
                "Board",
                "123 Main St",
                "",
                "Guelph",
                "ON",
                "N1H 2T2",
                "Measles - 2",
                "M",
                "2020-05-01 - MMR - Valid;",
            ])
            .unwrap();
        }
        w.flush().unwrap();
        let assignments = root.join("assignments.json");
        let runs = root.join("runs");
        let selection = [
            "overdue_agents_v1.en.typ",
            "overdue_agents_v1.fr.typ",
            "overdue_agents_v1.en.typ",
            "custom.en.typ",
            "package.en.typ",
        ];
        let a: Vec<_> = selection
            .iter()
            .enumerate()
            .map(|(i, template)| json!({"client_id":format!("{:010}", i+1),"template":template}))
            .collect();
        fs::write(&assignments, serde_json::to_vec(&a).unwrap()).unwrap();
        fs::write(templates.join("custom.en.typ"), "#let notice = json(sys.inputs.at(\"data\"))\nUseful custom notice. Client ID: #notice.client_id\n").unwrap();
        fs::write(
            templates.join("package.en.typ"),
            "#import \"@preview/fictional:1.0.0\": *\n",
        )
        .unwrap();
        let fr = templates.join("overdue_agents_v1.fr.typ");
        let mut content = fs::read_to_string(&fr).unwrap();
        content.push_str("\n#panic(\"deliberate notice failure\")\n");
        fs::write(fr, content).unwrap();
        Self {
            _temp: temp,
            root,
            config,
            templates,
            csv,
            assignments,
            runs,
        }
    }
    fn run(&self) -> Output {
        cli(
            &self.root,
            &[
                "run",
                p(&self.csv),
                "--notice-assignments",
                p(&self.assignments),
                "--templates",
                p(&self.templates),
                "--config",
                p(&self.config),
                "--output",
                p(&self.runs),
            ],
        )
    }
    fn record(&self) -> (PathBuf, Value) {
        let mut found = Vec::new();
        for e in fs::read_dir(&self.runs).unwrap() {
            let run = e.unwrap().path();
            if run.join("run.json").is_file() {
                found.push(run);
            }
        }
        assert_eq!(found.len(), 1, "expected one saved run: {found:?}");
        let run = found.remove(0);
        let record = serde_json::from_slice(&fs::read(run.join("run.json")).unwrap()).unwrap();
        (run, record)
    }
}

#[test]
fn bounded_compilation_matches_one_worker_through_row_failures() {
    let project = Project::new();
    let config = project.config.join("parameters.yaml");
    let contents = fs::read_to_string(&config)
        .unwrap()
        .replace("enabled: false\n  password:", "enabled: true\n  password:");
    fs::write(config, contents).unwrap();
    let mut records = Vec::new();
    for workers in ["1", "2"] {
        let output_dir = project.root.join(format!("workers-{workers}"));
        let output = cli(
            &project.root,
            &[
                "run",
                p(&project.csv),
                "--notice-assignments",
                p(&project.assignments),
                "--templates",
                p(&project.templates),
                "--config",
                p(&project.config),
                "--output",
                p(&output_dir),
                "--timestamp",
                "1793534400",
                "--compile-workers",
                workers,
                "--encryption-workers",
                workers,
                "--progress",
                "off",
            ],
        );
        assert!(
            !output.status.success(),
            "deliberate row failures must be reported"
        );
        let directory = fs::read_dir(&output_dir)
            .unwrap()
            .next()
            .unwrap()
            .unwrap()
            .path();
        let record: Value =
            serde_json::from_slice(&fs::read(directory.join("run.json")).unwrap()).unwrap();
        assert_eq!(record["status"], "completed_with_failures");
        records.push(record);
    }
    for (before, after) in records[0]["entries"]
        .as_array()
        .unwrap()
        .iter()
        .zip(records[1]["entries"].as_array().unwrap())
    {
        for field in [
            "row_key",
            "client_id",
            "notice",
            "assignment",
            "facts",
            "original",
            "checks",
            "effective_checks",
            "render_report",
            "routing",
            "bundle",
        ] {
            assert_eq!(
                before[field], after[field],
                "row {} field {field}",
                before["row_key"]
            );
        }
        for field in ["status", "algorithm", "revision"] {
            assert_eq!(before["encryption"][field], after["encryption"][field]);
        }
    }
    assert_eq!(records[0]["bundles"], records[1]["bundles"]);
    let rows = records[1]["entries"].as_array().unwrap();
    assert_eq!(rows.len(), 5);
    assert_eq!(rows[1]["original"]["status"], "failed");
    assert_eq!(rows[2]["original"]["status"], "completed");
    assert_eq!(rows[3]["encryption"]["status"], "completed");
}

#[test]
fn exported_resources_work_outside_checkout_and_mixed_rows_remain_associated() {
    let project = Project::new();
    let config = project.config.join("parameters.yaml");
    let contents = fs::read_to_string(&config)
        .unwrap()
        .replace("enabled: false\n  password:", "enabled: true\n  password:");
    fs::write(config, contents).unwrap();
    let output = project.run();
    let (run, record) = project.record();
    assert!(!output.status.success(), "partial run must be signaled");
    assert_eq!(record["status"], "completed_with_failures");
    let rows = record["entries"].as_array().unwrap();
    assert_eq!(rows.len(), 5);
    for (i, row) in rows.iter().enumerate() {
        assert_eq!(row["row_key"], format!("row-{:06}", i + 1));
        assert_eq!(row["client_id"], format!("{:010}", i + 1));
    }
    for i in [0, 2, 3] {
        assert_eq!(
            rows[i]["original"]["status"], "completed",
            "row {i}: {}",
            rows[i]
        );
        assert!(
            run.join(rows[i]["original"]["path"].as_str().unwrap())
                .is_file()
        );
    }
    for i in [1, 4] {
        assert_eq!(
            rows[i]["original"]["status"], "failed",
            "row {i}: {}",
            rows[i]
        );
        assert!(rows[i]["bundle"].is_null());
    }
    assert!(
        rows[3]["checks"]
            .as_array()
            .unwrap()
            .iter()
            .any(|c| c["code"] == "render.evidence_failed" && c["status"] == "fail")
    );
    let review = record["bundles"]
        .as_array()
        .unwrap()
        .iter()
        .find(|b| b["route"] == "review")
        .expect("review bundle");
    assert!(
        review["members"]
            .as_array()
            .unwrap()
            .contains(&rows[3]["row_key"])
    );
    assert!(
        record["bundles"]
            .as_array()
            .unwrap()
            .iter()
            .filter(|b| b["route"] == "deliverable")
            .all(|b| !b["members"]
                .as_array()
                .unwrap()
                .contains(&rows[3]["row_key"]))
    );
    for i in [0, 2, 3] {
        assert_eq!(rows[i]["encryption"]["status"], "completed");
        let path = run.join(rows[i]["encryption"]["path"].as_str().unwrap());
        let encrypted = lopdf::Document::load(&path).unwrap();
        assert!(encrypted.is_encrypted());
        let details = encrypted.get_encrypted().unwrap();
        assert_eq!(details.get(b"R").unwrap().as_i64().unwrap(), 6);
        assert!(
            lopdf::Document::load_with_options(
                &path,
                lopdf::LoadOptions::with_password("20150102")
            )
            .is_ok()
        );
        assert!(
            lopdf::Document::load_with_options(&path, lopdf::LoadOptions::with_password("wrong"))
                .is_err()
        );
    }
    let raw = fs::read_to_string(run.join("run.json")).unwrap();
    assert!(!raw.contains("20150102"));
    assert!(run.join("report.html").is_file());
    let first = rows[0]["row_key"].as_str().unwrap();
    let original = run.join(rows[0]["original"]["path"].as_str().unwrap());
    let before = fs::read(&original).unwrap();
    let old_bundles = record["bundles"].clone();
    let held = cli(
        &project.root,
        &[
            "rebundle",
            p(&run),
            "--withhold",
            first,
            "--reason",
            "Awaiting review",
        ],
    );
    let after: Value = serde_json::from_slice(&fs::read(run.join("run.json")).unwrap()).unwrap();
    assert_eq!(
        after["entries"][0]["routing"],
        "withheld",
        "{}",
        String::from_utf8_lossy(&held.stderr)
    );
    assert!(after["entries"][0]["bundle"].is_null());
    assert!(
        old_bundles
            .as_array()
            .unwrap()
            .iter()
            .all(|b| run.join(b["path"].as_str().unwrap()).is_file())
    );
    assert_eq!(fs::read(&original).unwrap(), before);
    let released = cli(&project.root, &["rebundle", p(&run), "--release", first]);
    let after: Value = serde_json::from_slice(&fs::read(run.join("run.json")).unwrap()).unwrap();
    assert_ne!(
        after["entries"][0]["routing"],
        "withheld",
        "{}",
        String::from_utf8_lossy(&released.stderr)
    );
    assert!(!after["entries"][0]["bundle"].is_null());
    assert_eq!(fs::read(&original).unwrap(), before);
    let lock = fs::OpenOptions::new()
        .create(true)
        .read(true)
        .write(true)
        .open(run.join(".run.lock"))
        .unwrap();
    lock.try_lock().unwrap();
    let snapshot = fs::read(run.join("run.json")).unwrap();
    let busy = cli(
        &project.root,
        &["rebundle", p(&run), "--withhold", first, "--reason", "busy"],
    );
    assert!(!busy.status.success());
    assert_eq!(fs::read(run.join("run.json")).unwrap(), snapshot);
}

#[test]
fn prepare_supports_both_selectors_and_does_not_create_runs() {
    let project = Project::new();
    let config = project.config.clone();
    let manifest = cli(
        &project.root,
        &[
            "prepare",
            p(&project.csv),
            "--notice-assignments",
            p(&project.assignments),
            "--templates",
            p(&project.templates),
            "--config",
            p(&config),
        ],
    );
    success(&manifest);
    let prepared: Value = serde_json::from_slice(&manifest.stdout).unwrap();
    assert_eq!(prepared["schema_version"], 1);
    assert_eq!(prepared["entries"].as_array().unwrap().len(), 5);
    for (i, e) in prepared["entries"].as_array().unwrap().iter().enumerate() {
        assert_eq!(e["notice"]["row_key"], format!("row-{:06}", i + 1));
        assert_eq!(e["notice"]["client_id"], e["source"]["client_id"]);
    }
    let mut assignments: Vec<Value> =
        serde_json::from_slice(&fs::read(&project.assignments).unwrap()).unwrap();
    assignments.push(json!({"client_id":"9999999999","template":"overdue_agents_v1.en.typ"}));
    fs::write(
        &project.assignments,
        serde_json::to_vec(&assignments).unwrap(),
    )
    .unwrap();
    let extra = cli(
        &project.root,
        &[
            "prepare",
            p(&project.csv),
            "--notice-assignments",
            p(&project.assignments),
            "--templates",
            p(&project.templates),
            "--config",
            p(&config),
        ],
    );
    success(&extra);
    let mut with_extra: Value = serde_json::from_slice(&extra.stdout).unwrap();
    for entry in with_extra["entries"].as_array_mut().unwrap() {
        let checks = entry["checks"].as_array_mut().unwrap();
        let warnings: Vec<_> = checks
            .iter()
            .filter(|check| check["code"] == "assignment.extra_manifest_row")
            .collect();
        assert_eq!(warnings.len(), 1);
        assert_eq!(warnings[0]["status"], "warn");
        checks.retain(|check| check["code"] != "assignment.extra_manifest_row");
    }
    assert_eq!(
        with_extra, prepared,
        "An extra assignment changes only its warning"
    );
    let template = project.templates.join("overdue_agents_v1.en.typ");
    let single = cli(
        &project.root,
        &[
            "prepare",
            p(&project.csv),
            "--template",
            p(&template),
            "--config",
            p(&config),
        ],
    );
    success(&single);
    let prepared: Value = serde_json::from_slice(&single.stdout).unwrap();
    assert!(
        prepared["entries"]
            .as_array()
            .unwrap()
            .iter()
            .all(|e| e["assignment"]["template"] == "overdue_agents_v1.en.typ")
    );
    assert!(!project.runs.exists());
}

#[test]
fn prepare_reports_stdout_failure() {
    let project = Project::new();
    select_first_rows(&project, &["overdue_agents_v1.en.typ"]);
    let mut child = Command::new(env!("CARGO_BIN_EXE_immuknow"))
        .current_dir(&project.root)
        .args([
            "prepare",
            p(&project.csv),
            "--notice-assignments",
            p(&project.assignments),
            "--templates",
            p(&project.templates),
            "--config",
            p(&project.config),
        ])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    // No reader remains: buffered output must surface the write/flush error.
    drop(child.stdout.take());
    let output = child.wait_with_output().unwrap();
    assert!(!output.status.success());
    let diagnostic = String::from_utf8_lossy(&output.stderr);
    assert!(diagnostic.contains("ImmuKnow:"), "{diagnostic}");
    assert!(!diagnostic.contains("panicked"), "{diagnostic}");
}

#[test]
fn school_reference_defaults_to_project_config_and_has_no_packaged_fallback() {
    let project = Project::new();
    let parameters = project.config.join("parameters.yaml");
    let settings = fs::read_to_string(&parameters).unwrap().replace(
        "school_validation:\n  enabled: false",
        "school_validation:\n  enabled: true",
    );
    let template = project.templates.join("overdue_agents_v1.en.typ");
    let prepare = || {
        cli(
            &project.root,
            &[
                "prepare",
                p(&project.csv),
                "--template",
                p(&template),
                "--config",
                p(&project.config),
            ],
        )
    };
    for reference in ["", "  reference_file: null\n", "  reference_file: '  '\n"] {
        fs::write(
            &parameters,
            settings.replace("  target_phu:", &format!("{reference}  target_phu:")),
        )
        .unwrap();
        success(&prepare());
    }
    fs::remove_file(project.config.join("school_reference.json")).unwrap();
    let missing = prepare();
    assert!(!missing.status.success());
    assert!(String::from_utf8_lossy(&missing.stderr).contains("Unable to read school reference"));
}

#[test]
fn failed_configuration_and_input_keep_source_row_accounting() {
    let project = Project::new();
    fs::write(
        project.config.join("parameters.yaml"),
        "encryption: [not an object]\n",
    )
    .unwrap();
    let result = project.run();
    assert!(!result.status.success());
    let (_, record) = project.record();
    assert_eq!(record["entries"].as_array().unwrap().len(), 5);
    for (i, e) in record["entries"].as_array().unwrap().iter().enumerate() {
        assert_eq!(e["source"]["client_id"], format!("{:010}", i + 1));
        assert_ne!(e["original"]["status"], "completed");
    }
}

fn select_first_rows(project: &Project, templates: &[&str]) {
    let mut reader = csv::Reader::from_path(&project.csv).unwrap();
    let headers = reader.headers().unwrap().clone();
    let rows: Vec<_> = reader
        .records()
        .take(templates.len())
        .map(Result::unwrap)
        .collect();
    drop(reader);
    let mut writer = csv::Writer::from_path(&project.csv).unwrap();
    writer.write_record(&headers).unwrap();
    for row in rows {
        writer.write_record(&row).unwrap();
    }
    writer.flush().unwrap();
    let assignments: Vec<_> = templates
        .iter()
        .enumerate()
        .map(|(i, t)| json!({"client_id": format!("{:010}", i+1), "template":t}))
        .collect();
    fs::write(
        &project.assignments,
        serde_json::to_vec(&assignments).unwrap(),
    )
    .unwrap();
}

#[test]
fn french_notice_with_school_mismatch_is_retained_for_review() {
    let project = Project::new();
    let french = project.templates.join("overdue_agents_v1.fr.typ");
    fs::copy(
        Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("tests/fixtures/templates/overdue_agents_v1.fr.typ"),
        &french,
    )
    .unwrap();
    select_first_rows(&project, &["overdue_agents_v1.fr.typ"]);
    let parameters = project.config.join("parameters.yaml");
    let config = fs::read_to_string(&parameters).unwrap().replace(
        "school_validation:\n  enabled: false",
        "school_validation:\n  enabled: true",
    );
    fs::write(parameters, config).unwrap();
    let _ = project.run();
    let (run, record) = project.record();
    assert_eq!(
        record["school_reference_source"],
        project
            .config
            .join("school_reference.json")
            .to_string_lossy()
            .as_ref()
    );
    assert_eq!(
        fs::read(run.join("resources/config/school-reference-snapshot.json")).unwrap(),
        fs::read(project.config.join("school_reference.json")).unwrap()
    );
    let row = &record["entries"][0];
    assert_eq!(row["original"]["status"], "completed", "{row}");
    assert!(
        run.join(row["original"]["path"].as_str().unwrap())
            .is_file()
    );
    assert!(
        row["checks"]
            .as_array()
            .unwrap()
            .iter()
            .any(|c| c["code"] == "data.school_match" && c["status"] == "fail")
    );
    assert_eq!(row["routing"], "review");
    assert!(
        record["bundles"]
            .as_array()
            .unwrap()
            .iter()
            .any(|b| b["route"] == "review"
                && b["members"].as_array().unwrap().contains(&row["row_key"]))
    );
}

#[test]
fn zero_bundle_size_leaves_originals_without_bundles() {
    let project = Project::new();
    select_first_rows(&project, &["overdue_agents_v1.en.typ"]);
    let parameters = project.config.join("parameters.yaml");
    let config = fs::read_to_string(&parameters)
        .unwrap()
        .replace("bundle_size: 100", "bundle_size: 0");
    fs::write(parameters, config).unwrap();
    let _ = project.run();
    let (run, record) = project.record();
    let row = &record["entries"][0];
    assert_eq!(row["original"]["status"], "completed", "{row}");
    assert!(
        run.join(row["original"]["path"].as_str().unwrap())
            .is_file()
    );
    assert!(record["bundles"].as_array().unwrap().is_empty());
    assert!(row["bundle"].is_null());
}

#[test]
fn unterminated_quoted_csv_is_rejected() {
    let project = Project::new();
    fs::write(&project.csv, b"school_name,client_id,first_name,last_name,date_of_birth\n\"unterminated,0000000001,Alice,Example,2015-01-02\n").unwrap();
    let result = project.run();
    assert!(!result.status.success(), "malformed CSV must be rejected");
    let (_, record) = project.record();
    assert!(
        record["entries"]
            .as_array()
            .unwrap()
            .iter()
            .all(|e| e["original"]["status"] != "completed")
    );
}

#[test]
fn rebundle_applies_global_and_client_policy_without_changing_observations() {
    let project = Project::new();
    select_first_rows(
        &project,
        &["overdue_agents_v1.en.typ", "overdue_agents_v1.en.typ"],
    );
    let template = project.templates.join("overdue_agents_v1.en.typ");
    let contents = fs::read_to_string(&template)
        .unwrap()
        .replace("https://example.org/records", "http://example.org/records");
    fs::write(template, contents).unwrap();
    let _ = project.run();
    let (run, record) = project.record();
    for row in record["entries"].as_array().unwrap() {
        assert!(
            row["checks"]
                .as_array()
                .unwrap()
                .iter()
                .any(|c| c["code"] == "content.link_https" && c["status"] == "warn"),
            "{row}"
        );
    }
    let policy = project.root.join("policy.json");
    fs::write(&policy, serde_json::to_vec(&json!({
        "rules":{"content.link_https":{"severity":"fail","reason":"Require HTTPS"}},
        "clients":[{"selector":{"scheme":"panorama","value":"0000000001"},"rules":{"content.link_https":{"severity":"warn","reason":"Review later"}}}]
    })).unwrap()).unwrap();
    let _ = cli(
        &project.root,
        &["rebundle", p(&run), "--policy", p(&policy)],
    );
    let updated: Value = serde_json::from_slice(&fs::read(run.join("run.json")).unwrap()).unwrap();
    for (index, status) in [(0, "warn"), (1, "fail")] {
        let row = &updated["entries"][index];
        assert!(
            row["checks"]
                .as_array()
                .unwrap()
                .iter()
                .any(|c| c["code"] == "content.link_https" && c["status"] == "warn")
        );
        assert!(
            row["effective_checks"]
                .as_array()
                .unwrap()
                .iter()
                .any(|c| c["code"] == "content.link_https" && c["status"] == status)
        );
    }
    assert_eq!(updated["entries"][1]["routing"], "review");
    fs::write(&policy, serde_json::to_vec(&json!({"rules":{"content.link_https":{"enabled":false,"reason":"Not applicable to this delivery"}}})).unwrap()).unwrap();
    let _ = cli(
        &project.root,
        &["rebundle", p(&run), "--policy", p(&policy)],
    );
    let updated: Value = serde_json::from_slice(&fs::read(run.join("run.json")).unwrap()).unwrap();
    assert!(
        updated["entries"][1]["effective_checks"]
            .as_array()
            .unwrap()
            .iter()
            .any(|c| c["code"] == "content.link_https"
                && c["status"] == "not_run"
                && c["disabled"] == true)
    );
    let report = fs::read_to_string(run.join("report.html")).unwrap();
    assert!(report.contains("content.link_https"));
}

#[test]
fn nested_selected_config_never_leaks_literal_encryption_password() {
    let project = Project::new();
    select_first_rows(&project, &["overdue_agents_v1.en.typ"]);
    let flat = project.root.join("flat-project");
    copy_tree(&project.templates, &flat);
    let config = flat.join("config");
    copy_tree(&project.config, &config);
    let parameters = config.join("parameters.yaml");
    let secret = "fixture-secret-not-to-save";
    let content = fs::read_to_string(&parameters)
        .unwrap()
        .replace("enabled: false\n  password:", "enabled: true\n  password:")
        .replace("{date_of_birth_iso_compact}", secret);
    fs::write(parameters, content).unwrap();
    let template = flat.join("overdue_agents_v1.en.typ");
    let result = cli(
        &project.root,
        &[
            "run",
            p(&project.csv),
            "--template",
            p(&template),
            "--config",
            p(&config),
            "--output",
            p(&project.runs),
        ],
    );
    success(&result);
    let (run, record) = project.record();
    let encrypted = run.join(
        record["entries"][0]["encryption"]["path"]
            .as_str()
            .expect("encrypted copy"),
    );
    assert!(
        lopdf::Document::load_with_options(&encrypted, lopdf::LoadOptions::with_password(secret))
            .is_ok()
    );
    fn no_secret(dir: &Path, secret: &str) {
        for entry in fs::read_dir(dir).unwrap() {
            let path = entry.unwrap().path();
            if path.is_dir() {
                no_secret(&path, secret);
            } else if let Ok(text) = fs::read_to_string(&path) {
                assert!(
                    !text.contains(secret),
                    "password leaked to {}",
                    path.display()
                );
            }
        }
    }
    no_secret(&run.join("resources"), secret);
    assert!(
        !fs::read_to_string(run.join("run.json"))
            .unwrap()
            .contains(secret)
    );
    assert!(
        !fs::read_to_string(run.join("report.html"))
            .unwrap()
            .contains(secret)
    );
}

#[test]
fn missing_password_fact_fails_one_copy_and_later_rows_continue() {
    let project = Project::new();
    select_first_rows(
        &project,
        &["overdue_agents_v1.en.typ", "overdue_agents_v1.en.typ"],
    );
    let mut reader = csv::Reader::from_path(&project.csv).unwrap();
    let headers = reader.headers().unwrap().clone();
    let postal = headers.iter().position(|h| h == "postal_code").unwrap();
    let rows: Vec<_> = reader.records().map(Result::unwrap).collect();
    drop(reader);
    let mut writer = csv::Writer::from_path(&project.csv).unwrap();
    writer.write_record(&headers).unwrap();
    for (index, row) in rows.iter().enumerate() {
        let values: Vec<_> = row
            .iter()
            .enumerate()
            .map(|(i, value)| if index == 0 && i == postal { "" } else { value })
            .collect();
        writer.write_record(values).unwrap();
    }
    writer.flush().unwrap();
    let parameters = project.config.join("parameters.yaml");
    let config = fs::read_to_string(&parameters)
        .unwrap()
        .replace("enabled: false\n  password:", "enabled: true\n  password:")
        .replace("{date_of_birth_iso_compact}", "{postal_code}");
    fs::write(parameters, config).unwrap();
    let result = project.run();
    assert!(!result.status.success());
    let (run, record) = project.record();
    let rows = record["entries"].as_array().unwrap();
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[0]["original"]["status"], "completed");
    assert!(
        run.join(rows[0]["original"]["path"].as_str().unwrap())
            .is_file()
    );
    assert_eq!(rows[0]["encryption"]["status"], "failed");
    assert_eq!(rows[0]["routing"], "review");
    let review_csv =
        run.join(Path::new(rows[0]["bundle"]["path"].as_str().unwrap()).with_extension("csv"));
    let findings = csv::Reader::from_path(review_csv)
        .unwrap()
        .deserialize::<std::collections::BTreeMap<String, String>>()
        .map(Result::unwrap)
        .collect::<Vec<_>>();
    assert!(
        findings
            .iter()
            .any(|finding| finding["check_code"] == "encryption.failed"
                && finding["status"] == "fail"
                && finding["message"].contains("password")
                && finding["message"].contains("missing"))
    );
    assert_eq!(rows[1]["original"]["status"], "completed");
    assert_eq!(rows[1]["encryption"]["status"], "completed");
    let encrypted = run.join(rows[1]["encryption"]["path"].as_str().unwrap());
    assert!(
        lopdf::Document::load_with_options(
            &encrypted,
            lopdf::LoadOptions::with_password("N1H 2T2")
        )
        .is_ok()
    );
}

#[test]
fn failed_rebundle_records_attempt_and_keeps_existing_delivery_and_decisions() {
    let project = Project::new();
    select_first_rows(
        &project,
        &["overdue_agents_v1.en.typ", "overdue_agents_v1.en.typ"],
    );
    let result = project.run();
    success(&result);
    let (run, before) = project.record();
    let rows = before["entries"].as_array().unwrap();
    let original = run.join(rows[0]["original"]["path"].as_str().unwrap());
    let saved_original = fs::read(&original).unwrap();
    let original_bundle = run.join(before["bundles"][0]["path"].as_str().unwrap());
    let bundle_bytes = fs::read(&original_bundle).unwrap();
    fs::write(&original, b"deliberately corrupted PDF").unwrap();
    let policy = project.root.join("failure-policy.json");
    fs::write(
        &policy,
        serde_json::to_vec(
            &json!({"rules":{"content.link_https":{"severity":"fail","reason":"Stricter policy"}}}),
        )
        .unwrap(),
    )
    .unwrap();
    let second_key = rows[1]["row_key"].as_str().unwrap();
    let result = cli(
        &project.root,
        &[
            "rebundle",
            p(&run),
            "--withhold",
            second_key,
            "--reason",
            "Hold pending review",
            "--policy",
            p(&policy),
        ],
    );
    assert!(
        !result.status.success(),
        "corrupt source must fail assembly"
    );
    let after: Value = serde_json::from_slice(&fs::read(run.join("run.json")).unwrap()).unwrap();
    assert_eq!(after["bundles"], before["bundles"]);
    assert_eq!(after["configured_settings"], before["configured_settings"]);
    for (old, new) in before["entries"]
        .as_array()
        .unwrap()
        .iter()
        .zip(after["entries"].as_array().unwrap())
    {
        assert_eq!(new["hold"], old["hold"]);
        assert_eq!(new["bundle"], old["bundle"]);
        assert_eq!(new["effective_checks"], old["effective_checks"]);
    }
    let attempts = after["delivery_attempts"].as_array().unwrap();
    assert_eq!(
        attempts.len(),
        before["delivery_attempts"].as_array().unwrap().len() + 1
    );
    assert_eq!(attempts.last().unwrap()["status"], "failed");
    assert_eq!(fs::read(original_bundle).unwrap(), bundle_bytes);
    fs::write(original, saved_original).unwrap();
}

#[test]
fn project_shortcut_supports_explicit_choices_overrides_and_quiet_output() {
    let project = Project::new();
    select_first_rows(&project, &["overdue_agents_v1.en.typ"]);
    let authored = project.root.join("authored project");
    copy_tree(&project.templates, &authored.join("templates"));
    copy_tree(&project.config, &authored.join("config"));
    let selected = cli(
        &project.root,
        &[
            "prepare",
            p(&project.csv),
            "--project",
            p(&authored),
            "--notices",
            p(&project.assignments),
        ],
    );
    success(&selected);
    let facts: Value = serde_json::from_slice(&selected.stdout).unwrap();
    let from_project = cli(
        &authored,
        &[
            "prepare",
            p(&project.csv),
            "--notices",
            p(&project.assignments),
        ],
    );
    success(&from_project);
    let local_facts: Value = serde_json::from_slice(&from_project.stdout).unwrap();
    assert_eq!(facts["entries"], local_facts["entries"]);
    assert_eq!(
        facts["entries"][0]["assignment"]["template"],
        "overdue_agents_v1.en.typ"
    );
    let single = cli(
        &project.root,
        &[
            "prepare",
            p(&project.csv),
            "--project",
            p(&authored),
            "--template",
            "overdue_agents_v1.en.typ",
        ],
    );
    success(&single);
    let single_facts: Value = serde_json::from_slice(&single.stdout).unwrap();
    assert_eq!(facts["entries"], single_facts["entries"]);
    // Explicit paths still work even when the project defaults are absent.
    fs::rename(
        authored.join("templates"),
        authored.join("unused-templates"),
    )
    .unwrap();
    fs::rename(authored.join("config"), authored.join("unused-config")).unwrap();
    let quiet = cli(
        &project.root,
        &[
            "run",
            p(&project.csv),
            "--project",
            p(&authored),
            "--notices",
            p(&project.assignments),
            "--templates",
            p(&project.templates),
            "--config",
            p(&project.config),
            "--output",
            p(&project.runs),
            "--progress",
            "off",
            "--emoji",
        ],
    );
    success(&quiet);
    assert!(quiet.stderr.is_empty());
    let saved = PathBuf::from(String::from_utf8(quiet.stdout).unwrap().trim());
    let record: Value = serde_json::from_slice(&fs::read(saved).unwrap()).unwrap();
    assert_eq!(record["entries"].as_array().unwrap().len(), 1);
}

#[test]
fn bundles_group_selected_notice_variant_and_optionally_language() {
    for (group_by, expected) in [
        (
            "notice_variant",
            json!([
                {"group": ["overdue_agents_v1"], "members": ["row-000001", "row-000002", "row-000005"]},
                {"group": ["overdue_diseases_v1"], "members": ["row-000003", "row-000004"]}
            ]),
        ),
        (
            "[notice_variant, language]",
            json!([
                {"group": ["overdue_agents_v1", "en"], "members": ["row-000001", "row-000005"]},
                {"group": ["overdue_agents_v1", "fr"], "members": ["row-000002"]},
                {"group": ["overdue_diseases_v1", "en"], "members": ["row-000003"]},
                {"group": ["overdue_diseases_v1", "fr"], "members": ["row-000004"]}
            ]),
        ),
    ] {
        let project = Project::new();
        fs::copy(
            Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("tests/fixtures/templates/overdue_agents_v1.fr.typ"),
            project.templates.join("overdue_agents_v1.fr.typ"),
        )
        .unwrap();
        select_first_rows(
            &project,
            &[
                "overdue_agents_v1.en.typ",
                "overdue_agents_v1.fr.typ",
                "overdue_diseases_v1.en.typ",
                "overdue_diseases_v1.fr.typ",
                "overdue_agents_v1.en.typ",
            ],
        );
        let parameters = project.config.join("parameters.yaml");
        let config = fs::read_to_string(&parameters)
            .unwrap()
            .replace("group_by: null", &format!("group_by: {group_by}"));
        fs::write(parameters, config).unwrap();
        success(&project.run());
        let (_, record) = project.record();
        let actual: Vec<_> = record["bundles"]
            .as_array()
            .unwrap()
            .iter()
            .map(|bundle| json!({"group": bundle["group"], "members": bundle["members"]}))
            .collect();
        assert_eq!(json!(actual), expected);
    }
}
