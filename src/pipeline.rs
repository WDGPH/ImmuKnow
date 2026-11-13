//! Prepare client information, create notices, and save bundles and reports.
use crate::{
    bundles, compiler,
    input::{self, Config, PrepareOptions, Prepared, RowPreparation, Selection},
    pdf, policy, pool, report, resources, validation,
};
use anyhow::{Context, Result, bail, ensure};
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    fs::{self, File},
    path::{Path, PathBuf},
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

/// Reserve enough execution capacity for compilation and PDF protection to overlap.
/// Smaller machines keep one worker of each kind; explicit CLI values override this.
pub fn default_notice_workers() -> u8 {
    if std::thread::available_parallelism().is_ok_and(|cpus| cpus.get() >= 4) {
        2
    } else {
        1
    }
}

pub struct RunOptions {
    pub csv: PathBuf,
    pub selection: Selection,
    pub templates: PathBuf,
    pub config: PathBuf,
    pub output: PathBuf,
    pub encoding: Option<String>,
    pub timestamp: Option<i64>,
    pub compile_workers: u8,
    pub encryption_workers: u8,
    pub bundle_workers: u8,
}
/// A published run or saved-run update, which may still contain failed notices.
///
/// `succeeded` is false for `completed_with_failures`; warnings alone leave it true.
/// Fatal processing errors return `Err` instead, retaining staged work when possible.
pub struct RunResult {
    pub record: PathBuf,
    pub succeeded: bool,
    pub summary: RunSummary,
}

/// A processing failure with a discoverable saved run record.
#[derive(Debug)]
pub struct SavedRunFailure {
    pub record: PathBuf,
    pub message: String,
}
impl std::fmt::Display for SavedRunFailure {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(&self.message)
    }
}
impl std::error::Error for SavedRunFailure {}
impl SavedRunFailure {
    fn new(dir: &Path, message: String) -> anyhow::Error {
        Self {
            record: dir.join("run.json"),
            message,
        }
        .into()
    }
    pub fn receipt(&self) -> Result<RunResult> {
        let record: Value = crate::read_json(&self.record)?;
        Ok(RunResult {
            record: self.record.clone(),
            succeeded: false,
            summary: RunSummary::from_record(&record),
        })
    }
}

/// Small receipts for terminal progress; no client information or worker-side output.
#[derive(Clone, Copy)]
pub enum Progress {
    Preparing,
    Notices {
        done: usize,
        total: usize,
        protected: usize,
    },
    Protecting {
        done: usize,
        total: usize,
    },
    Grouping {
        done: usize,
        total: usize,
    },
    Reporting,
}

#[derive(Default)]
pub struct RunSummary {
    pub report: report::Summary,
    pub records_path: String,
    pub findings_path: String,
    pub protection_requested: bool,
    pub grouping_requested: bool,
    pub run_findings: usize,
    pub rows: usize,
    pub originals: usize,
    pub pages: u64,
    pub protected: usize,
    pub groups: usize,
    pub review_groups: usize,
    pub warnings: usize,
    pub failed: usize,
    pub held: usize,
}
impl RunSummary {
    fn from_record(record: &Value) -> Self {
        let mut summary = Self {
            report: report::summary(record),
            records_path: record["exports"]["records"]["path"]
                .as_str()
                .unwrap_or("")
                .to_owned(),
            findings_path: record["exports"]["findings"]["path"]
                .as_str()
                .unwrap_or("")
                .to_owned(),
            protection_requested: record["configured_settings"]["encryption"]["enabled"] == true,
            grouping_requested: record["configured_settings"]["bundling"]["bundle_size"]
                .as_u64()
                .is_some_and(|n| n > 0),
            ..Self::default()
        };
        summary.run_findings = record["checks"]
            .as_array()
            .into_iter()
            .flatten()
            .filter(|check| matches!(check["status"].as_str(), Some("warn" | "fail")))
            .count();
        for entry in record["entries"].as_array().into_iter().flatten() {
            summary.rows += 1;
            if entry["original"]["status"] == "completed" {
                summary.originals += 1;
                summary.pages += entry["original"]["pages"].as_u64().unwrap_or(0);
            }
            summary.protected += usize::from(entry["encryption"]["status"] == "completed");
            let severity = bundles::severity(entry);
            summary.warnings += usize::from(severity == "warn");
            summary.failed += usize::from(
                severity == "fail"
                    || entry["original"]["status"] != "completed"
                    || entry["encryption"]["status"] == "failed",
            );
            summary.held += usize::from(entry["routing"] == "withheld");
        }
        for group in record["bundles"].as_array().into_iter().flatten() {
            if group["route"] == "review" {
                summary.review_groups += 1;
            } else {
                summary.groups += 1;
            }
        }
        summary
    }
}

