//! Command parsing only; the library owns each complete workflow.
use anyhow::{Context, Result, ensure};
use clap::{Args, Parser, Subcommand};
use immuknow::{
    input::Selection,
    pipeline::{self, RunOptions},
};
use std::path::PathBuf;

#[derive(Parser)]
#[command(
    name = "immuknow",
    version,
    about = "Create and bundle immunization notices"
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}
#[derive(Args)]
#[group(required = false)]
struct Inputs {
    /// CSV file containing client information.
    csv: PathBuf,
    /// JSON file matching each client ID to a template filename.
    #[arg(
        long,
        conflicts_with = "template",
        requires = "templates",
        required_unless_present = "template"
    )]
    notice_assignments: Option<PathBuf>,
    /// One template file to use for every client.
    #[arg(long, conflicts_with_all=["notice_assignments", "templates"], required_unless_present="notice_assignments")]
    template: Option<PathBuf>,
    /// Directory containing the templates named in the assignment file.
    #[arg(long)]
    templates: Option<PathBuf>,
    /// Directory containing parameters and reference files.
    #[arg(long, default_value = "config")]
    config: PathBuf,
    /// CSV text encoding; by default, try UTF-8, Windows-1252, then Latin-1.
    #[arg(long, value_parser=["utf-8-sig", "cp1252", "latin-1"])]
    input_encoding: Option<String>,
}
impl Inputs {
    fn options(
        self,
        output: PathBuf,
        timestamp: Option<i64>,
        encryption_workers: u8,
        bundle_workers: u8,
    ) -> Result<RunOptions> {
        let (selection, templates) = match (self.notice_assignments, self.template) {
            (Some(manifest), None) => (
                Selection::Manifest(manifest),
                self.templates
                    .context("--templates is required with assignments")?,
            ),
            (None, Some(template)) => {
                let parent = template
                    .parent()
                    .filter(|p| !p.as_os_str().is_empty())
                    .unwrap_or(std::path::Path::new("."))
                    .to_path_buf();
                (Selection::Single(template), parent)
            }
            _ => anyhow::bail!("Select exactly one of --template or --notice-assignments"),
        };
        Ok(RunOptions {
            csv: self.csv,
            selection,
            templates,
            config: self.config,
            output,
            encoding: self.input_encoding,
            timestamp,
            encryption_workers,
            bundle_workers,
        })
    }
}
#[derive(Subcommand)]
enum Command {
    /// Generate notices, encrypted copies, bundles and a saved report.
    Run {
        #[command(flatten)]
        inputs: Inputs,
        #[arg(long, default_value = "runs")]
        output: PathBuf,
        #[arg(long)]
        timestamp: Option<i64>,
        #[arg(long, default_value_t=1, value_parser=clap::value_parser!(u8).range(0..=16))]
        encryption_workers: u8,
        #[arg(long, default_value_t=4, value_parser=clap::value_parser!(u8).range(1..=16))]
        bundle_workers: u8,
    },
    /// Write prepared client information and checks as JSON without creating PDFs.
    Prepare {
        #[command(flatten)]
        inputs: Inputs,
    },
    /// Export the shared Typst library and JSON schemas included in this executable.
    Resources {
        #[arg(long)]
        output: PathBuf,
    },
    /// Make new bundles from a saved run without rebuilding notices.
    Rebundle {
        run: PathBuf,
        #[arg(long)]
        policy: Option<PathBuf>,
        #[arg(long, requires = "reason")]
        withhold: Vec<String>,
        #[arg(long)]
        reason: Option<String>,
        #[arg(long)]
        release: Vec<String>,
        #[arg(long, default_value_t=4, value_parser=clap::value_parser!(u8).range(1..=16))]
        bundle_workers: u8,
    },
}
fn main() {
    if let Err(error) = execute() {
        eprintln!("ImmuKnow: {error:#}");
        std::process::exit(1);
    }
}
fn execute() -> Result<()> {
    match Cli::parse().command {
        Command::Run {
            inputs,
            output,
            timestamp,
            encryption_workers,
            bundle_workers,
        } => {
            let result = pipeline::run(&inputs.options(
                output,
                timestamp,
                encryption_workers,
                bundle_workers,
            )?)?;
            println!("{}", result.record.display());
            if !result.succeeded {
                std::process::exit(1);
            }
        }
        Command::Prepare { inputs } => {
            let prepared = pipeline::prepare(&inputs.options(PathBuf::new(), None, 0, 1)?)?;
            serde_json::to_writer_pretty(std::io::stdout().lock(), &prepared)?;
            println!();
        }
        Command::Resources { output } => {
            immuknow::resources::materialize(&output)?;
            serde_json::to_writer_pretty(
                std::io::stdout().lock(),
                &immuknow::resources::identity(),
            )?;
            println!();
        }
        Command::Rebundle {
            run,
            policy,
            withhold,
            reason,
            release,
            bundle_workers,
        } => {
            ensure!(
                withhold.is_empty() || reason.as_ref().is_some_and(|s| !s.trim().is_empty()),
                "Withholding requires a nonempty reason"
            );
            let result = pipeline::rebundle(
                &run,
                policy.as_deref(),
                &withhold,
                reason.as_deref(),
                &release,
                usize::from(bundle_workers),
            )?;
            println!("{}", result.record.display());
            if !result.succeeded {
                std::process::exit(1);
            }
        }
    }
    Ok(())
}
