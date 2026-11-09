//! Command parsing and terminal presentation; the library owns each workflow.
mod terminal;
use anyhow::{Result, ensure};
use clap::{Args, Parser, Subcommand};
use immuknow::{
    input::Selection,
    pipeline::{self, RunOptions},
};
use std::{
    io::{BufWriter, Write},
    path::PathBuf,
};

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
    #[arg(required_unless_present = "sample", conflicts_with = "sample")]
    csv: Option<PathBuf>,
    /// Use sample.json, or the conventional fictional sample, inside the project.
    #[arg(long, conflicts_with_all = ["csv", "notice_assignments", "template", "templates", "config"])]
    sample: bool,
    /// JSON file matching each client ID to a template filename.
    #[arg(
        long,
        visible_alias = "notices",
        conflicts_with = "template",
        required_unless_present_any = ["template", "sample"]
    )]
    notice_assignments: Option<PathBuf>,
    /// One template file to use for every client.
    #[arg(long, conflicts_with_all=["notice_assignments", "templates"], required_unless_present_any=["notice_assignments", "sample"])]
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
        mut self,
        output: PathBuf,
        timestamp: Option<i64>,
        compile_workers: u8,
        encryption_workers: u8,
        bundle_workers: u8,
    ) -> Result<RunOptions> {
        if self.sample {
            let project = self.project.as_deref().unwrap_or(std::path::Path::new("."));
            let (csv, assignments) = immuknow::project::sample_paths(project)?;
            self.csv = Some(csv);
            self.notice_assignments = Some(assignments);
        }
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
            csv: self
                .csv
                .expect("Clap requires a CSV unless --sample resolves it"),
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
    /// Set up or check a configured notice project without Python.
    Project {
        #[command(subcommand)]
        command: ProjectCommand,
    },
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
    /// List distinct URL warnings in a completed saved run.
    Warnings {
        run: PathBuf,
        /// Regenerate the HTML view from the saved record.
        #[arg(long)]
        refresh: bool,
    },
    /// Record or revoke review of an exact warning issue.
    Acknowledge {
        run: PathBuf,
        issue: String,
        /// Explain the review decision; avoid client information.
        #[arg(long)]
        reason: String,
        /// Revoke an existing acknowledgment.
        #[arg(long)]
        revoke: bool,
    },
    /// Make new bundles from a saved run without rebuilding notices.
    Rebundle {
        run: PathBuf,
        #[arg(long)]
        policy: Option<PathBuf>,
        /// JSON bundle/review filename templates; originals retain their saved names.
        #[arg(long)]
        filenames: Option<PathBuf>,
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

#[derive(Subcommand)]
enum ProjectCommand {
    /// Install the executable's shared library into templates/lib/immuknow.
    Sync {
        #[arg(long, default_value = ".")]
        project: PathBuf,
        /// Replace an existing library that differs; authored files are untouched.
        #[arg(long)]
        replace: bool,
    },
    /// Verify the shared library and prepare the project's fictional sample.
    Check {
        #[arg(long, default_value = ".")]
        project: PathBuf,
        /// Also render the sample in a temporary folder, removed after checking.
        #[arg(long)]
        sample: bool,
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
        Command::Project { command } => match command {
            ProjectCommand::Sync { project, replace } => {
                immuknow::project::sync_library(&project, replace)?;
                println!("Shared library matches this ImmuKnow executable.");
            }
            ProjectCommand::Check { project, sample } => {
                immuknow::project::check_library(&project)?;
                let (csv, assignments) = immuknow::project::sample_paths(&project)?;
                let temporary = tempfile::tempdir()?;
                let options = RunOptions {
                    csv,
                    selection: Selection::Manifest(assignments),
                    templates: project.join("templates"),
                    config: project.join("config"),
                    output: temporary.path().join("runs"),
                    encoding: None,
                    timestamp: None,
                    compile_workers: pipeline::default_notice_workers(),
                    encryption_workers: pipeline::default_notice_workers(),
                    bundle_workers: 4,
                };
                if sample {
                    // A check removes its output, so do not print the normal
                    // run summary's report link to a temporary file.
                    let result = pipeline::run(&options)?;
                    println!(
                        "Sample: {}/{} PDFs created; {} notices with warnings; {} failed.",
                        result.summary.originals,
                        result.summary.rows,
                        result.summary.warnings,
                        result.summary.failed,
                    );
                    ensure!(
                        result.succeeded,
                        "Sample run failed; run immuknow run --sample --project {} to retain its report",
                        project.display()
                    );
                    println!(
                        "Project checked: {}/{} sample PDFs created. Temporary output removed.",
                        result.summary.originals, result.summary.rows
                    );
                } else {
                    let prepared = pipeline::prepare(&options)?;
                    let failed = prepared["entries"]
                        .as_array()
                        .into_iter()
                        .flatten()
                        .flat_map(|entry| entry["checks"].as_array().into_iter().flatten())
                        .any(|check| check["status"] == "fail");
                    ensure!(
                        !failed,
                        "Sample preparation contains failures; use immuknow prepare --sample --project {} for findings",
                        project.display()
                    );
                    println!(
                        "Project checked: shared library matches; {} sample rows prepared.",
                        prepared["entries"].as_array().map_or(0, Vec::len)
                    );
                }
            }
        },
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
            let mut stdout = BufWriter::new(std::io::stdout().lock());
            serde_json::to_writer_pretty(&mut stdout, &prepared)?;
            writeln!(stdout)?;
            stdout.flush()?;
        }
        Command::Resources { output } => {
            immuknow::resources::materialize(&output)?;
            serde_json::to_writer_pretty(
                std::io::stdout().lock(),
                &immuknow::resources::identity(),
            )?;
            println!();
        }
        Command::Warnings { run, refresh } => {
            immuknow::warning_review::list(&run, refresh)?;
        }
        Command::Acknowledge {
            run,
            issue,
            reason,
            revoke,
        } => {
            immuknow::warning_review::acknowledge(&run, &issue, &reason, revoke)?;
        }
        Command::Rebundle {
            run,
            policy,
            filenames,
            withhold,
            reason,
            release,
            bundle_workers,
        } => {
            ensure!(
                withhold.is_empty() || reason.as_ref().is_some_and(|s| !s.trim().is_empty()),
                "Withholding requires a nonempty reason"
            );
            let result = pipeline::rebundle_with_filenames(
                &run,
                policy.as_deref(),
                filenames.as_deref(),
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
