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

Select exactly one route for the whole CSV:

- `--notice-assignments PATH` reads a JSON manifest. Each accepted client
  needs a `client_id` and a `template` filename such as
  `overdue_standard_v1.fr.typ`. The filename selects version and language
  within the packaged or selected complete template tree.
- `--notice-template PATH` selects one such `.typ` file for all accepted
  clients. Its filename supplies the version and language. The version must
  exist in the catalog and satisfy its eligibility rule for every client.

```bash
uv run immuknow students.csv \
  --notice-assignments /path/to/assignments.json \
  --output /path/to/notices

uv run immuknow students.csv \
  --notice-template /path/to/my-phu/legacy_overdue_v1.en.typ \
  --output /path/to/notices
```

Both routes require `<version_id>.<language>.typ` with supported `en` or
`fr`. Manifest `template` values must be filenames, not paths; they resolve
inside the selected complete tree. Typst also checks the literal version and
language in the derived JSON. The packaged `notice_versions.yaml` defines
eligible versions. Use
`--config /path/to/config` for your own catalog and settings. With a
manifest, `--templates /path/to/my-phu` selects a complete external Typst
tree, or `--template NAME` selects `phu_templates/NAME/` beneath the
working directory. Those directory choices cannot be combined with
`--notice-template`, which supplies its containing template tree. Each
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