pub(crate) fn lock(dir: &Path) -> Result<File> {
    let f = fs::OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(dir.join(".run.lock"))?;
    f.try_lock().context("This run is already in use")?;
    Ok(f)
}
fn timestamp(value: Option<i64>) -> Result<i64> {
    match value {
        Some(v) => Ok(v),
        None => Ok(SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs() as i64),
    }
}
fn copy_tree(
    source: &Path,
    destination: &Path,
    private_parameters: &Path,
    sanitized: &[u8],
) -> Result<()> {
    ensure!(
        !source.is_symlink() && source.is_dir(),
        "Resource directory is missing or is a symbolic link"
    );
    fs::create_dir_all(destination)?;
    for item in fs::read_dir(source)? {
        let item = item?;
        let path = item.path();
        ensure!(
            !path.is_symlink(),
            "Symbolic links are not allowed in project resources"
        );
        let target = destination.join(item.file_name());
        if path.is_dir() {
            copy_tree(&path, &target, private_parameters, sanitized)?;
        } else if path.is_file() {
            if path.canonicalize()? == private_parameters {
                fs::write(target, sanitized)?;
            } else {
                fs::copy(path, target)?;
            }
        } else if !path.is_file() {
            bail!("Unsupported project resource type");
        }
    }
    Ok(())
}
fn tree(path: &Path) -> Result<BTreeMap<PathBuf, String>> {
    fn walk(path: &Path, root: &Path, result: &mut BTreeMap<PathBuf, String>) -> Result<()> {
        ensure!(
            !path.is_symlink() && path.is_dir(),
            "Shared library is missing or is a symbolic link"
        );
        for item in fs::read_dir(path)? {
            let path = item?.path();
            ensure!(
                !path.is_symlink(),
                "Shared library cannot contain symbolic links"
            );
            if path.is_dir() {
                walk(&path, root, result)?;
            } else if path.is_file() {
                result.insert(
                    path.strip_prefix(root)?.to_owned(),
                    crate::hash(&fs::read(&path)?),
                );
            } else {
                bail!("Unsupported shared library entry");
            }
        }
        Ok(())
    }
    let mut result = BTreeMap::new();
    walk(path, path, &mut result)?;
    Ok(result)
}
fn redacted(config: &Config) -> Result<Value> {
    let mut settings = serde_json::to_value(config)?;
    if let Some(enc) = settings
        .get_mut("encryption")
        .and_then(Value::as_object_mut)
    {
        enc.remove("password");
    }
    Ok(settings)
}
fn source_entries(path: &Path, encoding: Option<&str>) -> Result<Vec<Value>> {
    Ok(input::source_rows(path, encoding)?
        .into_iter()
        .enumerate()
        .map(|(i, source)| {
            let id = source["client_id"].as_str().unwrap_or("").trim().to_owned();
            json!({
                "row_key": format!("row-{:06}", i + 1),
                "client_id": id,
                "source": source,
                "checks": [],
                "original": {"status": "not_run"},
                "encryption": {"status": "not_run"}
            })
        })
        .collect())
}
fn assign_entries(record: &mut Value, prepared: &[RowPreparation], encryption: bool) -> Result<()> {
    let entries = record["entries"]
        .as_array_mut()
        .context("Missing source entries")?;
    ensure!(
        entries.len() == prepared.len(),
        "Preparation did not account for every source row"
    );
    let mut failed_history_rows = 0usize;
    for (entry, outcome) in entries.iter_mut().zip(prepared) {
        let (key, checks) = match outcome {
            RowPreparation::Ready(p) => {
                entry["notice"] = p.notice.clone();
                entry["assignment"] = p.assignment.clone();
                entry["blocked_checks"] = json!([]);
                (p.notice["row_key"].clone(), &p.checks)
            }
            RowPreparation::Failed {
                row_key,
                assignment,
                checks,
            } => {
                entry["assignment"] = assignment.clone();
                failed_history_rows += usize::from(
                    checks
                        .iter()
                        .any(|c| c["code"] == "source.history_unusable"),
                );
                ensure!(
                    entry["row_key"] == *row_key,
                    "Prepared row identity mismatch"
                );
                (json!(row_key), checks)
            }
        };
        ensure!(entry["row_key"] == key, "Prepared row identity mismatch");
        entry["checks"] = json!(checks);
        entry["deferred_checks"] = json!([
            "notice.requirements",
            "notice.eligibility",
            "data.forecast_coverage",
            "content.agent_display"
        ]);
        entry["encryption"] = json!({"status": if encryption {"not_run"} else {"not_requested"}});
    }
    let total_rows = prepared.len();
    if failed_history_rows > 0 {
        let checks = record["checks"]
            .as_array_mut()
            .context("Missing run checks")?;
        checks.push(json!({"code":"data.history_cohort_incomplete","stage":"preparation","status":"warn","message":"Some histories could not be parsed; cohort validity coverage is incomplete.","measurements":{"total_rows":total_rows,"failed_history_rows":failed_history_rows}}));
    }
    Ok(())
}
fn options<'a>(
    source: &'a Path,
    selection: &'a Selection,
    config: &'a Path,
    templates: &'a Path,
    resource_root: &'a Path,
    encoding: Option<&'a str>,
) -> PrepareOptions<'a> {
    PrepareOptions {
        csv: source,
        selection,
        config_dir: config,
        templates,
        resources: resource_root,
        encoding,
    }
}
fn validate_project(templates: &Path, root: &Path) -> Result<()> {
    ensure!(
        tree(&templates.join("lib/immuknow"))? == tree(&root.join("typst"))?,
        "Project shared library differs from the supplied library"
    );
    Ok(())
}
fn prepare_data(
    opts: &RunOptions,
    resource_root: &Path,
    source: &Path,
    selection: &Selection,
    config_path: &Path,
    templates: &Path,
    c: &Config,
) -> Result<Vec<RowPreparation>> {
    input::prepare(
        &options(
            source,
            selection,
            config_path,
            templates,
            resource_root,
            opts.encoding.as_deref(),
        ),
        c,
    )
}
pub fn prepare(opts: &RunOptions) -> Result<Value> {
    let temp = tempfile::tempdir()?;
    resources::materialize(temp.path())?;
    let bytes = fs::read(&opts.csv)?;
    let source = temp.path().join("source.csv");
    fs::write(&source, &bytes)?;
    let mut record = json!({"schema_version":2,"engine":"typst 0.15.1","resources":resources::identity(),"input":{"sha256":crate::hash(&bytes)},"checks":[],"entries":source_entries(&source, opts.encoding.as_deref())?});
    drop(bytes);
    let c = input::config(&opts.config.join("parameters.yaml"))?;
    validate_project(&opts.templates, temp.path())?;
    let prepared = prepare_data(
        opts,
        temp.path(),
        &source,
        &opts.selection,
        &opts.config,
        &opts.templates,
        &c,
    )?;
    let validator = validation::Validator::new(temp.path())?;
    for outcome in &prepared {
        if let RowPreparation::Ready(p) = outcome {
            validator.payload(&p.notice)?;
        }
    }
    assign_entries(&mut record, &prepared, c.encryption.enabled)?;
    policy::validate(&record, &c, temp.path())?;
    for e in record["entries"].as_array_mut().unwrap() {
        e.as_object_mut().unwrap().remove("original");
        e.as_object_mut().unwrap().remove("encryption");
    }
    Ok(record)
}
fn add_check(entry: &mut Value, code: &str, message: &str) {
    entry["checks"]
        .as_array_mut()
        .unwrap()
        .push(json!({"code":code,"stage":"render","status":"fail","message":message}));
}
/// Save early progress, then double the row interval to avoid rewriting the full
/// record every 100 notices. Slow batches still save at the next row boundary
/// after 30 seconds. Final and error reports are written independently.
struct NoticeCheckpoint {
    next_row: usize,
    saved_at: Instant,
}
impl NoticeCheckpoint {
    fn new(now: Instant) -> Self {
        Self {
            next_row: 100,
            saved_at: now,
        }
    }
    fn due(&self, done: usize, now: Instant) -> bool {
        done >= self.next_row || now.duration_since(self.saved_at) >= Duration::from_secs(30)
    }
    fn saved(&mut self, done: usize, now: Instant) {
        self.next_row = done.saturating_mul(2);
        self.saved_at = now;
    }
}

