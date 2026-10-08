# ImmuKnow

ImmuKnow turns Panorama/PEAR vaccination records into personalized immunization
notices and history charts. Python validates records, resolves each client's
notice assignment, and checks every expected output. Authored Typst templates
format the English or French PDFs. Built-in wording, branding, and contact
details are samples that a Public Health Unit must review before use.

## Run a cohort

Install Python 3.10 or later, [uv](https://docs.astral.sh/uv/), and Typst 0.15.1.
From a checkout:

```bash
uv sync
uv run immuknow students.csv --notice-assignments ./assignments.json \
  --input ./input --output ./output
```

A run selects notices in one of two ways: pass `--notice-assignments` with
one `template` filename per client, or pass one
`--notice-template PATH` for all accepted clients:

```bash
uv run immuknow students.csv \
  --notice-template immuknow/templates/legacy_overdue_v1.en.typ \
  --output ./output
```

Every selected file must be named `<version_id>.<language>.typ`, with
`en` or `fr`, and its version must be registered in the notice catalog for
eligibility checks. An installed
package supplies the same command, catalog, and resources. Use
`--config /path/to/config` to select your own configuration and catalog.

Each manifest `template` is a filename within the selected complete tree;
paths in manifest rows are rejected. The filename supplies canonical version
and language, and Typst independently asserts both. Use
`--templates /path/to/my-phu` for a complete PHU template directory, or
`--template NAME` for `phu_templates/NAME/` beneath the working directory.
The single-file option uses the selected file's containing tree and cannot be
combined with either directory option. No missing entry, helper, or asset falls
back to built-ins.

The maintained notices are legacy overdue (English/French), standard overdue
(English/French), and affirmative schedule (English). The legacy notice
displays overdue diseases; the standard overdue notice displays vaccine
agents. Eligibility uses overdue diseases in either case. No French
affirmative entry ships. Each Typst entry point declares and checks its own
version and language. An explicit source `version_id` must agree with the
selected notice.

The run writes individual PDFs, optional encrypted copies and bundles, and
run metadata beneath `--output`. The canonical cohort and render jobs identify
every expected notice. Compilation, validation, encryption, and bundling account
for that same set; a missing or invalid PDF fails the run. See
[getting started](docs/user_guide/getting_started.md) for input and output paths,
[configuration](docs/user_guide/configuration.md) for options and assignments,
and [template authoring](docs/user_guide/phu_templates.md) for the JSON contract.

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
[architecture](docs/reference/architecture.md) explains the run and its evidence.

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
