# Rust pipeline exploration

This draft is based directly on `main`. It includes the compiled QR resources
and their source/build checks used by the experiment, with the existing Python
orchestration left intact. Earlier Python performance changes are documented in
[PR #241](https://github.com/WDGPH/ImmuKnow/pull/241); they are not prerequisites
for building or running this Rust executable.

This standalone experiment starts with the original client CSV and assignment
manifest. It prepares facts in Rust, keeps official Typst 0.15.1 warm, obtains
PDF bytes and the placed report from the **same compiled document**, validates
against Core's existing schemas, and uses lopdf 0.47.0 for individual AES-256
revision-6 encryption and size-based PDF/CSV bundles. No Python runs in that path.
Library internals retain their default threading. By default application work is
sequential; optional bounded PDF workers can overlap encryption with compilation
and process independent bundles concurrently. The Rust source and shared Typst
resources match the measured experiment; this PR carries the compiled QR
resource update relative to `main`.

This is an experiment, not an alternative production command. The existing
Python CLI retains its runtime dependencies. The earlier direct-report Rust Typst middleware with Python orchestration and
pikepdf remains a fallback candidate, documented in #241/#242 rather than
included in this standalone branch.

## CI coverage

`Check Rust pipeline` builds the release executable with the pinned toolchain and
locked Cargo dependencies, runs the shared render-contract/PDF/worker tests,
checks formatting and exercises the executable entry point. Cargo builds run
serially to bound compiler memory; application/library runtime threads retain
their defaults. Cached build outputs avoid rebuilding Typst on every revision.

The existing Python matrix stays enabled because this draft still ships the
Python CLI and changes its shared QR resources. It also type-checks the optional
Python audit tools. Their independent PDF reader, `pikepdf`, is a locked
**development-only** dependency, not a dependency of the Rust executable.
Install those tools with `uv sync --locked --group dev`. CI does not run the
1,000-client performance experiment or claim production workflow parity.

## Build and run

A first build needs Rust 1.92 and network access to download locked dependencies.
Subsequent builds can use Cargo's cache. Build serially on constrained machines:

```sh
cd experiments/rust-pipeline
cargo build --release --locked --jobs 1
cargo test --release --locked --jobs 1
cargo fmt --check
```

For a complete fictional project whose `templates/lib/immuknow` exactly matches
this Core checkout:

```sh
target/release/immuknow-rust-pipeline run \
  --csv /path/to/fictional/students.csv \
  --assignments /path/to/fictional/assignments.json \
  --config /path/to/project/config --templates /path/to/project/templates \
  --core ../.. --output /path/to/experimental-runs
```

For the preferred measured configuration, add
`--encryption-workers 1 --bundle-workers 4`.
Compilation stays on the calling thread. Encryption uses a bounded queue of
filenames and in-memory passwords, with results associated by entry index. Only
the calling thread updates the run record. Every worker joins before failure
reporting or directory publication. Bundles retain input order regardless of
completion order. `--encryption-workers 0` keeps encryption inline;
`--bundle-workers 1` handles one bundle at a time. Neither option changes library
thread defaults.

`encryption_task_seconds` sums overlapping task wall times; it is not an elapsed
stage timer. `render_encrypt_wall_seconds`, `encryption_drain_seconds`,
`checkpoint_seconds` and `delivery_seconds` identify elapsed work on the critical
path. Complete command time also includes the final record/view and process exit.

Use `TYPST_FONT_PATHS`, `TYPST_IGNORE_SYSTEM_FONTS=true` and, if needed,
`TYPST_IGNORE_EMBEDDED_FONTS=true` for the same font discovery as the native CLI.
`--timestamp UNIX_SECONDS` freezes PDF metadata and Typst's clock together.
Package imports are refused by the Rust file loader, including computed imports;
there is no package downloader. Project resources cannot contain symbolic links.

## What this establishes

The executable performs factual history parsing, deduplication and validity
coverage, date/age preparation, disease normalization and forecast coverage,
explicit notice assignment, schema and source/report association validation,
PDF publication, encryption, and whole-cohort visual bundling. Every source row
keeps its original values and stable row key. Independent compilation/report or
encryption failures retain useful originals and allow later notices to continue.
A run has a unique `.incomplete` directory until its record and outputs finish.
Reports are extracted directly; there is no evidence attachment or Python rewrite.

`check.py` is an **independent verification tool**, requiring Core's Python dev
dependencies. It is outside the timed Rust executable. Given a reference run
with identical input, settings and project resources:

```sh
python check.py --record /path/to/rust/run.json \
  --reference /path/to/reference/run.json --output /path/to/audit.json
```

It compares every payload and complete render report, verifies PDF encryption
with pikepdf, and checks representative original/encrypted/bundled page pixels
and links, all bundle memberships and findings-CSV page spans.

## Deliberate limits

- UTF-8 comma CSV and manifest selection only; no legacy encodings, delimiter
  detection or single-template selector yet.
- Simplified experimental validation only; no school-reference validation,
  policy overrides,
  warning acceptance, holds, grouping fields, fixed notice length, cleanup or
  saved-run delivery. Unsupported configured options fail explicitly.
- Individual encryption currently supports the compact DOB password setting
  only. The lower-level encoder is also tested with a Unicode password.
- `typst.bin` is accepted from existing projects but unused: this executable
  embeds the pinned official engine. Hard per-notice deadlines are unsupported.
- Experimental `run.json`/HTML and CSV formats are **not compatible** with the
  production run schema/review workflow. Checkpointing and failure accounting
  are incomplete compared with the production orchestrator.
- Bundles preserve original page subtrees, inherited resources/geometry and
  direct-reference links. Forms are rejected. Named link destinations resolve
  within their source notice before merging; full arrays retain coordinates and
  zoom. Outlines,
  document metadata and tagged structure are not combined. **Bundle accessibility
  is not preserved.** The current pikepdf bundle baseline likewise has no
  document-level structure tree; this is not an additional Rust regression.
  Original/encrypted individual notices retain their tags.
- The merger targets notice PDFs. Additional catalog handling should follow
  demonstrated template needs, rather than general-purpose PDF support.

The strict input contract and existing Typst library reduce the porting work,
but do not eliminate Python's preparation, policy, review and publication logic.
Timing this subset is evidence about feasibility, not production feature parity
or a capacity guarantee.

## Matched Python comparison

`compare_python.py` runs the unchanged Core pipeline with one application worker
and pikepdf, replacing only the compiler call with this binary's `serve` mode.
It keeps Core's report validation, policy evaluation, saved records, encryption
verification and delivery enabled. This is a timing adapter with blocking pipes,
not a production-ready transport. Run it under an external whole-run deadline.
The adapter targets the optimized Python API from PR #241 (`60c23c6`), rather
than the unchanged Python API on this standalone branch. Pass that reference
checkout as `--core`. Both variants must use the same fonts, CSV, configuration,
templates, binary and library thread environment:

```sh
python compare_python.py --core /path/to/PR241-checkout \
  --binary "$PWD/target/release/immuknow-rust-pipeline" \
  --csv /path/to/fictional/students.csv \
  --assignments /path/to/fictional/assignments.json \
  --config /path/to/project/config --templates /path/to/project/templates \
  --output /path/to/python-comparison --metrics /path/to/python-metrics.json
```

The Rust subset and Python application still differ in policy, reports and
catalog preservation. Same-compiler timing isolates important costs; it does not
establish full feature equivalence. `check_boundaries.py` exercises failures,
Unicode encryption with an independent reader, cross-page links, and inherited
PDF resources/geometry. Its arguments identify a six-row fixture, complete
project, binary, Core source root and a new output directory.

## Studio and Template handoff

Authored Typst APIs and the JSON facts contract remain compatible. Relative to
`main`, this PR updates the shared library to use the compiled QR plugin;
existing projects must refresh their complete shared library tree, and Studio
must update its Core resource pin accordingly. Studio's browser already consumes
the JSON facts contract checked here. Studio's **build scripts** still call Python preparation/resource APIs;
Template's local helpers call the Python pipeline. Replacing Core entirely would
also require adapting those callers and verifying their existing native/browser
handoff tests. This experiment leaves those interfaces intact and changes neither
downstream project's dependency pins.

## Measured cohort

One complete measured run per architecture used the same 1,000 unique fictional
clients (six repeated Template cases), 2,000 pages, individual encryption, ten
PDF/CSV bundles, fonts, and exact Rust compiler binary. The environment had a
four-CPU quota and 8 GiB memory limit. Application work in this initial comparison was sequential; library
threading retained its defaults. The source implementing that measured executable
was the initial Rust experiment before the bounded PDF-worker changes.

| Path | Complete command | Pipeline timer | Peak process-tree RSS |
| --- | ---: | ---: | ---: |
| This Rust experiment, lopdf | 106.2 s | 103.7 s | 618 MiB |
| Existing Python pipeline, same warm Rust compiler, pikepdf | 133.3 s | 129.9 s | 694 MiB |

These are individual observations, not a capacity guarantee. The prototype is
about 20% faster in this comparison and has fewer workflow features. That
sequential configuration did not meet 1,000 notices in 60 seconds. Earlier 54.8/59.9-second experiments retained
four Python coordination/encryption workers; they are not equivalent sequential
end-to-end comparisons.

Rust recorded 35.9 seconds in Typst compilation/export, 39.0 in encryption,
6.0 in PDF inspection/report validation, and 10.6 in delivery. Factual preparation
was 0.15 seconds. The rest includes resource setup, facts/checkpoints and reports;
the final report write is outside the internal pipeline timer but inside complete
command time. Python's compiler timer includes its report validation, so its
62.9-second value is not directly equivalent to Rust's compiler-only timer.
Python encryption took 44.1 seconds and delivery 8.7 seconds.

The independent audit compared all 1,000 original source rows, prepared payloads
and complete Typst reports, verified every Rust encrypted notice with pikepdf,
and checked all saved resource hashes, bundle memberships and CSV page spans.
All passed. Six representative cases also matched original/encrypted/bundled
page pixels and links. Rust tests passed the 66 shared report-contract cases;
the executable boundary harness passed 15 failure/PDF cases.

This establishes feasibility of the native data-to-delivery path and makes
lopdf a credible candidate for our notice-PDF scope. The remaining adoption work
is production policy/review and saved-run behavior, preparation/options parity,
packaging/resource identity, downstream helpers and deadline semantics. Keep the
Python/Rust/pikepdf path available while those interfaces are migrated and tested.
Further performance work should measure report/checkpoint costs and encryption;
porting CSV preparation alone cannot materially change these timings. There is
no demonstrated need for a general catalog/tag merger or an encrypted-PDF writer
fork.

## Bounded PDF concurrency

The next experiment keeps the same single warm compiler and overlaps encryption
with notice processing. Bundle workers run after that stage, each writing a
separate PDF. Neither Typst's internal thread defaults nor the shared library/QR
code changed. Validation, encrypted-output verification, original retention,
100-notice checkpoints, ten PDF/CSV bundles and final JSON/HTML remain enabled.

| Complete 1,000-notice command | Background encryption threads | Bundle workers | Seconds |
| --- | ---: | ---: | ---: |
| Initial sequential prototype | 0 | 1 | 106.2 |
| Bounded PDF workers, original reporting | 3 | 4 | 62.2 |
| Reused report serialization, no final record reparse | 1 | 4 | 57.4 |
| Same reporting cleanup | 3 | 4 | 58.6 |
| Final committed queue/report cleanup, repeat | 1 | 4 | 59.4 |

The final measured Rust sources and shared-library bytes are retained on this
standalone branch. The 57.4/58.6-second pair predates only the final
queue-disconnection fix. These are individual observations, not error
bars or a capacity guarantee. The final run's small margin below 60 seconds does
not establish headroom for a more expensive input mix. Extra encryption threads
showed no useful benefit here. One background thread overlaps the two costly
stages already; four workers did help independent bundles (about 4.6–5.3 seconds
versus the earlier 10.6). Parallel bundles raised observed peak process memory
from about 618 MiB to 1.1 GiB.

Prefer `--encryption-workers 1 --bundle-workers 4` for this measured environment.
Defaults remain sequential for explicit comparisons and smaller-memory machines.
The bounded queue stores paths/passwords, not an unbounded collection of parsed
PDFs. Worker receipts keep each encrypted output associated with its original
entry. If all workers panic, the queue disconnects and the producer returns an
error; workers join before failure reporting or directory publication.

Reporting now serializes the saved record once for JSON and its escaped HTML
view. The CLI uses the completion status already in memory instead of parsing
the finished 32 MiB record merely to choose its exit code. This preserves both
outputs and their checkpoint frequency while removing duplicate work.

The full independent audit passed for the final 1,000 originals/encrypted copies,
all prepared payloads/reports, membership/CSV spans and representative rendered
pages/links. The 15 CLI/PDF boundary cases passed with both three and one
background encryption threads. Rust's four test functions include the 66 shared
report-contract cases and the worker-panic regression. The prototype's production
feature and hard-deadline limits above still apply.

## PDF library choice

The [isolated backend comparison](pdf-backend-probe/README.md) tested pinned
pdf_oxide 0.3.78 against lopdf 0.47.0, with one/four workers and identical
post-encryption verification. Four-worker merging took 2.9 seconds with pdf_oxide
versus 3.9 with lopdf, but pdf_oxide misdirected an internal link between distinct
source PDFs. Its AES-256 revision-6 output omitted `/Perms` and was rejected by
qpdf for both ASCII DOB and Unicode passwords, even though MuPDF opened it.

Keep lopdf. The optional comparison crate and lock remain separate from the
pipeline. Neither candidate speed claims nor successful page-count checks
establish compatible encryption/navigation. The sub-minute end-to-end results
above already use lopdf, so replacing it is unnecessary to demonstrate the target.