fn process(
    dir: &Path,
    record: &mut Value,
    prepared: &[RowPreparation],
    c: &Config,
    timestamp: i64,
    compile_workers: u8,
    workers: u8,
    root: &Path,
    progress: &mut impl FnMut(Progress),
) -> Result<()> {
    let ready: Vec<(usize, &Prepared)> = prepared
        .iter()
        .enumerate()
        .filter_map(|(i, outcome)| match outcome {
            RowPreparation::Ready(p) => Some((i, p)),
            RowPreparation::Failed { .. } => None,
        })
        .collect();
    let failed = prepared.len() - ready.len();
    progress(Progress::Notices {
        done: failed,
        total: prepared.len(),
        protected: 0,
    });
    if ready.is_empty() {
        return Ok(());
    }
    let mut names = crate::filenames::Names::default();
    let mut stems = Vec::with_capacity(prepared.len());
    for &(index, p) in &ready {
        let key = p.notice["row_key"]
            .as_str()
            .context("Prepared row has no key")?;
        let values = if c.filenames.individual.is_some() {
            crate::filenames::values(&p.notice)
        } else {
            BTreeMap::new()
        };
        let name = names.resolve(
            c.filenames.individual.as_ref().map(|p| p.template.as_str()),
            &values,
            key,
            key,
        );
        if let Some(message) = name.warning {
            record["entries"][index]["checks"]
                .as_array_mut()
                .unwrap()
                .push(crate::filenames::warning(
                    &message,
                    &format!("originals/{}.pdf", name.stem),
                ));
        }
        stems.push(name.stem);
    }
    let validator = validation::Validator::new(root)?;
    for &(_, p) in &ready {
        validator.payload(&p.notice)?;
    }
    let compiler_root = dir.join("resources/templates").canonicalize()?;
    let compiler_fonts = compiler::Compiler::fonts();
    let compile_workers = usize::from(compile_workers.clamp(1, 2));
    let compile_window = compile_workers * 2;
    // Amortize global cache sweeps while retaining roughly ten rows of history.
    let evict_every = if compile_workers == 2 { 5 } else { 1 };
    let make_request = |p: &Prepared| compiler::Request {
        inputs: BTreeMap::from([
            (
                "immuknow-template-path".into(),
                format!("/{}", p.notice["template"].as_str().unwrap()),
            ),
            (
                "notice-template".into(),
                p.notice["template"].as_str().unwrap().into(),
            ),
            (
                "notice-version".into(),
                p.notice["version_id"].as_str().unwrap().into(),
            ),
            (
                "notice-language".into(),
                p.notice["language"].as_str().unwrap().into(),
            ),
        ]),
        notice: p.notice.clone(),
        timestamp,
    };
    let encrypt = |(index, original, destination, password): (usize, PathBuf, PathBuf, String)| {
        let result = pdf::encrypt_with_hash(&original, &destination, &password);
        let value = match result {
            Ok(hash) => {
                json!({"status":"completed","path":format!("encrypted/{}",destination.file_name().unwrap().to_string_lossy()),"algorithm":"AES-256","revision":6,"sha256":hash})
            }
            Err(_) => json!({"status":"failed","error":"Encryption failed"}),
        };
        (index, value)
    };
    let pool_result = pool::with_pool(usize::from(workers.max(1)), encrypt, |jobs, results| {
        pool::with_state_pool(
            compile_workers,
            || compiler::Compiler::new(compiler_root.clone(), compiler_fonts.clone()),
            |compiler, (index, request): (usize, compiler::Request)| {
                (index, compiler.run(&request))
            },
            |compile_jobs, compile_results| {
                // Only this window may be queued, compiling, or awaiting ordered commit.
                // Refill after committing its first row so a slow row cannot grow the buffer.
                for &(index, p) in ready.iter().take(compile_window) {
                    compile_jobs
                        .send((index, make_request(p)))
                        .context("Compiler worker stopped")?;
                }
                let mut checkpoint = NoticeCheckpoint::new(Instant::now());
                let mut pending = BTreeMap::new();
                let mut count = 0usize;
                let mut protected = 0usize;
                let mut encryption_done = 0usize;
                let mut encryption_total = 0usize;
                let rendering = std::panic::catch_unwind(std::panic::AssertUnwindSafe(
                    || -> Result<()> {
                        for (position, &(index, p)) in ready.iter().enumerate() {
                            let original = format!("originals/{}.pdf", stems[position]);
                            let compiled = loop {
                                if let Some(result) = pending.remove(&index) {
                                    break result;
                                }
                                let (done, result) = compile_results
                                    .recv()
                                    .context("Compiler worker stopped")??;
                                if done == index {
                                    break result;
                                }
                                pending.insert(done, result);
                            };
                            let entry = &mut record["entries"][index];
                            match compiled {
                                Err(error) => {
                                    entry["original"] = json!({"status":"failed","error":error});
                                    add_check(
                                        entry,
                                        "rendering.failed",
                                        "Notice compilation failed",
                                    );
                                }
                                Ok(compiled) if compiled.pages > 0 && !compiled.pdf.is_empty() => {
                                    // Typst exports the document whose pages were counted;
                                    // parsing its bytes again would repeat the exporter contract.
                                    let pages = compiled.pages;
                                    crate::atomic(&dir.join(&original), &compiled.pdf)?;
                                    entry["original"] = json!({"status":"completed","path":original,"sha256":crate::hash(&compiled.pdf),"pages":pages});
                                    if !compiled.diagnostics.is_empty() {
                                        entry["compiler_diagnostics"] = json!(compiled.diagnostics);
                                    }
                                    let evidence = compiled
                                        .reports
                                        .map_err(anyhow::Error::msg)
                                        .and_then(|v| validator.report(&v, &p.notice, pages));
                                    match evidence {
                                        Ok(value) => {
                                            entry["checks"].as_array_mut().unwrap().extend(
                                                value["checks"].as_array().unwrap().clone(),
                                            );
                                            entry["deferred_checks"] = json!([]);
                                            entry["blocked_checks"] =
                                                value["blocked_checks"].clone();
                                            let mut saved = value;
                                            let object = saved
                                                .as_object_mut()
                                                .context("Invalid validated render evidence")?;
                                            object.remove("notice");
                                            object.remove("checks");
                                            object.remove("schema_version");
                                            object
                                                .insert("saved_evidence_version".into(), json!(1));
                                            object.remove("blocked_checks");
                                            if let Some(measurements) = object
                                                .get_mut("measurements")
                                                .and_then(Value::as_object_mut)
                                            {
                                                measurements.remove("header");
                                                for name in ["address", "client", "signature"] {
                                                    if let Some(items) = measurements
                                                        .get_mut(name)
                                                        .and_then(Value::as_array_mut)
                                                    {
                                                        for item in items {
                                                            if let Some(fields) =
                                                                item.as_object_mut()
                                                            {
                                                                fields.retain(|key, _| {
                                                                    !matches!(
                                                                        key.as_str(),
                                                                        "x_pt"
                                                                            | "y_pt"
                                                                            | "width_pt"
                                                                            | "height_pt"
                                                                            | "end_y_pt"
                                                                            | "window_x_pt"
                                                                            | "window_y_pt"
                                                                            | "window_width_pt"
                                                                            | "window_height_pt"
                                                                            | "window_padding_pt"
                                                                    )
                                                                });
                                                            }
                                                        }
                                                    }
                                                }
                                            }
                                            object.insert(
                                                "facts_sha256".into(),
                                                json!(crate::hash(&serde_json::to_vec(&p.notice)?)),
                                            );
                                            entry["saved_evidence"] = saved;
                                        }
                                        Err(error) => add_check(
                                            entry,
                                            "render.evidence_failed",
                                            &error.to_string(),
                                        ),
                                    }
                                    if c.encryption.enabled {
                                        match input::password(p, c) {
                                            Ok(password) => {
                                                encryption_total += 1;
                                                let job = (
                                                    index,
                                                    dir.join(&original),
                                                    dir.join(format!(
                                                        "encrypted/{}.pdf",
                                                        stems[position]
                                                    )),
                                                    password,
                                                );
                                                if workers == 0 {
                                                    let (_, value) = encrypt(job);
                                                    encryption_done += 1;
                                                    protected +=
                                                        usize::from(value["status"] == "completed");
                                                    entry["encryption"] = value;
                                                } else {
                                                    entry["encryption"] =
                                                        json!({"status":"pending"});
                                                    jobs.send(job)
                                                        .context("Encryption worker stopped")?;
                                                    count += 1;
                                                }
                                            }
                                            Err(_) => {
                                                entry["encryption"] = json!({"status":"failed","error":"Information needed for the password is missing"})
                                            }
                                        }
                                    }
                                }
                                Ok(_) => {
                                    entry["original"] = json!({"status":"failed","error":"PDF export returned no pages or no bytes"});
                                    add_check(
                                        entry,
                                        "output.readable",
                                        "PDF export returned no pages or no bytes",
                                    );
                                }
                            }
                            if (position + 1) % evict_every == 0 {
                                comemo::evict(10 / evict_every);
                            }
                            for (i, result) in results.try_iter() {
                                encryption_done += 1;
                                protected += usize::from(result["status"] == "completed");
                                record["entries"][i]["encryption"] = result;
                                count -= 1;
                            }
                            progress(Progress::Notices {
                                done: failed + position + 1,
                                total: prepared.len(),
                                protected,
                            });
                            if checkpoint.due(failed + position + 1, Instant::now()) {
                                report::checkpoint(dir, record)?;
                                checkpoint.saved(failed + position + 1, Instant::now());
                            }
                            if let Some(&(next_index, p)) = ready.get(position + compile_window) {
                                compile_jobs
                                    .send((next_index, make_request(p)))
                                    .context("Compiler worker stopped")?;
                            }
                        }
                        Ok(())
                    },
                ));
                drop(compile_jobs);
                // Finish submitted encryption jobs even when a later notice or checkpoint fails.
                drop(jobs);
                if count > 0 {
                    progress(Progress::Protecting {
                        done: encryption_done,
                        total: encryption_total,
                    });
                }
                for (index, value) in results {
                    encryption_done += 1;
                    progress(Progress::Protecting {
                        done: encryption_done,
                        total: encryption_total,
                    });
                    record["entries"][index]["encryption"] = value;
                    count -= 1;
                }
                ensure!(count == 0, "Encryption worker did not return every result");
                match rendering {
                    Ok(result) => result,
                    Err(_) => bail!("Unexpected rendering error"),
                }
            },
        )
    });
    if let Some(entries) = record["entries"].as_array_mut() {
        for entry in entries {
            if entry["encryption"]["status"] == "pending" {
                entry["encryption"] =
                    json!({"status":"failed","error":"Encryption worker did not return a result"});
            }
        }
    }
    pool_result
}

