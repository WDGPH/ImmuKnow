# Getting started

Install Python 3.11 or later, [uv](https://docs.astral.sh/uv/), and
[Typst 0.15.1](https://typst.app/docs/changelog/0.15.1/). Put `typst`
on `PATH`, set `TYPST_BIN`, or configure `typst.bin` in `parameters.yaml`.
Start with [ImmuKnow Template](https://github.com/WDGPH/ImmuKnow-Template),
or download a Studio project with **Include fictional client data** enabled.
From that project directory, run the fictional sample:

```bash
uv sync --locked
uv run python scripts/run.py --sample
```

Template maintains the example clients and sample assignments. Studio uses the
same fictional people for previews and can include a selected example in a
project download. Their histories and forecasts are illustrative; they are not
vaccination schedules or clinical assessments. Follow the [Template guide](https://github.com/WDGPH/ImmuKnow-Template)
for setup and sample options. The examples describe facts as of January 15, 2026;
project dates determine ages and notice applicability.

Keeping one CSV in Template lets native projects and browser previews use the
same people. Template owns their facts and sample notice assignments; Studio
supplies preview descriptions and builds preview JSON. Public examples help
people design notices and try the workflow. Independent test fixtures exercise
engine and project behavior; see the [testing guide](../developer_guide/testing.md).

To run Core directly from a checkout, first prepare a Template project using its
setup guide. With that project in `./my-project`:

```bash
uv sync
uv run immuknow ./my-project/input/sample/sample_students.csv \
  --notice-assignments ./my-project/input/sample/sample_assignments.json \
  --templates ./my-project/templates --config ./my-project/config --output ./runs
```

An installed package provides `immuknow` and its resources without a checkout.

## Prepare input

Pass the path to one CSV extracted from Panorama/PEAR for the complete cohort.
Relative paths start from your working directory: `students.csv` reads a file
in that directory, while `./input/students.csv` reads it from the `input`
subdirectory. Absolute paths are also accepted. Use the column names and required
fields listed in [CSV input fields](input_schema.md).

Absent optional columns are filled with empty strings. Missing required columns
stop shared setup. Row findings preserve the known facts and identify problems.
Panorama client IDs are ten-digit strings using `0`–`9`; malformed or repeated
nonblank IDs reject the complete file. Missing IDs retain their source row keys
and may be used with the single-template selector.

The CSV is read as text, with raw values saved before trimming whitespace.
Comma, semicolon, tab and pipe separators are supported. Headers must be unique,
nonempty names without surrounding whitespace. Every row must have the same
number of fields as the header; quote values that contain the separator or a
line break. Repeated headers, broken quoting and extra or missing fields stop
the run before notices are generated.

The reader first tries UTF-8, with or without a byte-order mark, then Windows-1252,
then Latin-1. The selected encoding and separator are recorded in `run.json`.
This is a fallback order, not guaranteed encoding detection. To select explicitly,
use `--input-encoding utf-8-sig`, `--input-encoding cp1252`, or
`--input-encoding latin-1`. Unsupported control characters stop the run so that
damaged names or addresses cannot silently reach notices.

Blank cells stay blank; literal `NA`, `nan`, and `NULL` stay as text. Unknown
birth dates produce unknown ages, not an assumed age group. Incomplete mailing
addresses remain in the cohort with warnings. Normalized history retains all
disease mappings.
Forecasted agents must cover every overdue disease using the selected
`vaccine_reference.json` and disease-name normalization. Missing coverage rejects
the cohort before notices are generated, even when other diseases are also
covered. Additional coverage warns. Unlisted agents do not count toward coverage;
they warn when the known agents already cover the overdue set. Details are saved
with each source row in `run.json`.
The packaged input schema defines the columns and cannot be replaced through
`--config`.

### Intended reader

The optional `intended_reader` column accepts `student` or `guardian`. An explicit choice
controls both ordinary letter wording and the default address addressee,
regardless of age. Leave it blank to use the default: students aged 16 or older
receive student wording, younger clients receive guardian wording, and unknown
age uses neutral wording. Reader selection does not change the birth date or age.

Supply the mailing destination in the existing street, city, province and postal
code columns. A reader choice does not create guardian contact details. Invalid
values reject the cohort before any notices are rendered; correct the source
and run it again. Saved source rows retain the supplied choice. Rename the former `reader` column
to `intended_reader` before running.

### History format

End every administration with a semicolon, including the last, as in Panorama
exports. Each entry is exactly `YYYY-MM-DD - Agent;`, optionally with
` - Valid` or ` - Invalid` before the semicolon, for example
`2020-05-01 - MMR - Valid;`. Month and day always have two digits
(`2020-05-01`, not `2020-5-1`), and the date must exist. Use one space on
each side of the separating hyphens. Spaces, tabs and line breaks may surround
complete entries. Hyphenated names such as `DTaP-IPV-Hib` remain intact; an
extra field separator inside an agent name is ambiguous and is rejected.

Blank history, `-;` and `-  -;` mean no recorded history. A missing final
semicolon, a leading semicolon, `;;` and other empty entries, extra fields,
impossible dates, dates
in any other form (such as `May 1, 2020`) and wrongly cased status tokens
reject the entire input file before any notices are generated, even when a
notice omits history or its `ignore-agents` option excludes the agent. `Invalid`
is accepted as an upstream assessment. An omitted status leaves dose validity
unknown. Every bad fragment is recorded with its source row, column and
fragment number; correct the source
and start a new run. Warning acceptance cannot release rejected input.

### Vaccine names in history

Use the full source agent name for lookup in the selected project's
`config/vaccine_reference.json`, including spelling and case. The supplied
reference maps `HB-unspecified` to Hepatitis B. It displays as `HB*`, where the
asterisk marks an unspecified vaccine formulation. Displaying `*` does not
change the lookup key or establish that a name has a reference entry.

An agent absent from the reference stays in the source and prepared history.
A history table reports a `content.history_mapping` error unless its
`ignore-agents` option explicitly excludes that name. Correct the source name,
add an appropriate reference entry, or deliberately exclude the agent from the
table. See [history options](phu_templates.md#component-choices-and-findings)
for exclusions and how mapping errors affect delivery.

## Select notices

Select exactly one route for the whole CSV:

- `--notice-assignments PATH` reads a JSON manifest. Each client
  needs a `client_id` and a `template` filename such as
  `overdue_agents_v1.fr.typ`. The filename selects version and language
  within the complete template tree supplied with the required
  `--templates DIRECTORY` option.
- `--template PATH` selects one such `.typ` file for all
  clients. Its filename supplies the version and language. Known applicability
  conflicts warn without changing this explicit choice.

```bash
uv run immuknow students.csv \
  --notice-assignments /path/to/assignments.json \
  --templates /path/to/my-phu \
  --output /path/to/runs

uv run immuknow students.csv \
  --template /path/to/my-phu/overdue_diseases_v1.en.typ \
  --output /path/to/runs
```

An assignment file is a UTF-8 JSON array. IDs and template names are nonempty
strings, with exactly one unambiguous assignment per input client. Optional
experiment labels are strings carried into the report:

```json
[
  {"client_id": "1234567890", "template": "overdue_diseases_v1.en.typ"},
  {
    "client_id": "1234567891",
    "template": "overdue_agents_v1.fr.typ",
    "experiment_id": "wording-comparison",
    "experiment_arm": "B"
  }
]
```

Missing or ambiguous assignments cannot produce a trustworthy selected notice.
Extra assignments are reported and do not create clients. A readable custom
template without a registered applicability check can render with an
`assignment.check_unavailable` warning.

Both routes require `<version_id>.<language>.typ` with supported `en` or
`fr`. Manifest `template` values must be filenames, not paths; they resolve
inside the selected complete tree. The filename is the only declaration of
version and language; the compiler passes that identity to Typst. The packaged
`notice_versions.yaml` supplies named applicability checks. Use
`--config /path/to/config` for your own catalog and settings. With a
manifest, `--templates /path/to/my-phu` selects a complete external Typst
tree. It cannot be combined with `--template`, which supplies its
containing template tree. A conflicting source `version_id` records a warning;
it never chooses or replaces the selected notice.

The pipeline processes the whole CSV together; language does not filter
clients from later output checks. See [configuration](configuration.md)
for assignment and eligibility rules and [template authoring](phu_templates.md)
for the native JSON contract.

## Render progress and workers

The command shows rendering and encryption progress on standard error, followed
by delivery activity. Redirected output uses concise stage summaries. Use
`--no-progress` to suppress progress messages.

Rendering runs one notice at a time by default. To render multiple notices at
once, pass a positive worker count, for example `--workers 4`. Choose a count
that suits the available CPU and memory. Encryption and delivery run after
rendering and remain serial. The run log records stage durations to help assess
performance for your cohort. An interrupted run stops submitting notices, waits
for active work, and saves its results before releasing the run. Delivery does
not start after an interruption during rendering.

## Run output

Each invocation creates its own directory beneath `--output` and preserves
previous runs:

```text
runs/<run-id>/
  run.json        # authoritative source rows, findings and output results
  report.html     # readable report with links to actual PDFs
  report-*.html   # notice pages for runs larger than 1,000 rows
  originals/      # retained, unchanged compiled notices
  facts/          # saved notice payloads
  resources/      # source and template/configuration snapshots
  encrypted/      # optional individual encrypted copies
  bundles/        # one active delivery/ and review/ result
  logs/
  work/           # disposable compiler and assembly files
```

Open the printed `report.html` path to inspect every row, including failed and
incomplete rows. For more than 1,000 rows, follow its links to pages of 100
notices. The complete source values and run details are in `run.json`. During
rendering and encryption the JSON record is checkpointed after 1,000 outcomes
or periodically at the next outcome. The time interval starts at 30 seconds and
increases for slow snapshots; the HTML view is updated at workflow
boundaries. Progress counts incorporated outcomes, which may not yet be saved.
An abrupt stop can leave recent outcomes after the last checkpoint unrecorded;
PDFs created after it are not automatically adopted for delivery. Original source row keys remain stable when
notices are sorted. Input failures produce `rejected_input` and no notices,
encrypted copies or bundles. Shared configuration or file-reading failures
produce `failed_setup`. After input is accepted, template errors retain
independent clients' successful outputs; a run with individual failures is
`completed_with_failures`. Warnings alone return exit 0; failures return nonzero.

The report records actual original hashes and page counts, encryption outcomes,
and bundle membership and page ranges. Encryption does not delete originals.
Saved configuration omits encryption password settings. Cleanup can remove
`work/`, while originals, facts and report evidence remain. Diagnostics and
originals contain client information and should be handled as sensitive output.

For a callable workflow, `immuknow.orchestrator.run_pipeline` returns the saved
`run.json` path. Read its status to distinguish partial results from complete
success. The [workflow guide](../reference/architecture.md) defines run accounting.

## Review and release notices

Failed checks and unaccepted warnings keep a readable original in review.
Review copies have a findings sheet and a red REVIEW mark; delivery copies come
from unchanged originals. Inspect the original and the latest evaluation, then
accept individual warning tokens with a reason:

```bash
uv run immuknow-rebundle ./runs/<run-id> --accept-warning <token> --reason "Reviewed original"
```

The [PDF review guide](pdf_validation.md) owns warning acceptance, withholding
and invalidation rules. No choice can force delivery past failed checks.

Rebundling verifies the saved original hashes and does not reread source data or
authored templates, recompile notices, or rerun encryption. A failed attempt
keeps the previous active set. See [review and PDF findings](pdf_validation.md)
for override examples, page ranges and recovery behavior.
