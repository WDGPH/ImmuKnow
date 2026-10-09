# ImmuKnow

ImmuKnow turns Panorama/PEAR vaccination records into personalized immunization
notices and history charts. Python validates records, resolves each client's
notice assignment, and checks every expected output. Authored Typst templates
format the English or French PDFs. Built-in wording, branding, and contact
details are samples that a Public Health Unit must review before use.

## Run a cohort

Install Python 3.10 or later, [uv](https://docs.astral.sh/uv/),
and Typst 0.15.1.
From a checkout:

```bash
uv sync
uv run immuknow ./input/students.csv --notice-assignments ./assignments.json \
  --output ./output
```

A run selects notices in one of two ways: pass `--notice-assignments` with
one `template` filename per client, or pass one
`--template PATH` for all accepted clients:

```bash
uv run immuknow students.csv \
  --template immuknow/templates/overdue_diseases_v1.en.typ \
  --output ./output
```

Every selected file must be named `<version_id>.<language>.typ`, with
`en` or `fr`, and its version must be registered in the notice catalog for
eligibility checks. An installed package supplies the same command,
catalog, and resources. Use
`--config /path/to/config` to select your own configuration and catalog.

Each manifest `template` is a filename within the selected complete tree;
paths in manifest rows are rejected. The filename supplies the selected version
and language, and Typst independently asserts both. Use
`--templates /path/to/my-phu` to select a complete PHU template directory
for manifest rows. The single-file option uses its file's containing tree
and cannot be combined with `--templates`. Missing entry points, helpers,
and assets do not fall back to built-ins.

The maintained examples are `overdue_diseases_v1` (English/French),
which displays overdue diseases; `overdue_agents_v1` (English/French),
which displays vaccine agents; and `affirmative_schedule_v1` (English),
which reports that the child's immunizations are up to date. Both overdue
examples use the overdue disease list for eligibility. The affirmative
example is selected
explicitly in the manifest or with `--template`; it is never chosen
automatically when no diseases are due. Its catalog `no_overdue` rule
requires an empty `overdue_diseases` list from the source assessment.
An ineligible assignment fails preflight. No French affirmative example ships.
Each Typst entry point declares and checks its version and language. An
explicit source `version_id` must agree with the selected notice.

The run writes individual PDFs, optional encrypted copies and bundles, and
run metadata beneath `--output`. The prepared client list and render jobs
identify
every expected notice. Compilation, validation, encryption, and bundling account
for that same set; a missing or invalid PDF fails the run. See
[getting started](docs/user_guide/getting_started.md) for input and output
paths, [configuration](docs/user_guide/configuration.md) for options and
assignments, and [template authoring](docs/user_guide/phu_templates.md)
for the JSON contract.

## Call from Python

```python
from pathlib import Path
from immuknow.orchestrator import run_pipeline

completion = run_pipeline(
    Path("students.csv"),
    Path("notices"),
    notice_assignments=Path("assignments.json"),
)
```

`completion` is the successful run's completion record, or `None` when the
user cancels an output-directory prompt. The
[architecture](docs/reference/architecture.md) explains the run and
its evidence.

## Development

```bash
uv sync --all-groups
uv run ty check
uv run pytest
uv run pre-commit run --all-files
```

The [testing guide](docs/developer_guide/testing.md) covers pinned Typst and
fonts, native checks, and visual review. Git history and releases record earlier
changes.