/// Process a batch without progress output. Inspect [`RunResult::succeeded`]
/// as well as the outer `Result` before treating the run as successful.
pub fn run(opts: &RunOptions) -> Result<RunResult> {
    run_with_progress(opts, &mut |_| {})
}

/// The coordinator reports completed work; callers choose how to display it.
pub fn run_with_progress(
    opts: &RunOptions,
    progress: &mut impl FnMut(Progress),
) -> Result<RunResult> {
    progress(Progress::Preparing);
    let started = Instant::now();
    let timestamp = timestamp(opts.timestamp)?;
    fs::create_dir_all(&opts.output)?;
    let output = opts.output.canonicalize()?;
    for path in [&opts.templates, &opts.config] {
        if let Ok(project) = path.canonicalize() {
            ensure!(
                !output.starts_with(project),
                "Output cannot be inside template or configuration directories"
            );
        }
    }
    let name = format!("run-{timestamp}-{:016x}", rand::random::<u64>());
    let dir = output.join(format!("{name}.incomplete"));
    fs::create_dir(&dir)?;
    let _lock = lock(&dir)?;
    let mut record = json!({
        "run_schema_version": 2,
        "run_id": name,
        "record_revision": 0,
        "exports": null,
        "engine": "typst 0.15.1",
        "timestamp": timestamp,
        "status": "running",
        "stage": "reading_input",
        "input": {},
        "resources": resources::identity(),
        "entries": [],
        "checks": [],
        "bundles": [],
        "delivery_attempts": [],
        "timings": {}
    });
    report::checkpoint(&dir, &mut record)?;
    let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| -> Result<()> {
        let bytes = fs::read(&opts.csv).context("Unable to read source CSV")?;
        crate::atomic(&dir.join("source.csv"), &bytes)?;
        record["input"] = json!({"path":"source.csv","sha256":crate::hash(&bytes),"requested_encoding":opts.encoding});
        drop(bytes);
        // Record every readable row before configuration or preparation can fail.
        record["entries"] = Value::Array(source_entries(
            &dir.join("source.csv"),
            opts.encoding.as_deref(),
        )?);
        report::checkpoint(&dir, &mut record)?;
        record["stage"] = json!("preparing");
        let resource_root = tempfile::tempdir()?;
        resources::materialize(resource_root.path())?;
        let mut c = input::config(&opts.config.join("parameters.yaml"))?;
        validate_project(&opts.templates, resource_root.path())?;
        let templates = dir.join("resources/templates");
        let config = dir.join("resources/config");
        let private_parameters = opts.config.join("parameters.yaml").canonicalize()?;
        let sanitized = serde_json::to_vec_pretty(&redacted(&c)?)?;
        copy_tree(&opts.templates, &templates, &private_parameters, &sanitized)?;
        copy_tree(&opts.config, &config, &private_parameters, &sanitized)?;
        if c.school_validation.enabled {
            let original = c
                .school_validation
                .reference_file
                .as_deref()
                .filter(|s| !s.trim().is_empty());
            let source = match original {
                None => opts.config.join("school_reference.json"),
                Some(s) if Path::new(s).is_absolute() => PathBuf::from(s),
                Some(s) => opts.config.join(s),
            };
            fs::copy(&source, config.join("school-reference-snapshot.json"))?;
            record["school_reference_source"] = json!(source.to_string_lossy());
            c.school_validation.reference_file = Some("school-reference-snapshot.json".into());
        }
        let settings = redacted(&c)?;
        crate::atomic(
            &config.join("parameters.yaml"),
            &serde_json::to_vec_pretty(&settings)?,
        )?;
        record["configured_settings"] = settings;
        record["project_resources"] =
            json!({"templates": tree(&templates)?, "config": tree(&config)?});
        let selection = match &opts.selection {
            Selection::Manifest(path) => {
                let bytes = fs::read(path)?;
                crate::atomic(&dir.join("assignments.json"), &bytes)?;
                record["input"]["assignments_sha256"] = json!(crate::hash(&bytes));
                Selection::Manifest(dir.join("assignments.json"))
            }
            Selection::Single(path) => Selection::Single(
                templates.join(path.file_name().context("Invalid selected template")?),
            ),
        };
        for sub in ["originals", "encrypted"] {
            fs::create_dir_all(dir.join(sub))?;
        }
        let prepared = prepare_data(
            opts,
            resource_root.path(),
            &dir.join("source.csv"),
            &selection,
            &config,
            &templates,
            &c,
        )?;
        ensure!(
            prepared.len() == record["entries"].as_array().unwrap().len(),
            "Preparation did not account for every source row"
        );
        assign_entries(&mut record, &prepared, c.encryption.enabled)?;
        policy::validate(&record, &c, resource_root.path())?;
        record["timings"]["preparation_seconds"] = json!(started.elapsed().as_secs_f64());
        report::checkpoint(&dir, &mut record)?;
        record["stage"] = json!("rendering");
        let render_start = Instant::now();
        process(
            &dir,
            &mut record,
            &prepared,
            &c,
            timestamp,
            opts.compile_workers,
            opts.encryption_workers,
            resource_root.path(),
            progress,
        )?;
        drop(prepared);
        record["timings"]["render_seconds"] = json!(render_start.elapsed().as_secs_f64());
        policy::apply(&mut record, &c, resource_root.path())?;
        record["stage"] = json!("bundling");
        let bundling_start = Instant::now();
        bundles::bundle_with_progress(
            &dir,
            &mut record,
            &c,
            usize::from(opts.bundle_workers),
            &mut |done, total| progress(Progress::Grouping { done, total }),
        )?;
        record["timings"]["delivery_seconds"] = json!(bundling_start.elapsed().as_secs_f64());
        progress(Progress::Reporting);
        record["status"] = json!(bundles::outcome(&record));
        record["stage"] = json!("complete");
        let rows: Vec<_> = record["entries"].as_array().unwrap().iter().map(|entry| json!({"row_key":entry["row_key"],"effective_checks":entry["effective_checks"],"hold":entry["hold"],"routing":entry["routing"],"bundle":entry["bundle"]})).collect();
        let attempt = json!({"bundles":record["bundles"],"configured_settings":record["configured_settings"],"holds":[],"status":record["status"],"rows":rows,"record_revision":record["record_revision"].as_u64().unwrap_or(0)+1});
        record["delivery_attempts"]
            .as_array_mut()
            .unwrap()
            .push(attempt);
        Ok(())
    }));
    record["timings"]["total_seconds"] = json!(started.elapsed().as_secs_f64());
    match outcome {
        Ok(Ok(())) => {
            record["active_bundle_attempt"] =
                json!(record["delivery_attempts"].as_array().unwrap().len());
            report::checkpoint(&dir, &mut record)?;
            report::publish(&dir, &mut record).map_err(|error| {
                SavedRunFailure::new(
                    &dir,
                    format!(
                        "Partial run saved at {}; CSV publication failed: {error:#}",
                        dir.display()
                    ),
                )
            })?;
            let completed = output.join(name);
            fs::rename(&dir, &completed).map_err(|error| {
                SavedRunFailure::new(
                    &dir,
                    format!(
                        "Finalization failed; partial run saved at {}: {error}",
                        dir.display()
                    ),
                )
            })?;
            Ok(RunResult {
                record: completed.join("run.json"),
                succeeded: record["status"] != "completed_with_failures",
                summary: RunSummary::from_record(&record),
            })
        }
        Ok(Err(error)) => {
            record["status"] = json!("failed");
            record["error"] = json!(format!("{error:#}"));
            if record["failed_planned_members"].is_array() {
                let attempt = json!({"status":"failed","error":format!("{error:#}"),"planned_members":record["failed_planned_members"]});
                record["delivery_attempts"]
                    .as_array_mut()
                    .unwrap()
                    .push(attempt);
                record
                    .as_object_mut()
                    .unwrap()
                    .remove("failed_planned_members");
            }
            let saved = report::checkpoint(&dir, &mut record)
                .and_then(|_| report::publish(&dir, &mut record));
            if let Err(report_error) = saved {
                return Err(SavedRunFailure::new(
                    &dir,
                    format!(
                        "Partial run at {}; processing failed: {error:#}; reporting also failed: {report_error:#}",
                        dir.display()
                    ),
                ));
            }
            Err(SavedRunFailure::new(
                &dir,
                format!(
                    "Partial run saved at {}; processing failed: {error:#}",
                    dir.display()
                ),
            ))
        }
        Err(_) => {
            record["status"] = json!("failed");
            record["error"] = json!("Unexpected pipeline error");
            let saved = report::checkpoint(&dir, &mut record)
                .and_then(|_| report::publish(&dir, &mut record));
            if let Err(error) = saved {
                return Err(SavedRunFailure::new(
                    &dir,
                    format!(
                        "Unexpected pipeline error; partial run at {}; reporting also failed: {error:#}",
                        dir.display()
                    ),
                ));
            }
            Err(SavedRunFailure::new(
                &dir,
                format!(
                    "Unexpected pipeline error; partial run saved at {}",
                    dir.display()
                ),
            ))
        }
    }
}

