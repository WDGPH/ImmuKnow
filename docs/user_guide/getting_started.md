# Getting started

Install Python 3.10 or later, [uv](https://docs.astral.sh/uv/), and
[Typst 0.15.1](https://typst.app/docs/changelog/0.15.1/). Put `typst`
on `PATH`, set `TYPST_BIN`, or configure `typst.bin` in
`parameters.yaml`. From a checkout:

```bash
uv sync
uv run immuknow students.csv --notice-assignments ./assignments.json \
  --input ./input --output ./output
```

An installed package provides `immuknow` and its resources without a checkout.

## Prepare input

Use one CSV extracted from Panorama/PEAR for the complete cohort. Column names
must match the packaged
[input schema](input_schema.md). Required columns are:

| Client and location | Assessment and history |
|---|---|
| `school_name`, `client_id`, `first_name`, `last_name`, `date_of_birth` | `overdue_disease`, `overdue_agent`, `imms_given` |
| `street_address_line_1`, `street_address_line_2`, `city`, `province`, `postal_code` | |

`client_id` is a 10-digit string and `date_of_birth` is a valid
`YYYY-MM-DD` date. The second street line, overdue fields, and history may
be blank. Optional columns are `board_name`, `board_id`, `school_id`,
and `version_id`. Missing required columns fail before notices are produced.

## Select notices

Assign versions and languages per client with a JSON manifest. The packaged
configuration includes `notice_versions.yaml`; use `--config` for your own
catalog and settings:

```bash
uv run immuknow students.csv \
  --notice-assignments /path/to/assignments.json \
  --config /path/to/config --output /path/to/notices
```

The manifest uses `client_id` and `version_id`; optional `language` uses
the catalog default. Together, version and language select an authored `.typ`
entry point. That file declares the document language and checks that the
assignment matches. Do not split the CSV or pass a positional language for
this workflow. An explicit source `version_id` must agree. The
[configuration guide](configuration.md) defines defaults, eligibility,
reconciliation, QR/password fields, and validation rules. Use
`--templates /path/to/my-phu` for a complete external Typst tree, or
`--template NAME` for `phu_templates/NAME/` beneath the working directory.
The [authoring guide](phu_templates.md) describes the JSON and entry points.

## Run output

The complete run writes beneath `--output`:

```text
output/
  pdf_individual/  # one expected notice per accepted client
  pdf_combined/    # optional bundles
  artifacts/       # canonical cohort, render jobs, staged inputs when retained
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
