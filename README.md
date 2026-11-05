# ImmuKnow

ImmuKnow prepares supplied immunization records and creates personalized notices with authored Typst templates. The upstream system assesses immunization status; ImmuKnow uses the notice selection you provide. Review your templates and the resulting PDFs before use.

Install Rust 1.92 or later and build the standalone executable:

```sh
cargo install --path . --locked
immuknow resources --output ./immuknow-resources
```

The binary embeds Typst 0.15.1 and uses fonts installed on the workstation. It needs no Python runtime or separate Typst executable. The exported resources include reference configuration, schemas and the shared Typst library. Supply a complete authored template project separately.

Run a cohort with one selected template:

```sh
immuknow run clients.csv --template ./project/templates/overdue_diseases_v1.en.typ \
  --config ./project/config --output ./runs
```

For per-client selections, use `--notice-assignments assignments.json --templates ./project/templates` in place of `--template`. Each run retains its inputs, prepared facts, original PDFs, findings and delivery bundles. Warnings are eligible for delivery by default; failed checks prevent delivery of the affected notice, whose readable original is placed in a review bundle. Check `run.json` and `report.html` after each run.

Integrations can use `immuknow prepare` with the same input and selection options to obtain versioned JSON facts without rendering. After reviewing a saved run, `immuknow rebundle ./runs/<run-id>` creates another delivery attempt; use its `--withhold` or `--release` options to manage holds.

See [getting started](docs/user_guide/getting_started.md), [configuration](docs/user_guide/configuration.md), [PDF review](docs/user_guide/pdf_validation.md), and the [command and facts reference](docs/reference/api.md). Template authors should also read the [Typst guide](docs/user_guide/phu_templates.md).
