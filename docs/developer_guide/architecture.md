# How the application works

Core follows one main path in `src/pipeline.rs`. It saves the supplied CSV, prepares
one set of client information per row, creates the selected notices with Typst,
checks their reports, makes requested encrypted copies, groups PDFs, and writes
the final report. The system supplying the CSV assesses immunization status;
the selected templates control wording and appearance.

| File | Responsibility |
| --- | --- |
| `src/main.rs` | Read command options and resolve project folders. |
| `src/terminal.rs` | Show progress and a readable completion summary. |
| `src/input.rs` | Read the CSV, project settings and reference lists; prepare client information. |
| `src/compiler.rs` | Keep one Typst compiler warm and obtain the PDF and checks from the same document. |
| `src/validation.rs`, `src/policy.rs` | Check the report and apply permitted rule changes. |
| `src/pdf.rs` | Encrypt copies and combine PDF pages. |
| `src/bundles.rs` | Choose which notices go into each grouped PDF and matching CSV. |
| `src/report.rs` | Write `run.json` and its readable HTML view. |
| `src/resources.rs` | Export the schemas and Typst library included in the executable. |

## Libraries in the pipeline

![Library map: Rust input preparation, one warm Typst engine and its QR plugin, original PDF checks, concurrent protected copies, grouped originals and run reports.](../assets/pipeline-libraries.svg)

The diagram names the main libraries used directly by Core and the QR plugin, with `wasmi` shown as Typst's WebAssembly runtime. It is a guide to responsibilities, not a list of every indirect dependency. Exact versions are in `Cargo.lock` and `typst-plugins/qr/Cargo.lock`.

`clap` reads command options. `csv` and `encoding_rs` read source text; `serde-saphyr` reads YAML settings. `serde`, `serde_json` and `chrono` support structured information and dates, while `jsonschema` checks the prepared data and template reports.

The official `typst`, `typst-layout`, `typst-kit` and `typst-pdf` libraries handle templates, fonts, page layout and PDF export inside the application. `comemo` lets Typst reuse earlier work. One compiler stays warm across notices. Typst runs the QR WebAssembly plugin through `wasmi`; that plugin uses `qrcodegen` and `wasm-minimal-protocol`. QR encoding currently happens inside that plugin, rather than through a separate native encoder. The same plugin can be used in Studio; see [QR codes](qr.md).

`lopdf` inspects originals, creates protected copies and combines original pages. `rand` supplies encryption randomness and `sha2` fingerprints saved files. A bounded queue built with Rust's standard library overlaps one encryption worker with notice creation. Four workers can combine independent groups afterward. Other libraries may use threads internally too. Grouped PDFs are built from originals, not the encrypted copies.

`serde_json`, Rust's HTML formatting and `csv` write the saved record, readable report and page lists. `include_dir` embeds the shared Typst library and schemas so an installed executable can export them. `anyhow`, `tempfile` and diagnostic helpers support errors and temporary files; they do not form extra pipeline stages.

For the elapsed-time picture, see [a minute of ImmuKnow](../user_guide/performance.md). Overlapping worker times must not be added to the main workflow total.

## Keep each client connected to the right notice

Every readable source row receives a key such as `row-000001`, in input order.
That key connects the source values, selected template, prepared information,
checks and PDFs. Filenames use these keys rather than personal identifiers.
A failed row does not stop later independent rows. If setup fails, the saved
record still accounts for source rows that could be read.

The compiler reads only the supplied project and local dependencies. Package
imports and downloads are unsupported. The project must contain an unchanged
copy of the shared library exported by this executable. Projects provide their
own settings, reference lists, templates, translations and images.

Typst returns PDF data and invisible check metadata from the same compiled
document. Core checks the metadata against `schemas/rendering.json`,
`typst/report.json`, the selected client and the document's page count. The JSON
is saved separately; it is never attached to the PDF or printed as extra pages.
The report schema retains `schema_version: 2`; filenames have no version suffix.
Git tags identify releases of the shared files.

## Keep useful results when something fails

Warnings allow inclusion in the normal grouped PDFs by default. A readable
original with failed checks goes into a separate review PDF. A missing or
uncreated original stays in the report only. A notice on hold is excluded from
both sets. Each included original appears once per bundle attempt, with its
page range in the matching CSV. A required page count never adds blank pages.

Encryption creates a separate AES-256 revision 6 PDF and verifies protection
and password access. The original remains available. Derived passwords are
never saved. One encryption worker and four bundle workers are used by default;
`src/pool.rs` provides the small bounded work queue. The coordinator alone updates
the saved record and sends count-only progress receipts to the terminal display. Library callers can run without terminal output. The display adds no worker thread.

## Save runs and later changes

A new run or bundle set starts in a uniquely named folder ending in `.incomplete`.
It receives its final name when finished. `run.json` is the saved record and
`report.html` is its escaped HTML view. These files and PDFs contain personal
information and should be kept private.

`immuknow rebundle` uses the saved originals and checks without creating notices
or repeating encryption. It takes the operating-system `.run.lock` before
reading the record and holds it through writes. Each attempt creates a new
numbered folder, leaving earlier bundles available. Failed attempts retain the
previous bundle decisions. Original checks remain in `checks`; permitted rule
changes produce `effective_checks`, with reasons. No visual or page-by-page
comparison is repeated. See [PDF review](../user_guide/pdf_validation.md) for the
commands and [configuration](../user_guide/configuration.md) for grouping rules.
