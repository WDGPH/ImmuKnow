# Getting Started

## Prerequisites

Before running the pipeline you need:

- **Python ≥ 3.10** — managed automatically by `uv`
- **[uv](https://github.com/astral-sh/uv)** — Python package and project manager
- **[Typst v0.14.2](https://typst.app)** — PDF typesetting engine (must be on `PATH` or configured via `typst.bin` in `parameters.yaml`)

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
| `School Type` | |
| `School Name` | |
| `Client Id` | 10-digit numeric string |
| `First Name` | |
| `Last Name` | |
| `Age` | Integer |
| `Date of Birth` | ISO 8601 date (`YYYY-MM-DD`) |
| `Street Address Line 1` | |
| `Street Address Line 2` | May be blank |
| `City` | |
| `Province/Territory` | |
| `Postal Code` | |
| `Overdue Disease` | May be blank |
| `Overdue Agent` | May be blank |
| `Imms Given` | May be blank |
| `Birth Year` | |

The following columns are **optional** and will be used when present:

| Column name |
|---|
| `Board Name` |
| `Board Id` |
| `School Id` |
| `Unique Id` |

The full schema is defined in `config/input_schema.yaml`. If the file is missing any required column, the pipeline will stop immediately with a clear error message listing the missing columns.

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

**Required arguments:**

| Argument | Description |
|----------|-------------|
| `<input_file>` | Name of the Excel file in `input/` (e.g., `students.xlsx`) |
| `<language>` | Language code: `en` (English) or `fr` (French) |

**Common options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--input PATH` | `../input` | Input directory |
| `--output PATH` | `../output` | Output directory |
| `--config PATH` | `../config` | Configuration directory |
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
├── artifacts/           # Intermediate files (QR codes, Typst sources)
├── metadata/            # Validation reports and run metadata
└── logs/                # Per-run log files
```

## Next steps

- [Configuration Reference](configuration.md) — feature flags, QR codes, encryption, validation rules
- [PHU Templates](phu_templates.md) — creating organization-specific layouts
- [Architecture](../reference/architecture.md) — how the pipeline steps fit together
