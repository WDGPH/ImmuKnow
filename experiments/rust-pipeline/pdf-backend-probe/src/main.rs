//! Optional PDF-only comparison: never linked into the notice executable.
#[path = "../../src/pdf.rs"]
mod pdf;
#[path = "../../src/pool.rs"]
mod pool;
use anyhow::{Context, Result, ensure};
use clap::{Parser, Subcommand, ValueEnum};
use pdf_oxide::editor::{
    DocumentEditor, EditableDocument, EncryptionAlgorithm, EncryptionConfig, SaveOptions,
};
use serde_json::{Value, json};
use std::{
    fs,
    path::{Path, PathBuf},
    time::Instant,
};

#[derive(Clone, Copy, ValueEnum)]
enum Backend {
    Lopdf,
    Oxide,
}
#[derive(Parser)]
struct Args {
    #[arg(long, value_enum)]
    backend: Backend,
    #[command(subcommand)]
    command: Command,
}
#[derive(Subcommand)]
enum Command {
    Encrypt {
        #[arg(long)]
        input: PathBuf,
        #[arg(long)]
        output: PathBuf,
        #[arg(long)]
        password_env: String,
    },
    Merge {
        #[arg(long)]
        output: PathBuf,
        #[arg(required = true)]
        inputs: Vec<PathBuf>,
    },
    Bench {
        #[arg(long)]
        record: PathBuf,
        #[arg(long)]
        output: PathBuf,
        #[arg(long)]
        operation: String,
        #[arg(long, default_value_t=1, value_parser=clap::value_parser!(u8).range(1..=16))]
        workers: u8,
    },
}
fn encrypt(backend: Backend, input: &Path, output: &Path, password: &str) -> Result<()> {
    if matches!(backend, Backend::Lopdf) {
        return pdf::encrypt(input, output, password);
    }
    ensure!(
        !password.trim().is_empty(),
        "Password facts are unavailable"
    );
    let mut editor = DocumentEditor::open(input)?;
    let pages = editor.page_count()?;
    let config =
        EncryptionConfig::new(password, password).with_algorithm(EncryptionAlgorithm::Aes256);
    let partial = output.with_extension("partial.pdf");
    editor.save_with_options(&partial, SaveOptions::with_encryption(config))?;
    pdf::verify_encrypted(&partial, password, pages)?;
    fs::rename(partial, output)?;
    Ok(())
}
fn merge(backend: Backend, paths: &[PathBuf], output: &Path) -> Result<usize> {
    if matches!(backend, Backend::Lopdf) {
        return pdf::merge(paths, output);
    }
    let mut editor = DocumentEditor::open(paths.first().context("No source PDFs")?)?;
    for path in &paths[1..] {
        editor.merge_from(path)?;
    }
    let pages = editor.page_count()?;
    editor.save_with_options(output, SaveOptions::full_rewrite())?;
    ensure!(
        pdf::inspect(&fs::read(output)?)? == pages,
        "Bundle page count mismatch"
    );
    Ok(pages)
}
fn main() -> Result<()> {
    let args = Args::parse();
    match args.command {
        Command::Encrypt {
            input,
            output,
            password_env,
        } => {
            ensure!(!output.exists(), "Output already exists");
            encrypt(args.backend, &input, &output, &std::env::var(password_env)?)
        }
        Command::Merge { inputs, output } => {
            ensure!(!output.exists(), "Output already exists");
            println!("{}", merge(args.backend, &inputs, &output)?);
            Ok(())
        }
        Command::Bench {
            record,
            output,
            operation,
            workers,
        } => {
            let started = Instant::now();
            fs::create_dir(&output)?;
            let root = record.parent().context("Record parent")?;
            let record: Value = serde_json::from_slice(&fs::read(&record)?)?;
            let mut jobs_to_run = Vec::new();
            match operation.as_str() {
                "encrypt" => {
                    for e in record["entries"].as_array().context("Entries")? {
                        jobs_to_run.push((
                            vec![
                                root.join(e["original"]["path"].as_str().context("Original path")?),
                            ],
                            output
                                .join(format!("{}.pdf", e["row_key"].as_str().context("Row key")?)),
                            e["notice"]["client_data"]["date_of_birth_iso"]
                                .as_str()
                                .context("DOB")?
                                .replace('-', ""),
                        ));
                    }
                }
                "merge" => {
                    for (i, b) in record["bundles"]
                        .as_array()
                        .context("Bundles")?
                        .iter()
                        .enumerate()
                    {
                        let paths = b["members"]
                            .as_array()
                            .context("Members")?
                            .iter()
                            .map(|key| {
                                let e = record["entries"]
                                    .as_array()
                                    .unwrap()
                                    .iter()
                                    .find(|e| e["row_key"] == *key)
                                    .unwrap();
                                root.join(e["original"]["path"].as_str().unwrap())
                            })
                            .collect();
                        jobs_to_run.push((
                            paths,
                            output.join(format!("bundle-{i:04}.pdf")),
                            String::new(),
                        ));
                    }
                }
                _ => anyhow::bail!("Operation must be encrypt or merge"),
            }
            let count = jobs_to_run.len();
            let work =
                |(paths, destination, password): (Vec<PathBuf>, PathBuf, String)| -> Result<f64> {
                    let t = Instant::now();
                    if operation == "encrypt" {
                        encrypt(args.backend, &paths[0], &destination, &password)?;
                    } else {
                        merge(args.backend, &paths, &destination)?;
                    }
                    Ok(t.elapsed().as_secs_f64())
                };
            let mut task_seconds = 0.0;
            pool::with_pool(usize::from(workers), work, |sender, results| {
                for job in jobs_to_run {
                    sender.send(job).context("Workers stopped")?;
                }
                drop(sender);
                for result in results {
                    task_seconds += result?;
                }
                Ok(())
            })?;
            let result = json!({"count":count,"workers":workers,"operation":operation,"wall_seconds":started.elapsed().as_secs_f64(),"summed_task_seconds":task_seconds});
            fs::write(
                output.join("metrics.json"),
                serde_json::to_vec_pretty(&result)?,
            )?;
            println!("{result}");
            Ok(())
        }
    }
}