/// Apply policy and hold decisions to a completed run and assemble fresh bundles.
///
/// Acquires the run lock before reading. Uses saved originals without recompiling
/// or repeating encryption. Assembly errors retain previous bundles and decisions.
pub fn rebundle_with_filenames(
    run: &Path,
    override_policy: Option<&Path>,
    filename_settings: Option<&Path>,
    withhold: &[String],
    reason: Option<&str>,
    release: &[String],
    workers: usize,
) -> Result<RunResult> {
    let dir = run.canonicalize()?;
    // Read the record only after taking the lock so two attempts cannot overwrite each other.
    let _lock = lock(&dir)?;
    let mut record: Value = crate::read_json(&dir.join("run.json"))?;
    ensure!(
        record["run_schema_version"] == 2,
        "Unsupported saved-run version; use the matching old executable"
    );
    crate::warning_review::validate(&record)?;
    crate::checks::validate_record(&record, true)?;
    ensure!(
        matches!(
            record["status"].as_str(),
            Some("completed" | "completed_with_warnings" | "completed_with_failures")
        ),
        "Run is not complete"
    );
    let mut c: Config = serde_json::from_value(record["configured_settings"].clone())
        .context("Invalid saved configuration")?;
    if let Some(path) = override_policy {
        let value: Value = crate::read_json(path)?;
        c.validation = serde_json::from_value(value).context("Policy must be an object")?;
    }
    if let Some(path) = filename_settings {
        let settings: crate::filenames::Settings = crate::read_json(path)?;
        settings.validate()?;
        ensure!(
            settings.individual.is_none(),
            "Individual filenames cannot change when rebundling"
        );
        c.filenames.bundle = settings.bundle;
        c.filenames.review_bundle = settings.review_bundle;
    }
    let resource_root = tempfile::tempdir()?;
    resources::materialize(resource_root.path())?;
    let mut next = record.clone();
    let mut seen = std::collections::BTreeSet::new();
    for key in withhold.iter().chain(release) {
        ensure!(seen.insert(key), "Repeated or conflicting hold decision");
        let matching: Vec<_> = next["entries"]
            .as_array()
            .context("Missing entries")?
            .iter()
            .enumerate()
            .filter(|(_, e)| e["row_key"] == *key)
            .map(|(i, _)| i)
            .collect();
        ensure!(
            matching.len() == 1,
            "Hold decision must identify exactly one source row"
        );
        let entry = &mut next["entries"][matching[0]];
        if withhold.contains(key) {
            let text = reason
                .filter(|v| !v.trim().is_empty())
                .context("Withholding requires a reason")?;
            entry["hold"] = json!({"reason":text});
        } else {
            entry["hold"] = Value::Null;
        }
    }
    policy::validate(&next, &c, resource_root.path())?;
    // Move the outgoing active attempt's delivery observations into its immutable
    // snapshot before replacing them. Shared observations remain on the row.
    if let Some(active) = next["active_bundle_attempt"]
        .as_u64()
        .and_then(|n| usize::try_from(n).ok())
        .and_then(|n| n.checked_sub(1))
    {
        let archived: BTreeMap<String, Vec<Value>> = next["entries"]
            .as_array()
            .context("Missing saved entries")?
            .iter()
            .map(|entry| {
                (
                    entry["row_key"].as_str().unwrap_or("").to_owned(),
                    entry["checks"]
                        .as_array()
                        .into_iter()
                        .flatten()
                        .filter(|check| check["stage"] == "delivery")
                        .cloned()
                        .collect(),
                )
            })
            .collect();
        let attempt = next["delivery_attempts"]
            .as_array_mut()
            .and_then(|attempts| attempts.get_mut(active))
            .context("Invalid active bundle attempt")?;
        for row in attempt["rows"]
            .as_array_mut()
            .context("Missing attempt rows")?
        {
            let key = row["row_key"].as_str().context("Missing attempt row key")?;
            row["delivery_checks"] = json!(archived.get(key).context("Attempt row not found")?);
        }
    }
    policy::apply(&mut next, &c, resource_root.path())?;
    if let Err(error) = bundles::bundle(&dir, &mut next, &c, workers) {
        let attempt = json!({"status":"failed","error":format!("{error:#}"),"validation":c.validation,"filenames":c.filenames,"withhold":withhold,"release":release,"reason":reason,"planned_members":next["failed_planned_members"]});
        record["delivery_attempts"]
            .as_array_mut()
            .context("Missing bundle attempts")?
            .push(attempt);
        let saved =
            report::checkpoint(&dir, &mut record).and_then(|_| report::publish(&dir, &mut record));
        if let Err(report_error) = saved {
            return Err(SavedRunFailure::new(
                &dir,
                format!(
                    "Bundle attempt failed: {error:#}; previous bundles were kept; reporting also failed: {report_error:#}"
                ),
            ));
        }
        return Err(SavedRunFailure::new(
            &dir,
            format!(
                "Could not create bundles: {error:#}; previous active attempt {} and its decisions were kept",
                record["active_bundle_attempt"]
                    .as_u64()
                    .map(|n| n.to_string())
                    .unwrap_or_else(|| "none".into())
            ),
        ));
    }
    next["configured_settings"] = redacted(&c)?;
    next["status"] = json!(bundles::outcome(&next));
    let rows: Vec<_> = next["entries"].as_array().unwrap().iter().map(|entry| json!({"row_key":entry["row_key"],"effective_checks":entry["effective_checks"],"hold":entry["hold"],"routing":entry["routing"],"bundle":entry["bundle"]})).collect();
    let attempt = json!({"bundles":next["bundles"],"validation":c.validation,"filenames":c.filenames,"withhold":withhold,"release":release,"reason":reason,"status":next["status"],"rows":rows,"record_revision":next["record_revision"].as_u64().unwrap_or(0)+1});
    if !next["delivery_attempts"].is_array() {
        next["delivery_attempts"] = json!([]);
    }
    next["delivery_attempts"]
        .as_array_mut()
        .unwrap()
        .push(attempt);
    record = next;
    record["active_bundle_attempt"] = json!(record["delivery_attempts"].as_array().unwrap().len());
    report::checkpoint(&dir, &mut record)?;
    report::publish(&dir, &mut record)?;
    Ok(RunResult {
        record: dir.join("run.json"),
        succeeded: record["status"] != "completed_with_failures",
        summary: RunSummary::from_record(&record),
    })
}

