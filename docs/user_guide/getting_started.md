# Getting started

Install Python 3.10 or later, [uv](https://docs.astral.sh/uv/), and
[Typst 0.15.1](https://typst.app/docs/changelog/0.15.1/). Put `typst`
on `PATH`, set `TYPST_BIN`, or configure `typst.bin` in
`parameters.yaml`. From a checkout:

```bash
uv sync
uv run immuknow ./input/students.csv --notice-assignments ./assignments.json \
  --output ./output
```

An installed package provides `immuknow` and its resources without a checkout.

## Prepare input

Pass the path to one CSV extracted from Panorama/PEAR for the complete cohort.
Relative paths start from your working directory: `students.csv` reads a file
in that directory, while `./input/students.csv` reads it from the `input`
subdirectory. Absolute paths are also accepted. The packaged
[input schema](input_schema.md) defines the CSV fields:

| Schema rule | Fields |
|---|---|
| Required, nonblank | `school_name`, `client_id`, `first_name`, `last_name`, `date_of_birth`, `city`, `imms_given` |
| Optional | `street_address_line_1`, `street_address_line_2`, `province`, `postal_code`, `overdue_disease`, `overdue_agent`, `board_name`, `board_id`, `school_id`, `version_id` |

Absent optional columns are filled with empty strings. `client_id` must be a
10-digit string, and `date_of_birth` must be a valid `YYYY-MM-DD` date.
`version_id`, when supplied, must agree with the selected notice; it does not
select a notice.

The CSV is read as text, and surrounding whitespace is removed once before
validation. Blank cells stay blank; literal `NA`, `nan`, and `NULL` stay as
text. The selected schema validates these prepared values, and accepted dates
are formatted as `YYYY-MM-DD` for notices, QR codes, and passwords. A missing required
column or invalid required value, including a whitespace-only value, rejects
the whole file before address and client completeness checks. A blank street
address, province, or postal code passes the packaged schema. Mailing still
requires at least one street line, plus city, province, and postal code. Rows
without a complete address are excluded and written to
`incomplete_addresses.csv`. If a custom schema permits blank essential client
fields, those rows are excluded and written to `incomplete_clients.csv`.

## Select notices

Select exactly one route for the whole CSV:

- `--notice-assignments PATH` reads a JSON manifest. Each accepted client
  needs a `client_id` and a `template` filename such as
  `overdue_agents_v1.fr.typ`. The filename selects version and language
  within the packaged or selected complete template tree.
- `--template PATH` selects one such `.typ` file for all accepted
  clients. Its filename supplies the version and language. The version must
  exist in the catalog and satisfy its eligibility rule for every client.

```bash
uv run immuknow students.csv \
  --notice-assignments /path/to/assignments.json \
  --output /path/to/notices

uv run immuknow students.csv \
  --template /path/to/my-phu/overdue_diseases_v1.en.typ \
  --output /path/to/notices
```

Both routes require `<version_id>.<language>.typ` with supported `en` or
`fr`. Manifest `template` values must be filenames, not paths; they resolve
inside the selected complete tree. Typst also checks the literal version and
language in the derived JSON. The packaged `notice_versions.yaml` defines
eligible versions. Use
`--config /path/to/config` for your own catalog and settings. With a
manifest, `--templates /path/to/my-phu` selects a complete external Typst
tree. It cannot be combined with `--template`, which supplies its
containing template tree. Each
entry point declares its identity and language and checks the derived JSON.
An explicit source `version_id` must agree with the selected notice.

The pipeline processes the whole CSV together; language does not filter
clients from later output checks. See [configuration](configuration.md)
for assignment and eligibility rules and [template authoring](phu_templates.md)
for the native JSON contract.

## Run output

The complete run writes beneath `--output`:

```text
output/
  pdf_individual/  # one expected notice per accepted client
  pdf_combined/    # optional bundles
  artifacts/       # prepared clients, render jobs, staged inputs when retained
  metadata/        # validation and completion evidence
  logs/
```

The accepted cohort and render jobs determine the expected PDFs. Compilation
and validation must succeed for every notice before optional encryption and
bundling complete. The run rejects missing or stale outputs and never uses a
language filter to split the expected set. Diagnostics can contain client
identifiers and should be handled as sensitive run output.

For a callable workflow, use `immuknow.orchestrator.run_pipeline` as shown
in the [Python interface](../reference/api.md). The
[workflow diagram](../reference/architecture.md) explains output accounting.
