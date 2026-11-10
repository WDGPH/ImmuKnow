//! Human-readable stderr output. Stdout remains available to scripts and Studio.
use clap::ValueEnum;
use immuknow::pipeline::{Progress, RunResult};
use std::{
    io::{self, IsTerminal, Write},
    time::{Duration, Instant},
};

#[derive(Clone, Copy, Default, PartialEq, ValueEnum)]
pub enum Mode {
    #[default]
    Auto,
    Plain,
    Off,
}

pub struct Terminal {
    mode: Mode,
    live: bool,
    emoji: bool,
    bold: bool,
    stage: &'static str,
    started: Instant,
    stage_started: Instant,
    drawn: Instant,
    line: bool,
}
impl Terminal {
    pub fn new(mode: Mode, emoji: bool) -> Self {
        let now = Instant::now();
        let live = mode == Mode::Auto
            && io::stderr().is_terminal()
            && std::env::var("TERM").is_ok_and(|term| term != "dumb");
        Self {
            mode,
            live,
            emoji,
            bold: live && std::env::var_os("NO_COLOR").is_none(),
            stage: "",
            started: now,
            stage_started: now,
            drawn: now,
            line: false,
        }
    }

    fn clear(&mut self) {
        if self.line {
            let _ = write!(io::stderr(), "\r\x1b[2K");
            self.line = false;
        }
    }

    pub fn update(&mut self, event: Progress) {
        if self.mode == Mode::Off {
            return;
        }
        let (stage, count, extra) = match event {
            Progress::Preparing => ("Reading inputs", None, String::new()),
            Progress::Notices {
                done,
                total,
                protected,
            } => (
                "Creating notices",
                Some((done, total)),
                if protected > 0 {
                    format!(" · {protected} protected")
                } else {
                    String::new()
                },
            ),
            Progress::Protecting { done, total } => (
                "Finishing protected copies",
                Some((done, total)),
                String::new(),
            ),
            Progress::Grouping { total: 0, .. } => return,
            Progress::Grouping { done, total } => {
                ("Grouping PDFs", Some((done, total)), String::new())
            }
            Progress::Reporting => ("Saving your report", None, String::new()),
        };
        let changed = self.stage != stage;
        if changed {
            // Keep the completed count visible when moving on to the next job.
            if self.line {
                eprintln!();
                self.line = false;
            }
            if self.stage.is_empty() {
                let title = if self.emoji {
                    "🌿 ImmuKnow"
                } else {
                    "ImmuKnow"
                };
                if self.bold {
                    eprintln!("\n\x1b[1m{title}\x1b[0m\n");
                } else {
                    eprintln!("\n{title}\n");
                }
            }
            self.stage = stage;
            self.stage_started = Instant::now();
            // A persistent line gives logs and screen readers one announcement per stage.
            eprintln!("  {stage}...");
        }
        if !self.live {
            if let Some((done, total)) = count {
                if done > 0 && (done % 100 == 0 || done == total) {
                    eprintln!("  {done}/{total} processed{extra}");
                }
            }
            return;
        }
        let Some((done, total)) = count else {
            return;
        };
        if !changed && done != total && self.drawn.elapsed() < Duration::from_millis(100) {
            return;
        }
        self.drawn = Instant::now();
        self.clear();
        let width = std::env::var("COLUMNS")
            .ok()
            .and_then(|s| s.parse::<usize>().ok())
            .unwrap_or(80);
        let seconds = self.stage_started.elapsed().as_secs_f64();
        let rate = if seconds >= 1.0 && stage == "Creating notices" {
            format!(" · {:.0}/s", done as f64 / seconds)
        } else {
            String::new()
        };
        let bar_width = if width < 80 { 8 } else { 16 };
        let filled = if total == 0 {
            bar_width
        } else {
            (done * bar_width / total).min(bar_width)
        };
        let status = if width < 40 {
            format!("  {done}/{total}")
        } else {
            let details = if width < 80 { "" } else { &extra };
            format!(
                "  [{}{}] {done}/{total}{rate}{details}",
                "#".repeat(filled),
                "-".repeat(bar_width - filled)
            )
        };
        let mut stderr = io::stderr().lock();
        if self.bold {
            let _ = write!(stderr, "\r\x1b[36m{status}\x1b[0m");
        } else {
            let _ = write!(stderr, "\r{status}");
        }
        let _ = stderr.flush();
        self.line = true;
    }

    /// Interactive users get the report link; redirected stdout keeps the record path.
    pub fn print_record(&self, result: &RunResult) {
        println!("{}", result.record.display());
    }

    pub fn finish(&mut self, result: &RunResult) {
        if self.mode == Mode::Off {
            return;
        }
        self.clear();
        let s = &result.summary;
        let heading = if !result.succeeded {
            "Finished — review needed"
        } else if s.warnings > 0 || s.run_findings > 0 {
            "Finished — check the findings"
        } else {
            "Finished"
        };
        let icon = if self.emoji {
            if result.succeeded { "✨ " } else { "🔎 " }
        } else {
            ""
        };
        eprintln!(
            "\n{icon}{heading} in {:.1}s\n",
            self.started.elapsed().as_secs_f64()
        );
        let report = &s.report;
        let percent = |count: usize| {
            if report.rows == 0 {
                "n/a".to_owned()
            } else {
                format!("{:.1}%", 100.0 * count as f64 / report.rows as f64)
            }
        };
        eprintln!("  Severity ({} source records):", report.rows);
        for label in ["error", "warning", "clear", "pending"] {
            let count = report.severity.get(label).copied().unwrap_or(0);
            eprintln!("    {label}: {count} ({})", percent(count));
        }
        eprintln!("  Delivery:");
        for label in ["ready", "review", "withheld", "report_only", "undecided"] {
            eprintln!(
                "    {label}: {}",
                report.routes.get(label).copied().unwrap_or(0)
            );
        }
        eprintln!("  Finding codes (overlapping source records):");
        let mut warnings = Vec::new();
        for ((severity, code), rows) in &report.codes {
            if severity == "fail" {
                eprintln!("    error {code}: {} ({})", rows.len(), percent(rows.len()));
            } else {
                warnings.push((code, rows.len()));
            }
        }
        warnings.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(b.0)));
        for (code, count) in warnings.iter().take(10) {
            eprintln!("    warning {code}: {count} ({})", percent(*count));
        }
        if warnings.len() > 10 {
            eprintln!(
                "    {} more warning codes in findings.csv",
                warnings.len() - 10
            );
        }
        if report.diagnostics > 0 {
            eprintln!(
                "    compiler diagnostics: {} ({})",
                report.diagnostics,
                percent(report.diagnostics)
            );
        }
        if report.run_findings > 0 {
            eprintln!("  Run/attempt findings: {}", report.run_findings);
        }
        if let Some(parent) = result.record.parent() {
            if s.records_path.is_empty() || s.findings_path.is_empty() {
                eprintln!(
                    "  CSV exports unavailable; run warnings {} --refresh",
                    parent.display()
                );
            } else {
                eprintln!("  Records: {}", parent.join(&s.records_path).display());
                eprintln!("  Findings: {}", parent.join(&s.findings_path).display());
            }
        }
    }
}
impl Drop for Terminal {
    fn drop(&mut self) {
        self.clear();
    }
}
