# 🩺 ImmuKnow
[![Run Pytest](https://github.com/WDGPH/ImmuKnow/actions/workflows/test.yml/badge.svg)](https://github.com/WDGPH/ImmuKnow/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/WDGPH/ImmuKnow/graph/badge.svg?token=J7BSABDO9M)](https://codecov.io/gh/WDGPH/ImmuKnow)
[![Docs](https://img.shields.io/badge/docs-wdgph.github.io%2FImmuKnow-blue)](https://wdgph.github.io/ImmuKnow/)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/WDGPH/ImmuKnow)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## Run a cohort

Install Python 3.10 or later, [uv](https://docs.astral.sh/uv/),
and Typst 0.15.1.
From a checkout:

```bash
uv sync
uv run immuknow ./input/students.csv --notice-assignments ./assignments.json \
  --output ./runs
```

A run selects notices in one of two ways: pass `--notice-assignments` with
one `template` filename per client, or pass one
`--template PATH` for the whole cohort:

```bash
uv run immuknow students.csv \
  --template immuknow/templates/overdue_diseases_v1.en.typ \
  --output ./runs
```

Every selected file must be named `<version_id>.<language>.typ`, with
`en` or `fr`. The notice catalog checks supplied facts for known versions;
it never chooses a notice or language. An installed package supplies the same command,
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
which reports that the child's immunizations are up to date. An English
`suspension_order_v1` example contains only the order. These examples are selected
explicitly in the manifest or with `--template`; they are never chosen
automatically when no diseases are due. Known applicability conflicts warn
while retaining the explicitly selected notice. No French affirmative or
suspension example ships. Settings checks the compiler-supplied filename
identity against the prepared facts. A conflicting source `version_id` warns;
the explicit selection remains authoritative.

Each run has its own directory beneath `--output`, with original PDFs,
optional individual encryption, bundles, saved facts/resources, `run.json`, and
a readable `report.html`. Every source row has an entry, including failed notices.
Recoverable source, assignment, and layout findings retain a PDF where possible;
independent notices continue after a failed render. Warnings return CLI exit 0;
failed entries or output steps return nonzero. See
[getting started](docs/user_guide/getting_started.md) for input and output
paths, [configuration](docs/user_guide/configuration.md) for options and
assignments, and [template authoring](docs/user_guide/phu_templates.md)
for the JSON contract.

## Author notices in Studio

ImmuKnow Studio provides Template, Settings and Theme editing with matching
prepared examples and retained findings. Download the complete Typst project
to preserve source, Settings, translations and images. Font files are optional. Use a separately
installed native engine for cohort processing. The
[Studio guide](docs/user_guide/studio.md) covers drafts, exports and the route to
native cohort processing. Native usage does not require Studio.

## Call from Python

```python
from pathlib import Path
from immuknow.orchestrator import run_pipeline

record_path = run_pipeline(
    Path("students.csv"),
    Path("runs"),
    notice_assignments=Path("assignments.json"),
)
```

`record_path` points to the authoritative `run.json`, including partial results.
Read its status and entries to assess the complete run. The
[architecture](docs/reference/architecture.md) explains the run and
its evidence.

## Development

The wheel contains the complete Typst project without font files. Native
compilation uses system fonts and saves the project resources it uses. A relocated custom project keeps its own Settings, translations,
assets and library. Python supplies normalized facts; display choices and
QR destinations belong in Typst Settings. Native use needs no Node, Rust, or browser.

```bash
uv sync --all-groups
uv run ty check
uv run pytest
uv run pre-commit run --all-files
```

Build the native wheel and source distribution with:

```bash
uv run python scripts/build-native.py --out-dir dist
```

Both this command and `uv build` generate `immuknow/build.json` inside the build
output. It records the native files, build tools and source revision without
changing source files. Native builds need no Studio, Node, Rust or Typst installation.
Typst is needed to generate notices.

The [testing guide](docs/developer_guide/testing.md) covers pinned Typst and
fonts, native checks, and visual review. Git history and releases record earlier
changes.
