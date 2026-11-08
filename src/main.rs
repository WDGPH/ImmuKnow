//! Command parsing and terminal presentation; the library owns each workflow.
mod terminal;
use anyhow::{Result, ensure};
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
    /// Progress display: auto for terminals, plain for readable logs, off for silence.
    #[arg(long, global = true, value_enum, default_value_t = terminal::Mode::Auto)]
    progress: terminal::Mode,
    /// Add decorative emoji to the progress headings.
    #[arg(long, global = true)]
    emoji: bool,
}
#[derive(Args)]
#[group(required = false)]
struct Inputs {
    /// CSV file containing client information.
    csv: PathBuf,
    /// JSON file matching each client ID to a template filename.
    #[arg(
        long,
        visible_alias = "notices",
        conflicts_with = "template",
        required_unless_present = "template"
    )]
    notice_assignments: Option<PathBuf>,
    /// One template file to use for every client.
    #[arg(long, conflicts_with_all=["notice_assignments", "templates"], required_unless_present="notice_assignments")]
    template: Option<PathBuf>,
    /// Directory containing the templates named in the assignment file.
    #[arg(long)]
    templates: Option<PathBuf>,
    /// Project folder containing templates/ and config/.
    #[arg(long)]
    project: Option<PathBuf>,
    /// Directory containing parameters and reference files (default: config).
    #[arg(long)]
    config: Option<PathBuf>,
    /// CSV text encoding; by default, try UTF-8, Windows-1252, then Latin-1.
    #[arg(long, value_parser=["utf-8-sig", "cp1252", "latin-1"])]
    input_encoding: Option<String>,
}
impl Inputs {
    fn options(
        self,
        output: PathBuf,
        timestamp: Option<i64>,
        compile_workers: u8,
        encryption_workers: u8,
        bundle_workers: u8,
    ) -> Result<RunOptions> {
        let (selection, templates) = match (self.notice_assignments, self.template) {
            (Some(manifest), None) => (
                Selection::Manifest(manifest),
                self.templates.unwrap_or_else(|| {
                    self.project
                        .as_deref()
                        .unwrap_or(std::path::Path::new("."))
                        .join("templates")
                }),
            ),
            (None, Some(template)) => {
                let template = if let Some(project) = &self.project {
                    if template.is_absolute() {
                        template
                    } else {
                        project.join("templates").join(template)
                    }
                } else {
                    template
                };
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
            config: self.config.unwrap_or_else(|| {
                self.project
                    .map_or_else(|| PathBuf::from("config"), |p| p.join("config"))
            }),
            output,
            encoding: self.input_encoding,
            timestamp,
            compile_workers,
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
        /// Persistent notice compilers; defaults to two on four or more available CPUs.
        #[arg(long, default_value_t=pipeline::default_notice_workers(), value_parser=clap::value_parser!(u8).range(1..=2))]
        compile_workers: u8,
        /// Protection workers; zero runs inline, default matches available CPU capacity.
        #[arg(long, default_value_t=pipeline::default_notice_workers(), value_parser=clap::value_parser!(u8).range(0..=16))]
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
    let cli = Cli::parse();
    let mut terminal = terminal::Terminal::new(cli.progress, cli.emoji);
    match cli.command {
        Command::Run {
            inputs,
            output,
            timestamp,
            compile_workers,
            encryption_workers,
            bundle_workers,
        } => {
            let result = pipeline::run_with_progress(
                &inputs.options(
                    output,
                    timestamp,
                    compile_workers,
                    encryption_workers,
                    bundle_workers,
                )?,
                &mut |event| terminal.update(event),
            )?;
            terminal.finish(&result);
            terminal.print_record(&result);
            if !result.succeeded {
                std::process::exit(1);
            }
        }
        Command::Prepare { inputs } => {
            let prepared = pipeline::prepare(&inputs.options(PathBuf::new(), None, 1, 0, 1)?)?;
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
            terminal.finish(&result);
            terminal.print_record(&result);
            if !result.succeeded {
                std::process::exit(1);
            }
        }
    }
    Ok(())
}
