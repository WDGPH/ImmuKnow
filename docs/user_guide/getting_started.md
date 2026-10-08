# Getting Started

## Prerequisites

Before running the pipeline you need:

- **Python ≥ 3.10** — managed automatically by `uv`
- **[uv](https://github.com/astral-sh/uv)** — Python package and project manager
- **[Typst v0.15.1](https://typst.app/docs/changelog/0.15.1/)** — PDF typesetting engine (must be on `PATH`, configured via `typst.bin` in `parameters.yaml`, or selected with `TYPST_BIN`)

## Installation

```bash
git clone https://github.com/WDGPH/ImmuKnow.git
cd ImmuKnow
uv sync
```

To also install development tools (pre-commit, pytest, etc.):

```bash
uv sync --group dev
uv run pre-commit install
```

## Preparing input data

Input files must be `.xlsx` format with a single worksheet, extracted from [Panorama PEAR](https://accessonehealth.ca/).

The pipeline enforces a strict column schema — column names must match exactly (no fuzzy matching). The following columns are **required**:

| Column name | Notes |
|---|---|
| `school_name` | |
| `client_id` | 10-digit numeric string |
| `first_name` | |
| `last_name` | |
| `date_of_birth` | ISO 8601 date (`YYYY-MM-DD`) |
| `street_address_line_1` | |
| `street_address_line_2` | May be blank |
| `city` | |
| `province` | |
| `postal_code` | |
| `overdue_disease` | May be blank |
| `overdue_agent` | May be blank |
| `imms_given` | May be blank |

The following columns are **optional** and will be used when present:

| Column name |
|---|
| `board_name` |
| `board_id` |
| `school_id` |
| `version_id` |

The full schema is defined in `config/input_schema.json`. If the file is missing any required column, the pipeline will stop immediately with a clear error message listing the missing columns.

Place input files in the `input/` subdirectory (not tracked by Git):

```
ImmuKnow/
└── input/
    └── students.xlsx
```

## Running the pipeline

```bash
uv run viper <input_file> <language> [options]
```

**Positional arguments:**

| Argument | Description |
|----------|-------------|
| `<input_file>` | Excel path, or a filename within `--input` |
| `<language>` | `en` or `fr`; required in fixed mode, optional with manifest assignments |

**Common options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--input PATH` | `./input` | Input directory |
| `--output PATH` | `./output` | Output directory |
| `--config PATH` | Packaged config | Configuration directory |
| `--templates PATH` | Built-in templates | External PHU template directory |
| `--notice-assignments PATH` | None | Assignment manifest; selects manifest mode |
| `--template NAME` | Built-in `templates/` | PHU template name within `phu_templates/` |

**Examples:**

```bash
# Basic English run
uv run viper students.xlsx en

# French run with custom output directory
uv run viper students.xlsx fr --output /tmp/output

# Use a PHU-specific template
uv run viper students.xlsx en --template wdgph
```

## Output

All outputs are written to `output/` (or the path given by `--output`):

```
output/
├── pdf_individual/      # One PDF per client
├── pdf_combined/        # Bundled PDFs (if bundling is enabled)
├── artifacts/           # Render jobs, JSON, unchanged templates and QR codes
├── metadata/            # Validation reports and run metadata
└── logs/                # Per-run log files
```

## Next steps

- [Configuration Reference](configuration.md) — feature flags, QR codes, encryption, validation rules
- [PHU Templates](phu_templates.md) — creating organization-specific layouts
- [Architecture](../reference/architecture.md) — how the pipeline steps fit together
