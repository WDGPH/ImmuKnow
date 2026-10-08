# Getting started

Install Python 3.10 or later, [uv](https://docs.astral.sh/uv/), and
[Typst 0.15.1](https://typst.app/docs/changelog/0.15.1/). Put `typst`
on `PATH`, set `TYPST_BIN`, or configure `typst.bin` in
`parameters.yaml`. From a checkout:

```bash
uv sync
uv run viper students.xlsx en --input ./input --output ./output
```

An installed package provides `viper` and its resources without a checkout.

## Prepare input

Input is one Excel worksheet (`.xlsx` or `.xls`) or a CSV extracted from
Panorama/PEAR. Column names must match the packaged
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

Fixed mode uses the legacy overdue notice and requires a positional language:

```bash
uv run viper students.xlsx fr --output /path/to/notices
```

To assign versions and languages per client, supply a JSON manifest and a
configuration directory with `notice_versions.yaml`:

```bash
uv run viper students.xlsx \
  --notice-assignments /path/to/assignments.json \
  --config /path/to/config --output /path/to/notices
```

The manifest uses `client_id` and `version_id`; optional `language` uses
the catalog default. An explicit source `version_id` must agree. The
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
