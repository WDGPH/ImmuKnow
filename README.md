# 🩺 ImmuKnow
[![Run Pytest](https://github.com/WDGPH/ImmuKnow/actions/workflows/test.yml/badge.svg)](https://github.com/WDGPH/ImmuKnow/actions/workflows/test.yml)
[![codecov](https://codecov.io/gh/WDGPH/ImmuKnow/graph/badge.svg?token=J7BSABDO9M)](https://codecov.io/gh/WDGPH/ImmuKnow)
[![Docs](https://img.shields.io/badge/docs-PHIZ-blue)](https://docs.phiz.ca/immuknow/)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/WDGPH/ImmuKnow)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## Run a cohort

Install Python 3.11 or later, [uv](https://docs.astral.sh/uv/),
and Typst 0.15.1.
Start with a project from [ImmuKnow Template](https://github.com/WDGPH/ImmuKnow-Template)
or a Studio project download. Core supplies the engine and shared library;
it includes no starter letters, Settings, example branding or project translations.
The commands below assume that project is in `./my-project`. From a Core checkout:

```bash
uv sync
uv run immuknow ./input/sample_students.csv \
  --notice-assignments ./input/sample_assignments.json \
  --templates ./my-project/templates --config ./my-project/config --output ./runs
```

`input/sample_students.csv` and `input/sample_assignments.json` contain
synthetic data for trying the pipeline; they describe no real clients.

A run selects notices in one of two ways: pass `--notice-assignments` with
one `template` filename per client, or pass one
`--template PATH` for the whole cohort:

```bash
uv run immuknow ./input/sample_students.csv \
  --template ./my-project/templates/overdue_diseases_v1.en.typ \
  --config ./my-project/config --output ./runs
```

Every selected file must be named `<version_id>.<language>.typ`, with
`en` or `fr`. In an assignments file, `template` is a filename, not a path.
`--notice-assignments` requires `--templates` to select a complete template project;
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
    template_dir=Path("my-project/templates"),
    config_dir=Path("my-project/config"),
)
```

`record_path` points to the authoritative `run.json`, including partial results.
Read its status and entries to assess the complete run. The
[architecture](docs/reference/architecture.md) explains the run and
its evidence.

## Development

The wheel contains the shared Typst library under `typst/`, schemas, reference
configuration and internal review layouts. Starter projects live in Template.
Core tests use small unbranded fixtures outside the distribution. Native
compilation uses system fonts and saves the project resources it uses. A relocated custom project keeps its own Settings, translations,
assets and library. Python supplies normalized facts; display choices and
QR destinations belong in the supplied project’s Typst files. Native use needs no Node, Rust, or browser.

```bash
uv sync --all-groups
uv run ty check
uv run pytest
uv run --locked prek install
uv run --locked prek run --all-files
```

Install hooks once per clone. They lint and format Python with Ruff; CI checks
the same rules without rewriting files. The hooks run the Ruff version
locked by the project.

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
