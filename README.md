# 🩺 ImmuKnow
[![Run Pytest](https://github.com/WDGPH/ImmuKnow/actions/workflows/test.yml/badge.svg)](https://github.com/WDGPH/ImmuKnow/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/WDGPH/ImmuKnow/graph/badge.svg?token=J7BSABDO9M)](https://codecov.io/gh/WDGPH/ImmuKnow)
[![Docs](https://img.shields.io/badge/docs-PHIZ-blue)](https://docs.phiz.ca/immuknow/)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/WDGPH/ImmuKnow)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## Run a cohort

Install Python 3.11 or later, [uv](https://docs.astral.sh/uv/),
and Typst 0.15.1.
From a checkout:

```bash
uv sync
uv run immuknow ./input/sample_students.csv \
  --notice-assignments ./input/sample_assignments.json --output ./runs
```

`input/sample_students.csv` and `input/sample_assignments.json` contain
synthetic data for trying the pipeline; they describe no real clients.

A run selects notices in one of two ways: pass `--notice-assignments` with
one `template` filename per client, or pass one
`--template PATH` for the whole cohort:

```bash
uv run immuknow ./input/sample_students.csv \
  --template immuknow/templates/overdue_diseases_v1.en.typ \
  --output ./runs
```

Every selected file must be named `<version_id>.<language>.typ`, with
`en` or `fr`. In an assignments file, `template` is a filename, not a path.
Use `--templates` to select a complete custom template directory for assignments;
`--template` uses the selected file's directory. An installed package supplies
the same command and resources. See [selecting notices](docs/user_guide/getting_started.md#select-notices)
for the catalog, custom directories and selection rules.

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

ImmuKnow Studio lets you edit and preview notices in your browser using
fictional examples. Its project download includes your selected notice,
configuration, fonts and licences, plus local setup and helper scripts from
[ImmuKnow-Template](https://github.com/WDGPH/ImmuKnow-Template). Install the
fonts for native use and run the project with Core on your workstation. The
[Studio overview](docs/user_guide/studio.md) explains the handoff.

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
