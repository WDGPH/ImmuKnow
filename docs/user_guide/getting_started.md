# Getting started

Install Rust 1.92 or later, then build and install the executable from a checkout:

```sh
cargo install --path . --locked
immuknow resources --output ./resources
```

The executable contains the Typst 0.15.1 engine and shared resources. Install the fonts required by your authored project on the workstation. Exported resources include `config/`, `schemas/`, `typst/` and a resource manifest; keep the shared library with the template project as described in [template authoring](phu_templates.md).

Provide a CSV, your configuration directory and exactly one selector. For one notice for the whole cohort:

```sh
immuknow run clients.csv --template ./project/templates/overdue_diseases_v1.en.typ \
  --config ./project/config --output ./runs
```

For explicit per-client selection, use a manifest and a template directory:

```sh
immuknow run clients.csv --notice-assignments assignments.json \
  --templates ./project/templates --config ./project/config --output ./runs
```

The [configuration guide](configuration.md) describes the manifest and reference files. Template filenames have the form `<version>.<language>.typ`; supported languages are `en` and `fr`. Assignments choose notices; the catalog checks applicability and does not select or translate notices.

## Prepare the input

See the [CSV field reference](input_schema.md) for required columns. Text is retained as text, including leading zeros. CSV may use comma, semicolon, tab or pipe delimiters. Automatic decoding tries UTF-8 (with an optional BOM), Windows-1252, then Latin-1. To specify one, pass `--input-encoding utf-8-sig`, `cp1252` or `latin-1`. Control characters, repeated or malformed headers, and rows with a different number of fields are rejected.

A blank or incomplete source value can produce a finding while retaining the row. Invalid history, duplicate nonblank client IDs, missing or ambiguous assignments, and forecasted agents that do not cover overdue diseases reject the cohort before rendering. `intended_reader` may be blank, `student`, or `guardian`; other values require correction. Source rows are retained with stable row keys before preparation. If malformed CSV structure prevents row parsing, the raw `source.csv` is retained with the rejection reason.

## Vaccine names in history

Each history entry is `YYYY-MM-DD - Agent`, optionally followed by ` - Valid` or ` - Invalid`, and ends with `;`. Dates must exist, separators and validity tokens are exact, and every fragment is checked. For example:

```text
2020-05-01 - MMR - Valid;2021-06-02 - Tdap;
```

Blank history and `-;` or `-  -;` mean no history. Agent names match the selected vaccine reference exactly. A placed history table reports unknown agents unless its `ignore-agents` option excludes them; an omitted table performs no mapping check. See [template authoring](phu_templates.md).

## Review the run

A new run is held in an `.incomplete` directory until it finishes. It retains the source CSV, configuration and resource copies, prepared facts, original PDFs, `run.json`, `report.html`, and numbered bundle directories. Warnings remain eligible for delivery by default; failed checks route readable PDFs to review bundles. A run with failures exits nonzero; warnings alone exit successfully. See [PDF review](pdf_validation.md) for withholding and rebuilding bundles.

Use `immuknow prepare` with the same CSV, selector, config and optional encoding to write versioned facts and checks to standard output without rendering PDFs. See the [API reference](../reference/api.md).

## Intended reader

Set the optional `intended_reader` column to `student` or `guardian`. A blank
value uses the age default: student at 16 or older, guardian under 16. Unknown
age without an explicit reader uses neutral wording. Other values reject the
input. Supply the intended mailing destination in the address columns.
