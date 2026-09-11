# 🩺 ImmuKnow

**Current version:** v1.0.0  

## 📘 Introduction

This project provides a Python and Bash-based workflow for generating **personalized immunization history charts** and **notice letters** for children overdue for mandated vaccinations under the **Child Care and Early Years Act (CCEYA)** and ISPA.

Reports are generated in PDF format using [Typst](https://typst.app) and a custom report template.

## ⚙️ Environment Setup

- Written in **Bash** and **Python**
- Uses [Typst](https://typst.app) for typesetting
- Python dependencies managed via `pyproject.toml` and [uv](https://github.com/astral-sh/uv)

### Virtual Environment

Install all dependencies (and create the `.venv` if it doesn't yet exist) before doing anything else:

```bash
uv sync
source .venv/bin/activate
```

> ℹ️ `uv sync` only installs the core runtime packages by default. If you're planning to run tests or other dev tools, include the development group once via `uv sync --group dev` (or `uv sync --all-groups` if you prefer everything).

### Code Quality & Pre-commit Hooks

To enable automatic code linting and formatting on every commit, initialize pre-commit hooks:

```bash
uv sync --group dev                 # Install development tools (pre-commit, pytest, etc.)
uv run pre-commit install           # Initialize git hooks
```

Now, whenever you commit changes, the pre-commit hook automatically:
- **Lints** your code with `ruff check --fix` (auto-fixes issues when possible)
- **Formats** your code with `ruff format` (enforces consistent style)

If any check fails, your commit is blocked until you fix the issues. You can also run checks manually anytime:

```bash
uv run pre-commit run --all-files   # Check all files
```

## 🛠️ Pipeline Overview & Architecture

This section describes how the pipeline orchestrates data flow and manages state across processing steps.

### Module Organization

The `pipeline/` package is organized by pipeline function, not by layer. Each step has its own module:

| Step | Module | Purpose |
|------|--------|---------|
| 1 | `prepare_output.py` | Output directory setup |
| 2 | `preprocess.py` | Data validation & normalization → JSON artifact |
| 3 | `generate_qr_codes.py` | QR code PNG generation (optional) |
| 4 | `generate_notices.py` | Typst template rendering |
| 5 | `compile_notices.py` | Typst → PDF compilation |
| 6 | `validate_pdfs.py` | PDF validation (rules, summary, JSON report) |
| 7 | `encrypt_notice.py` | PDF encryption (optional) |
| 8 | `bundle_pdfs.py` | PDF bundling & grouping (optional) |
| 9 | `cleanup.py` | Intermediate file cleanup |

**Supporting modules:** `orchestrator.py` (orchestrator), `config_loader.py`, `data_models.py`, `enums.py`, `utils.py`, `notice_versioning.py`, `assignment_manifest.py`. 

**Template modules** (in `templates/` package): `en_template.py`, `fr_template.py` (Typst template rendering). For module structure questions, see `docs/CODE_ANALYSIS_STANDARDS.md`.

### Orchestration Model

The pipeline follows a **sequential, stateless step architecture** where each processing step:

1. **Reads fresh input** from disk (either Excel files or the preprocessed JSON artifact)
2. **Processes data** independently without holding state between steps
3. **Writes output** to disk for the next step to discover
4. **Never passes in-memory objects** between steps via the orchestrator

This design ensures:
- **Modularity**: Steps can be understood, tested, and modified in isolation
- **Resilience**: Each step can be re-run independently if needed (e.g., if Step 4 fails, fix the code and re-run Steps 4-9 without reprocessing)
- **Simplicity**: No complex data structures passed between components
- **Reproducibility**: Same input always produces same output across runs

### Data Management

The pipeline produces a single **normalized JSON artifact** (`preprocessed_clients_<run_id>.json`) during preprocessing. This artifact serves as the canonical source of truth:

- **Created by:** `preprocess.py` (Step 2) - contains sorted clients with normalized metadata
- **Consumed by:** `generate_qr_codes.py` (Step 3), `generate_notices.py` (Step 4), and `bundle_pdfs.py` (Step 8)
- **Format:** Single JSON file with run metadata, total client count, warnings, and per-client details

Client data flows through specialized handlers during generation:

| Stage | Input | Processing | Output |
|-------|-------|-----------|--------|
| **Preprocessing** | Excel file | Data normalization, sorting, age calculation | `preprocessed_clients_<run_id>.json` |
| **QR Generation** | Preprocessed JSON | Payload formatting → PNG generation | PNG images in `artifacts/qr_codes/` |
| **Typst Template** | Preprocessed JSON | Template rendering with QR reference | `.typ` files in `artifacts/typst/` |
| **PDF Compilation** | Filesystem glob of `.typ` files | Typst subprocess | PDF files in `pdf_individual/` |
| **PDF Bundling** | In-memory `ClientArtifact` objects | Grouping and manifest generation | Bundle PDFs in `pdf_combined/` |

Each step reads the JSON fresh when needed—there is no shared in-memory state passed between steps through the orchestrator.

### Client Ordering

Clients are deterministically ordered during preprocessing by: **school name → last name → first name → client ID**, ensuring consistent, reproducible output across pipeline runs. Each client receives a deterministic sequence number (`00001`, `00002`, etc.) that persists through all downstream operations.

## 🚦 Pipeline Steps

The main pipeline orchestrator (`orchestrator.py`) automates the end-to-end workflow for generating immunization notices and charts. Below are the nine sequential steps:

1. **Output Preparation** (`prepare_output.py`)  
   Prepares the output directory, optionally removing existing contents while preserving logs.

2. **Preprocessing** (`preprocess.py`)  
   Cleans, validates, and structures input data into a normalized JSON artifact (`preprocessed_clients_<run_id>.json`). Optionally validates school/daycare names against the PHIX reference mapping (see [PHIX School Validation](./config/README.md#phix-school-validation)). In manifest mode, also reconciles the assignment manifest against the client list and runs a preflight gate before any PDF is generated.

3. **Generating QR Codes** (`generate_qr_codes.py`, optional)  
   Generates QR code PNG files from templated payloads. Skipped if `qr.enabled: false` in `parameters.yaml`.

4. **Generating Notices** (`generate_notices.py`)  
   Renders Typst templates (`.typ` files) for each client from the preprocessed artifact, with QR code references. In manifest mode, dispatches each client to the template specified by their assigned notice version and language.

5. **Compiling Notices** (`compile_notices.py`)  
   Compiles Typst templates into individual PDF notices using the `typst` command-line tool.

6. **Validating PDFs** (`validate_pdfs.py`)  
   Runs rule-based PDF validation and prints a summary. Writes a JSON report to `output/metadata/<lang>_validation_<run_id>.json`. Rules and severities are configured in `config/parameters.yaml` (see config README). Default rules include:
   - `exactly_two_pages` (ensure each notice is 2 pages)
   - `signature_overflow` (detect signature block on page 2 using invisible markers)
   Severity levels: `disabled`, `warn`, `error` (error halts the pipeline).

7. **Encrypting PDFs** (`encrypt_notice.py`, optional)  
   When `encryption.enabled: true`, encrypts individual PDFs using client metadata as password.

8. **Bundling PDFs** (`bundle_pdfs.py`, optional)  
   When `bundling.bundle_size > 0`, combines individual PDFs into bundles with optional grouping by school or board. Runs independently of encryption.

9. **Cleanup** (`cleanup.py`)  
   Removes intermediate files (.typ, .json, per-client PDFs) if `pipeline.keep_intermediate_files: false`. Optionally deletes unencrypted PDFs if `cleanup.delete_unencrypted_pdfs: true`.

**Usage Example:**
```bash
uv run viper <input_file> [language] [--output PATH]
```

**Required Arguments:**
- `<input_file>`: Name of the input file (e.g., `students.xlsx`)
- `[language]`: Language code (`en` or `fr`). Required in fixed mode; omit when using `--notice-assignments`.

**Optional Arguments:**
- `--input PATH`: Input directory (default: ../input)
- `--output PATH`: Output directory (default: ../output)
- `--config PATH`: Configuration directory (default: ../config)
- `--template NAME`: PHU template name within `phu_templates/` (e.g., `wdgph`); defaults to built-in `templates/` when omitted
- `--notice-assignments PATH`: JSON file mapping client IDs to notice versions (enables manifest mode; requires `config/notice_versions.yaml`)

**Configuration:**
See the complete configuration reference and examples in `config/README.md`:
- Configuration overview and feature flags
- QR Code settings (payload templating)
- PDF Validation settings (rule-based quality checks)
- PDF encryption settings (password templating)
- Disease/chart/translation files
- Notice versioning catalog and assignment manifest

Direct link: [Configuration Reference](./config/README.md)

**Examples:**
```bash
# Basic usage (fixed mode — all clients get the same language and template)
uv run viper students.xlsx en

# Override output directory
uv run viper students.xlsx en --output /tmp/output

# Use a PHU-specific template (from phu_templates/my_phu/)
uv run viper students.xlsx en --template my_phu

# Manifest mode — per-client notice version and language from assignment file
uv run viper students.xlsx --notice-assignments assignments.json --template my_phu
```

### Using PHU-Specific Templates

Public Health Units can create custom template directories for organization-specific branding and layouts. All PHU templates live under the `phu_templates/` directory and are gitignored by default.

```bash
# Create your PHU template directory by copying defaults
cp -r templates/ phu_templates/my_phu/

# Customize templates and assets as needed, then run with your PHU template
uv run viper students.xlsx en --template my_phu
```

The `--template` argument expects a template name within `phu_templates/` (flat names only; no `/` or `\`). For example, `--template my_phu` loads from `phu_templates/my_phu/`.

Each PHU template directory should contain:
- `conf.typ` - Typst configuration and helper functions (required)
- `{lang}_template.py` - Language modules with `render_notice()` for the languages you intend to generate (e.g., `en_template.py` for English, `fr_template.py` for French). Single-language templates are supported.
- `assets/` - Optional directory for images like logos or signatures if your templates reference them

Templates are loaded dynamically at runtime, enabling different organizations to maintain separate template sets without modifying core code. By default (when `--template` is not specified), the pipeline uses the built-in `templates/` directory. It's recommended to start by copying from `templates/` into `phu_templates/<your_name>/` and customizing from there.

> ℹ️ **Typst preview note:** The WDGPH code-server development environments render Typst files via Tinymist. The shared template at `templates/conf.typ` only defines helper functions, colour tokens, and table layouts that the generated notice `.typ` files import; it doesn't emit any pages on its own, so Tinymist has nothing to preview if attempted on this file. To examine the actual markup that uses these helpers, run the pipeline with `pipeline.keep_intermediate_files: true` in `config/parameters.yaml` so the generated notice `.typ` files stay in `output/artifacts/` for manual inspection.

**Outputs:**
- Processed notices and charts in the `output/` directory
- Log and summary information in the terminal

## 🧪 Running Tests

The test suite is organized in three layers (see `docs/TESTING_STANDARDS.md` for details):

**Quick checks (unit tests, <100ms each):**
```bash
uv run pytest -m unit
```

**Integration tests (step interactions, 100ms–1s each):**
```bash
uv run pytest -m integration
```

**End-to-end tests (full pipeline, 1s–30s each):**
```bash
uv run pytest -m e2e
```

**All tests:**
```bash
uv run pytest
```

**With coverage report:**
```bash
uv run pytest --cov=pipeline --cov-report=html
```

View coverage in `htmlcov/index.html`.

**For CI/local development (skip slow E2E tests):**
```bash
uv run pytest -m "not e2e"
```

> ✅ Before running tests, make sure you've installed the `dev` group at least once (`uv sync --group dev`) so that testing dependencies are available.


## 📂 Input Data

- Use data extracts from [Panorama PEAR](https://accessonehealth.ca/)
- Place input files in the `input/` subfolder (not tracked by Git)
- Files must be `.xlsx` format with a **single worksheet** per file
  - Column names must match the required schema exactly - see [Getting Started](docs/user_guide/getting_started.md#preparing-input-data) for the full column list

## Preprocessing

The `preprocess.py` (Step 2) module reads raw input data and produces a normalized JSON artifact.

### Processing Workflow

- **Input:** Excel file with raw client vaccination records
- **Processing:**
  - Validates school/daycare names against `config/phix_mapping.json` for specified PHU (when `phix_validation.enabled: true`)
  - Validates schema (required columns, data types)
  - Cleans and transforms client data (dates, addresses, vaccine history)
  - Determines over/under 16 years old for recipient determination (uses `date_notice_delivery` from `parameters.yaml`)
  - Assigns deterministic per-client sequence numbers sorted by: school → last name → first name → client ID
  - Maps vaccine history against disease reference data
  - Synthesizes stable school/board identifiers when missing
- **Output:** Single JSON artifact at `output/artifacts/preprocessed_clients_<run_id>.json`

Logging is written to `output/logs/preprocess_<run_id>.log` for traceability.

### Artifact Structure

The preprocessed artifact contains:

```json
{
  "run_id": "20251023T200355",
  "language": "en",
  "total_clients": 5,
  "warnings": [],
  "clients": [
    {
      "sequence": "00001",
      "client_id": "1009876545",
      "language": "en",
      "person": {
        "first_name": "...", "last_name": "...",
        "date_of_birth": "...", "date_of_birth_display": "...", "date_of_birth_iso": "...",
        "age": "...", "over_16": true
      },
      "school": {"name": "...", "id": "..."},
      "board": {"name": "...", "id": "..."},
      "contact": {"street": "...", "city": "...", "province": "...", "postal_code": "..."},
      "vaccines_due": "...",
      "vaccines_due_list": ["..."],
      "received": [...],
      "metadata": {"version_id": null}
    },
    ...
  ]
}
```

In manifest mode, `assignment_mode` is `"manifest"`, `default_version` holds the catalog default version ID, and each client's `metadata` includes a `resolved_notice` object:

```json
{
  "run_id": "20251023T200355",
  "language": "en",
  "assignment_mode": "manifest",
  "default_version": "overdue_standard_v1",
  "total_clients": 5,
  "clients": [
    {
      "sequence": "00001",
      "client_id": "1009876545",
      "language": "fr",
      "metadata": {
        "recipient": "...",
        "over_16": false,
        "resolved_notice": {
          "notice_version": "overdue_standard_v1",
          "notice_kind": "overdue",
          "language": "fr",
          "experiment_id": null,
          "experiment_arm": null,
          "assignment_source": "manifest"
        }
      }
    }
  ]
}
```

## Configuration quick links

- PHIX school validation: see [PHIX School Validation](./config/README.md#phix-school-validation)
- QR Code settings: see [QR Code Configuration](./config/README.md#qr-code-configuration)
- PDF Encryption settings: see [PDF Encryption Configuration](./config/README.md#pdf-encryption-configuration)
- Notice versioning catalog: see [Notice Versioning](./config/README.md#notice-versioning)
## Changelog

See [CHANGELOG.md](./CHANGELOG.md) for details of each release.
