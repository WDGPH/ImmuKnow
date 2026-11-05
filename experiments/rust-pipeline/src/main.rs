//! Exploratory, single-process Rust CSV-to-delivery pipeline. Never a production fallback.
mod compiler;
mod input;
mod pdf;
mod pool;
mod report;
use anyhow::{Context, Result, ensure};
use clap::{Parser, Subcommand};
use serde::{
    Deserialize,
    de::{self, MapAccess, SeqAccess, Visitor},
};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fmt, fs,
    path::{Path, PathBuf},
    time::Instant,
};

#[derive(Parser)]
struct Args {
    #[command(subcommand)]
    command: Command,
}
#[derive(clap::Args)]
struct Workers {
    /// Background encryption threads; 0 encrypts inline on the compiler thread.
    #[arg(long, default_value_t = 0, value_parser = clap::value_parser!(u8).range(0..=16))]
    encryption_workers: u8,
    /// Independent bundles processed at once, after rendering.
    #[arg(long, default_value_t = 1, value_parser = clap::value_parser!(u8).range(1..=16))]
    bundle_workers: u8,
}
#[derive(Subcommand)]
enum Command {
    Run {
        #[arg(long)]
        csv: PathBuf,
        #[arg(long)]
        assignments: PathBuf,
        #[arg(long)]
        config: PathBuf,
        #[arg(long)]
        templates: PathBuf,
        #[arg(long)]
        core: PathBuf,
        #[arg(long)]
        output: PathBuf,
        #[arg(long)]
        timestamp: Option<i64>,
        #[command(flatten)]
        workers: Workers,
    },
    Encrypt {
        #[arg(long)]
        input: PathBuf,
        #[arg(long)]
        output: PathBuf,
        #[arg(long)]
        password_env: String,
    },
    Serve {
        #[arg(long)]
        root: PathBuf,
    },
    Merge {
        #[arg(long)]
        output: PathBuf,
        #[arg(required = true)]
        inputs: Vec<PathBuf>,
    },
}
// serde_json's ordinary Value map accepts repeated fields. Reject them recursively.
struct Unique(Value);
impl<'de> Deserialize<'de> for Unique {
    fn deserialize<D: serde::Deserializer<'de>>(d: D) -> std::result::Result<Self, D::Error> {
        struct V;
        impl<'de> Visitor<'de> for V {
            type Value = Unique;
            fn expecting(&self, f: &mut fmt::Formatter) -> fmt::Result {
                f.write_str("JSON with unique fields")
            }
            fn visit_map<M: MapAccess<'de>>(
                self,
                mut m: M,
            ) -> std::result::Result<Unique, M::Error> {
                let mut out = serde_json::Map::new();
                while let Some((k, v)) = m.next_entry::<String, Unique>()? {
                    if out.contains_key(&k) {
                        return Err(de::Error::custom(format!("Repeated JSON field: {k}")));
                    }
                    out.insert(k, v.0);
                }
                Ok(Unique(Value::Object(out)))
            }
            fn visit_seq<S: SeqAccess<'de>>(
                self,
                mut s: S,
            ) -> std::result::Result<Unique, S::Error> {
                let mut out = vec![];
                while let Some(v) = s.next_element::<Unique>()? {
                    out.push(v.0);
                }
                Ok(Unique(json!(out)))
            }
            fn visit_str<E: de::Error>(self, s: &str) -> std::result::Result<Unique, E> {
                Ok(Unique(json!(s)))
            }
            fn visit_bool<E: de::Error>(self, v: bool) -> std::result::Result<Unique, E> {
                Ok(Unique(json!(v)))
            }
            fn visit_i64<E: de::Error>(self, v: i64) -> std::result::Result<Unique, E> {
                Ok(Unique(json!(v)))
            }
            fn visit_u64<E: de::Error>(self, v: u64) -> std::result::Result<Unique, E> {
                Ok(Unique(json!(v)))
            }
            fn visit_f64<E: de::Error>(self, v: f64) -> std::result::Result<Unique, E> {
                Ok(Unique(json!(v)))
            }
            fn visit_unit<E: de::Error>(self) -> std::result::Result<Unique, E> {
                Ok(Unique(Value::Null))
            }
        }
        d.deserialize_any(V)
    }
}
pub fn read_json<T: serde::de::DeserializeOwned>(p: &Path) -> Result<T> {
    let v: Unique = serde_json::from_slice(&fs::read(p)?)?;
    Ok(serde_json::from_value(v.0)?)
}
pub fn atomic(p: &Path, bytes: &[u8]) -> Result<()> {
    let temp = p.with_extension("partial");
    fs::write(&temp, bytes)?;
    fs::rename(temp, p)?;
    Ok(())
}
fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn copy_tree(
    source: &Path,
    target: &Path,
    hashes: &mut BTreeMap<String, String>,
    root: &Path,
    redact: bool,
) -> Result<()> {
    ensure!(
        !source.is_symlink(),
        "Project resources cannot be symbolic links"
    );
    fs::create_dir_all(target)?;
    let mut entries = fs::read_dir(source)?.collect::<std::io::Result<Vec<_>>>()?;
    entries.sort_by_key(|e| e.file_name());
    for entry in entries {
        let p = entry.path();
        ensure!(
            !p.is_symlink(),
            "Project resources cannot be symbolic links"
        );
        let t = target.join(entry.file_name());
        if p.is_dir() {
            copy_tree(&p, &t, hashes, root, redact)?;
        } else {
            let bytes = fs::read(&p)?;
            let bytes =
                if redact && p.file_name().and_then(|n| n.to_str()) == Some("parameters.yaml") {
                    let mut settings: Value = serde_saphyr::from_str(std::str::from_utf8(&bytes)?)?;
                    if let Some(e) = settings
                        .get_mut("encryption")
                        .and_then(Value::as_object_mut)
                    {
                        e.remove("password");
                    }
                    serde_json::to_vec_pretty(&settings)?
                } else {
                    bytes
                };
            fs::write(&t, &bytes)?;
            hashes.insert(t.strip_prefix(root)?.to_string_lossy().into(), hash(&bytes));
        }
    }
    Ok(())
}
fn tree(path: &Path) -> Result<BTreeMap<String, String>> {
    fn walk(p: &Path, root: &Path, m: &mut BTreeMap<String, String>) -> Result<()> {
        ensure!(!p.is_symlink(), "Shared library cannot contain links");
        for e in fs::read_dir(p)? {
            let p = e?.path();
            ensure!(!p.is_symlink(), "Shared library cannot contain links");
            if p.is_dir() {
                walk(&p, root, m)?
            } else {
                m.insert(
                    p.strip_prefix(root)?.to_string_lossy().into(),
                    hash(&fs::read(p)?),
                );
            }
        }
        Ok(())
    }
    let mut m = BTreeMap::new();
    walk(path, path, &mut m)?;
    Ok(m)
}
fn pipeline(
    csv: &Path,
    assignments: &Path,
    config: &Path,
    templates: &Path,
    core: &Path,
    output: &Path,
    timestamp: Option<i64>,
    workers: &Workers,
) -> Result<(PathBuf, bool)> {
    let started = Instant::now();
    let timestamp = timestamp.unwrap_or_else(|| {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs() as i64
    });
    fs::create_dir_all(output)?;
    let resolved_output = output.canonicalize()?;
    ensure!(
        !resolved_output.starts_with(templates.canonicalize()?)
            && !resolved_output.starts_with(config.canonicalize()?),
        "Output directory cannot be inside templates or configuration"
    );
    let name = format!("rust-{timestamp}-{:016x}", rand::random::<u64>());
    let dir = output.join(format!("{name}.incomplete"));
    fs::create_dir(&dir)?;
    let mut record = json!({"experiment_schema":1,"engine":"typst 0.15.1","pdf_library":"lopdf 0.47.0","timestamp":timestamp,"status":"running","limitations":["Experimental record; Python rebundle/review commands unsupported","Simplified experimental validation, UTF-8 comma CSV, assignment manifest, size-only grouping, DOB password","Bundle tagging and catalog-level navigation are not preserved"],"entries":[],"bundles":[],"timings":{}});
    record["runtime"] = json!({"available_parallelism":std::thread::available_parallelism().map(|n|n.get()).unwrap_or(1),"rayon_num_threads_override":std::env::var("RAYON_NUM_THREADS").ok(),"compilation_workers":1,"encryption_workers":workers.encryption_workers,"bundle_workers":workers.bundle_workers});
    report::write(&dir, &record)?;
    let run = (|| -> Result<()> {
        let setup = Instant::now();
        let c = input::config(&config.join("parameters.yaml"))?;
        ensure!(
            tree(&templates.join("lib/immuknow"))? == tree(&core.join("immuknow/typst"))?,
            "Project shared library differs from Core"
        );
        let mut hashes = BTreeMap::new();
        copy_tree(
            templates,
            &dir.join("resources/templates"),
            &mut hashes,
            &dir,
            false,
        )?;
        copy_tree(
            config,
            &dir.join("resources/config"),
            &mut hashes,
            &dir,
            true,
        )?;
        fs::create_dir_all(dir.join("originals"))?;
        fs::create_dir_all(dir.join("encrypted"))?;
        fs::create_dir_all(dir.join("facts"))?;
        fs::copy(csv, dir.join("source.csv"))?;
        fs::copy(assignments, dir.join("assignments.json"))?;
        record["input"] = json!({"sha256":hash(&fs::read(csv)?),"assignments_sha256":hash(&fs::read(assignments)?)});
        record["resources"] = json!(hashes);
        let prepared = input::prepare(csv, assignments, config, templates, core, &c)?;
        let validator = report::Validator::new(core)?;
        for p in &prepared {
            validator.payload(&p.notice)?;
        }
        record["timings"]["preparation_seconds"] = json!(setup.elapsed().as_secs_f64());
        let mut compiler = compiler::Compiler::new(
            dir.join("resources/templates").canonicalize()?,
            compiler::Compiler::fonts(),
        );
        let mut render_seconds = 0.0;
        let mut inspect_seconds = 0.0;
        let mut encryption_seconds = 0.0;
        let mut checkpoint_seconds = 0.0;
        let processing = Instant::now();
        let encrypt = |(index, original, encrypted, password): (
            usize,
            PathBuf,
            PathBuf,
            String,
        )| {
            let started = Instant::now();
            let result = pdf::encrypt(&original, &encrypted, &password)
                .and_then(|()| Ok(hash(&fs::read(&encrypted)?)));
            let value = match result {
                Ok(sha256) => {
                    json!({"status":"completed","path":format!("encrypted/{}.pdf", original.file_stem().unwrap().to_string_lossy()),"algorithm":"AES-256","revision":6,"sha256":sha256})
                }
                Err(error) => json!({"status":"failed","error":error.to_string()}),
            };
            (index, value, started.elapsed().as_secs_f64())
        };
        pool::with_pool(
            usize::from(workers.encryption_workers.max(1)),
            encrypt,
            |jobs, results| {
                let mut submitted = 0;
                let mut received = 0;
                for p in prepared {
                    let key = p.notice["row_key"].as_str().unwrap();
                    let original = format!("originals/{key}.pdf");
                    atomic(
                        &dir.join(format!("facts/{key}.json")),
                        &serde_json::to_vec(&p.notice)?,
                    )?;
                    let mut entry = json!({"row_key":key,"client_id":p.notice["client_id"],"source":p.source,"assignment":p.assignment,"notice":p.notice,"checks":p.checks,"original":{"status":"not_run"},"encryption":{"status":if c.encryption.enabled{"not_run"}else{"not_requested"}}});
                    let t = Instant::now();
                    let request = compiler::Request {
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
                    let rendered = compiler.run(&request);
                    render_seconds += t.elapsed().as_secs_f64();
                    match rendered {
                        Err(error) => {
                            entry["original"] = json!({"status":"failed","error":error});
                        }
                        Ok(compiled) => {
                            atomic(&dir.join(&original), &compiled.pdf)?;
                            let t = Instant::now();
                            let inspected = pdf::inspect(&compiled.pdf)?;
                            ensure!(
                                inspected == compiled.pages,
                                "Compiler/PDF page count mismatch"
                            );
                            entry["original"] = json!({"status":"completed","path":original,"sha256":hash(&compiled.pdf),"pages":compiled.pages});
                            if !compiled.diagnostics.is_empty() {
                                entry["compiler_diagnostics"] = json!(compiled.diagnostics);
                            }
                            let evidence = compiled
                                .reports
                                .map_err(anyhow::Error::msg)
                                .and_then(|r| validator.report(&r, &p.notice, compiled.pages));
                            match evidence {Ok(r)=>{entry["checks"].as_array_mut().unwrap().extend(r["checks"].as_array().unwrap().clone());entry["render_report"]=r;},Err(e)=>entry["checks"].as_array_mut().unwrap().push(json!({"code":"render.evidence_failed","stage":"render","status":"fail","message":e.to_string()}))};
                            inspect_seconds += t.elapsed().as_secs_f64();
                            if c.encryption.enabled {
                                let encrypted = format!("encrypted/{key}.pdf");
                                let password = p.notice["client_data"]["date_of_birth_iso"]
                                    .as_str()
                                    .unwrap()
                                    .replace('-', "");
                                let job = (
                                    record["entries"].as_array().unwrap().len(),
                                    dir.join(&original),
                                    dir.join(&encrypted),
                                    password,
                                );
                                if workers.encryption_workers == 0 {
                                    let (_, value, seconds) = encrypt(job);
                                    entry["encryption"] = value;
                                    encryption_seconds += seconds;
                                } else {
                                    jobs.send(job).context("Encryption workers stopped")?;
                                    submitted += 1;
                                    entry["encryption"] = json!({"status":"pending"});
                                }
                            }
                        }
                    }
                    comemo::evict(10);
                    record["entries"].as_array_mut().unwrap().push(entry);
                    for (index, value, seconds) in results.try_iter() {
                        record["entries"][index]["encryption"] = value;
                        encryption_seconds += seconds;
                        received += 1;
                    }
                    if record["entries"].as_array().unwrap().len() % 100 == 0 {
                        let checkpoint = Instant::now();
                        report::write(&dir, &record)?;
                        checkpoint_seconds += checkpoint.elapsed().as_secs_f64();
                        eprintln!(
                            "{} notices completed",
                            record["entries"].as_array().unwrap().len()
                        );
                    }
                }
                drop(jobs);
                let drain = Instant::now();
                for (index, value, seconds) in results {
                    record["entries"][index]["encryption"] = value;
                    encryption_seconds += seconds;
                    received += 1;
                }
                ensure!(
                    received == submitted,
                    "Encryption worker did not return a result"
                );
                record["timings"]["encryption_drain_seconds"] =
                    json!(drain.elapsed().as_secs_f64());
                Ok(())
            },
        )?;
        record["timings"]["render_encrypt_wall_seconds"] =
            json!(processing.elapsed().as_secs_f64());
        record["timings"]["checkpoint_seconds"] = json!(checkpoint_seconds);
        record["timings"]["render_seconds"] = json!(render_seconds);
        record["timings"]["inspect_validate_seconds"] = json!(inspect_seconds);
        // Summed task wall times overlap when workers are enabled; not a stage wall timer.
        record["timings"]["encryption_task_seconds"] = json!(encryption_seconds);
        report::write(&dir, &record)?;
        let delivery = Instant::now();
        let bundle_dir = dir.join("bundles.incomplete");
        fs::create_dir(&bundle_dir)?;
        let usable: Vec<_> = record["entries"]
            .as_array()
            .unwrap()
            .iter()
            .enumerate()
            .filter(|(_, e)| e["original"]["status"] == "completed")
            .map(|(i, _)| i)
            .collect();
        let chunks: Vec<_> = usable.chunks(c.bundling.bundle_size).collect();
        let merge = |(index, paths): (usize, Vec<PathBuf>)| -> Result<(usize, usize, String)> {
            let destination = bundle_dir.join(format!("bundle-{:04}.pdf", index + 1));
            let pages = pdf::merge(&paths, &destination)?;
            Ok((index, pages, hash(&fs::read(destination)?)))
        };
        let mut merged = BTreeMap::new();
        pool::with_pool(
            usize::from(workers.bundle_workers).min(chunks.len()).max(1),
            merge,
            |jobs, results| {
                for (index, chunk) in chunks.iter().enumerate() {
                    let paths = chunk
                        .iter()
                        .map(|&i| {
                            dir.join(record["entries"][i]["original"]["path"].as_str().unwrap())
                        })
                        .collect();
                    jobs.send((index, paths))
                        .context("Bundle workers stopped")?;
                }
                drop(jobs);
                for result in results {
                    let (index, pages, sha256) = result?;
                    merged.insert(index, (pages, sha256));
                }
                ensure!(
                    merged.len() == chunks.len(),
                    "Bundle worker did not return a result"
                );
                Ok(())
            },
        )?;
        for (index, chunk) in chunks.into_iter().enumerate() {
            let filename = format!("bundle-{:04}.pdf", index + 1);
            let (pages, checksum) = merged.remove(&index).unwrap();
            let mut csv =
                csv::Writer::from_path(bundle_dir.join(format!("bundle-{:04}.csv", index + 1)))?;
            csv.write_record([
                "row_key",
                "client_id",
                "notice_start_page",
                "notice_end_page",
                "route",
                "check_code",
                "status",
                "message",
            ])?;
            let mut cursor = 1;
            let mut members = vec![];
            for &i in chunk {
                let e = &mut record["entries"][i];
                let count = e["original"]["pages"].as_u64().unwrap() as usize;
                let route = if e.get("compiler_diagnostics").is_some()
                    || e["checks"]
                        .as_array()
                        .unwrap()
                        .iter()
                        .any(|c| matches!(c["status"].as_str(), Some("warn" | "fail")))
                {
                    "review"
                } else {
                    "deliverable"
                };
                e["routing"] = json!(route);
                e["bundle"] = json!({"path":format!("bundles/{filename}"),"notice_start_page":cursor,"notice_end_page":cursor+count-1});
                members.push(e["row_key"].clone());
                for check in e["checks"].as_array().unwrap() {
                    csv.write_record([
                        e["row_key"].as_str().unwrap(),
                        e["client_id"].as_str().unwrap(),
                        &cursor.to_string(),
                        &(cursor + count - 1).to_string(),
                        route,
                        check["code"].as_str().unwrap(),
                        check["status"].as_str().unwrap(),
                        check["message"].as_str().unwrap(),
                    ])?;
                }
                cursor += count;
            }
            csv.flush()?;
            ensure!(pages == cursor - 1, "Bundle membership count mismatch");
            record["bundles"].as_array_mut().unwrap().push(json!({"path":format!("bundles/{filename}"),"pages":pages,"members":members,"sha256":checksum}));
        }
        fs::rename(bundle_dir, dir.join("bundles"))?;
        record["timings"]["delivery_seconds"] = json!(delivery.elapsed().as_secs_f64());
        record["status"] =
            json!(if record["entries"]
                .as_array()
                .unwrap()
                .iter()
                .any(|e| e["original"]["status"] != "completed"
                    || e["encryption"]["status"] == "failed"
                    || e["checks"]
                        .as_array()
                        .unwrap()
                        .iter()
                        .any(|c| c["status"] == "fail"))
            {
                "completed_with_failures"
            } else {
                "completed"
            });
        Ok(())
    })();
    record["timings"]["total_seconds"] = json!(started.elapsed().as_secs_f64());
    if let Err(e) = run {
        record["status"] = json!("failed");
        record["error"] = json!(format!("{e:#}"));
        report::write(&dir, &record)?;
        return Err(e);
    }
    report::write(&dir, &record)?;
    let complete = output.join(name);
    fs::rename(&dir, &complete)?;
    Ok((complete.join("run.json"), record["status"] == "completed"))
}
fn serve(root: PathBuf) -> Result<()> {
    use std::io::{BufRead, Write};
    #[derive(Deserialize)]
    #[serde(deny_unknown_fields)]
    struct Request {
        id: String,
        inputs: BTreeMap<String, String>,
        notice: Value,
        output: PathBuf,
        timestamp: i64,
        direct_report: bool,
    }
    let mut compiler = compiler::Compiler::new(root.canonicalize()?, compiler::Compiler::fonts());
    let mut stdout = std::io::stdout().lock();
    for line in std::io::stdin().lock().lines() {
        let request: Request = serde_json::from_str(&line?)?;
        ensure!(request.direct_report, "Only direct reports are supported");
        let compiled = compiler.run(&compiler::Request {
            inputs: request.inputs,
            notice: request.notice,
            timestamp: request.timestamp,
        });
        let response = match compiled {
            Ok(compiled) => {
                atomic(&request.output, &compiled.pdf)?;
                match compiled.reports {
                    Ok(reports) => {
                        json!({"id":request.id,"ok":true,"reports":reports,"diagnostics":compiled.diagnostics,"error":null})
                    }
                    Err(error) => {
                        json!({"id":request.id,"ok":false,"reports":null,"diagnostics":compiled.diagnostics,"error":error})
                    }
                }
            }
            Err(error) => {
                json!({"id":request.id,"ok":false,"reports":null,"diagnostics":"","error":error})
            }
        };
        serde_json::to_writer(&mut stdout, &response)?;
        writeln!(&mut stdout)?;
        stdout.flush()?;
        comemo::evict(10);
    }
    Ok(())
}
fn main() -> Result<()> {
    match Args::parse().command {
        Command::Run {
            csv,
            assignments,
            config,
            templates,
            core,
            output,
            timestamp,
            workers,
        } => {
            let (path, succeeded) = pipeline(
                &csv,
                &assignments,
                &config,
                &templates,
                &core,
                &output,
                timestamp,
                &workers,
            )?;
            println!("{}", path.display());
            if !succeeded {
                std::process::exit(1);
            }
            Ok(())
        }
        Command::Encrypt {
            input,
            output,
            password_env,
        } => {
            ensure!(!output.exists(), "Encryption output already exists");
            let password = std::env::var(password_env)
                .context("Password environment variable is unavailable")?;
            pdf::encrypt(&input, &output, &password)
        }
        Command::Serve { root } => serve(root),
        Command::Merge { output, inputs } => {
            ensure!(!output.exists(), "Merge output already exists");
            println!("{}", pdf::merge(&inputs, &output)?);
            Ok(())
        }
    }
}