#[cfg(test)]
mod checkpoint_tests {
    use super::*;

    #[test]
    fn early_then_doubling_checkpoints_and_time_limit() {
        let start = Instant::now();
        let mut checkpoint = NoticeCheckpoint::new(start);
        assert!(!checkpoint.due(99, start + Duration::from_secs(1)));
        assert!(checkpoint.due(100, start + Duration::from_secs(1)));
        checkpoint.saved(100, start + Duration::from_secs(1));
        assert!(!checkpoint.due(199, start + Duration::from_secs(2)));
        assert!(checkpoint.due(200, start + Duration::from_secs(2)));
        checkpoint.saved(200, start + Duration::from_secs(2));
        assert!(!checkpoint.due(399, start + Duration::from_secs(3)));
        assert!(checkpoint.due(400, start + Duration::from_secs(3)));
        // A slow first 100 rows also need a useful partial report.
        let checkpoint = NoticeCheckpoint::new(start);
        assert!(!checkpoint.due(20, start + Duration::from_secs(29)));
        assert!(checkpoint.due(20, start + Duration::from_secs(30)));
        let mut checkpoint = checkpoint;
        checkpoint.saved(20, start + Duration::from_secs(31));
        assert!(!checkpoint.due(21, start + Duration::from_secs(60)));
        assert!(checkpoint.due(21, start + Duration::from_secs(61)));
    }
}
