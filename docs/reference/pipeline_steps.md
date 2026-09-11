# Pipeline Steps Reference

Detailed reference for each of the nine pipeline steps. For an overview and flow diagram, see [Architecture](architecture.md). For configuration keys, see the [Configuration Reference](../user_guide/configuration.md).

---

## Step 1 — Output Preparation

**Module:** `pipeline/prepare_output.py`

Prepares the output directory before the pipeline run begins. This step runs before any data is processed.

**Configuration keys read:**

| Key | Type | Description |
|-----|------|-------------|
| `pipeline.before_run.clear_output_directory` | bool | When `true`, removes all output except logs |

**Behavior:**

- If the output directory does not exist, creates it and the logs subdirectory.
- If `clear_output_directory: true`, removes all contents of `output/` except `output/logs/` (logs are always preserved for audit trail).
- If `clear_output_directory: false`, prompts the user interactively before deleting.
- Returns `False` (cancels the pipeline) if the user declines the prompt.

**Output:** Clean `output/` directory with `output/logs/` ready for writing.

---

## Step 2 — Preprocessing

**Module:** `pipeline/preprocess.py`

Reads the raw Excel input, validates the schema, normalizes all client and vaccination data, and writes a single canonical JSON artifact.

**Configuration keys read:**

| Key | Type | Description |
|-----|------|-------------|
| `chart_diseases_header` | list | Diseases to include as chart columns; others collapse to "Other" |
| `preprocess.include_dose` | bool | Include dose numbers in overdue vaccine lists (default: `false`) |
| `preprocess.show_validity_markers` | bool | Render validity markers in the immunization chart (default: `false`) |
| `phix_validation.enabled` | bool | Validate school names against PHIX reference mapping (default: `true`) |
| `phix_validation.target_phu` | str | Exact PHU name as it appears in `phix_mapping.json` |
| `phix_validation.unmatched_behavior` | str | Action on unmatched schools: `warn`, `error`, or `skip` |
| `date_notice_delivery` | ISO 8601 | Reference date for age-based eligibility (16+ threshold) |
| `date_data_cutoff` | ISO 8601 | Date the source data was extracted from Panorama |
| `notice_versioning.allow_unassigned` | bool | When `true`, clients absent from the manifest receive catalog defaults (manifest mode only) |
| `notice_versioning.extra_manifest_rows` | str | How to treat manifest rows with no matching client: `"error"` or `"warn"` (manifest mode only) |

**Inputs:**

- Excel file from `input/` (single worksheet, `.xlsx`)
- `config/vaccine_reference.json` — maps vaccine codes to disease names
- `config/disease_normalization.json` — normalizes raw disease name variants
- `config/phix_mapping.json` — PHU-keyed school name → PHIX facility ID mapping (when PHIX validation enabled)
- `config/notice_versions.yaml` — notice version catalog (manifest mode only; feature is off when absent)
- Assignment manifest JSON (`--notice-assignments`) — per-client version and language assignments (manifest mode only)

**Outputs:**

- `output/artifacts/preprocessed_clients_<run_id>.json` — canonical client artifact
- `output/logs/preprocess_<run_id>.log` — processing log
- `output/incomplete_addresses.csv` — records dropped due to missing address fields (written when any are found)
- `output/incomplete_clients.csv` — records with missing required client fields, retained in processing (written when any are found)
- `phix_exact.csv`, `phix_inexact.csv`, `phix_no_match.csv` — school match audit CSVs (when PHIX validation enabled)
- `output/metadata/notice_assignments_<run_id>.json` — per-client assignment record, no PII (manifest mode only)

**Processing:**

1. Validates school/daycare names against `phix_mapping.json` for the configured PHU (when `phix_validation.enabled: true`)
2. Reads and validates Excel schema (required columns, data types)
3. Normalizes disease names using `disease_normalization.json`
4. Expands vaccine codes to disease names using `vaccine_reference.json`
5. Filters diseases against `chart_diseases_header`; collapses unlisted diseases to "Other"
6. Computes client ages relative to `date_notice_delivery` (determines parent vs. student addressing)
7. Checks address completeness: records missing `address`, `city`, `province`, or `postal_code` are logged, written to `output/incomplete_addresses.csv`, and **dropped** by default from further processing
8. Checks client information completeness: records missing `first_name`, `last_name`, `date_of_birth`, `client_id`, `school_name`, `overdue_disease`, or `imms_given` are logged and written to `output/incomplete_clients.csv`, and **dropped** by default from further processing
9. Sorts clients deterministically: school → last name → first name → client ID
10. Assigns stable sequence numbers (`00001`, `00002`, …)
11. Synthesizes missing school/board identifiers where needed
12. Writes the canonical JSON artifact
13. *(Manifest mode only)* Reconciles the assignment manifest against the client list; runs preflight checks (missing clients, unknown version IDs, eligibility conflicts); halts pipeline if any fatal issues are found; writes the assignment metadata file

**Manifest preflight checks** (manifest mode only — all checked before any PDF is generated):

| Check | Fatal? | Description |
|-------|--------|-------------|
| Missing clients | Always | Clients in the input with no manifest row (when `allow_unassigned: false`) |
| Unknown versions | Always | Manifest rows referencing a version ID not in `notice_versions.yaml` |
| Eligibility conflicts | Always | e.g., affirmative notice assigned to a client with vaccines due |
| Extra manifest rows | Configurable | Manifest rows with no matching client (`extra_manifest_rows: error` or `warn`) |

---

## Step 3 — QR Code Generation (optional)

**Module:** `pipeline/generate_qr_codes.py`

Generates QR code PNG images for each client from a configurable URL payload template. Skipped entirely when `qr.enabled: false`.

**Configuration keys read:**

| Key | Type | Description |
|-----|------|-------------|
| `qr.enabled` | bool | Enable/disable QR code generation |
| `qr.payload_template` | str | URL template with `{field}` placeholders |

**Inputs:** `output/artifacts/preprocessed_clients_<run_id>.json`

**Outputs:** PNG files in `output/artifacts/qr_codes/<sequence>.png`

All template placeholders are validated at config-load time against the `TemplateField` enum. See the [Template Field Reference](../user_guide/configuration.md#template-field-reference) for available placeholders.

---

## Step 4 — Notice Generation

**Module:** `pipeline/generate_notices.py`

Renders Typst source files (`.typ`) for each client by combining the preprocessed JSON artifact with PHU-specific language templates. This step is always run.

**Configuration keys read:**

| Key | Type | Description |
|-----|------|-------------|
| `chart_diseases_header` | list | Chart column disease names (translated per language) |

**Inputs:**

- `output/artifacts/preprocessed_clients_<run_id>.json`
- `output/artifacts/qr_codes/<sequence>.png` (if QR codes were generated)
- Language template module (`templates/` or `phu_templates/<name>/`)
- `config/translations/{lang}_diseases_chart.json`
- `config/translations/{lang}_diseases_overdue.json`

**Outputs:** `.typ` source files in `output/artifacts/typst/`

Templates are loaded dynamically at runtime. The `--template` CLI argument selects a directory under `phu_templates/`. When omitted, the built-in `templates/` directory is used. Each template module must define a `render_notice()` function.

Disease names are translated into the target language in Python before being passed to Typst — no runtime lookups occur in the Typst templates themselves.

**Manifest mode template layout**

When running in manifest mode, each notice version requires its own template subdirectory:

```
phu_templates/my_phu/
├── overdue_standard_v1/
│   ├── en_template.py
│   └── fr_template.py
├── affirmative_schedule_v1/
│   ├── en_template.py
│   └── fr_template.py
└── conf.typ
```

The pipeline builds a registry of all `(version_id, language)` pairs needed by the client list, verifies every required template exists before generating any file, and then dispatches each client to its resolved template. Missing templates are reported as a single error listing all absent paths.

---

## Step 5 — PDF Compilation

**Module:** `pipeline/compile_notices.py`

Compiles the generated `.typ` Typst source files into individual PDF notices by invoking the `typst` command-line tool as a subprocess.

**Configuration keys read:**

| Key | Type | Description |
|-----|------|-------------|
| `typst.bin` | str | Path to the Typst binary (default: `typst`) |

**Inputs:** `.typ` files from `output/artifacts/typst/`

**Outputs:** PDF files in `output/pdf_individual/`

This step is fail-fast: if any `.typ` file fails to compile, the pipeline halts immediately. Typst v0.14.2 is required; the binary must be on `PATH` or configured via `typst.bin`.

---

## Step 6 — PDF Validation

**Module:** `pipeline/validate_pdfs.py`

Validates compiled PDFs against configurable rules using invisible markers embedded by the Typst templates and `pypdf` text extraction.

**Configuration keys read:**

| Key | Type | Description |
|-----|------|-------------|
| `pdf_validation.rules.exactly_two_pages` | severity | Ensure each notice has exactly 2 pages |
| `pdf_validation.rules.signature_overflow` | severity | Signature block must end on page 1 |
| `pdf_validation.rules.envelope_window_1_125` | severity | Contact table height ≤ 1.125 inches |

Severity levels: `disabled` (skip), `warn` (log only), `error` (halt pipeline).

**Inputs:**

- PDFs from `output/pdf_individual/`
- `output/artifacts/preprocessed_clients_<run_id>.json` (source of truth for expected client IDs)

**Outputs:**

- Console summary with per-rule pass/fail counts
- `output/metadata/<lang>_validation_<run_id>.json` — per-PDF results and measurements

For a full explanation of how markers work and how to add new rules, see [PDF Validation](../user_guide/pdf_validation.md).

---

## Step 7 — PDF Encryption (optional)

**Module:** `pipeline/encrypt_notice.py`

Encrypts individual PDFs using a per-client password generated from a configurable template. Skipped when `encryption.enabled: false`.

**Configuration keys read:**

| Key | Type | Description |
|-----|------|-------------|
| `encryption.enabled` | bool | Enable/disable PDF encryption |
| `encryption.password.template` | str | Password template with `{field}` placeholders |

**Inputs:** PDFs from `output/pdf_individual/`

**Outputs:** Encrypted PDFs in `output/pdf_individual/` (replace originals or alongside them)

Per-item recovery: if individual PDF encryption fails, the failure is logged and processing continues for remaining PDFs.

---

## Step 8 — PDF Bundling (optional)

**Module:** `pipeline/bundle_pdfs.py`

Combines individual PDFs into multi-client bundles, optionally grouping by school or board. Skipped when `bundling.bundle_size: 0`.

**Configuration keys read:**

| Key | Type | Description |
|-----|------|-------------|
| `bundling.bundle_size` | int | Max clients per bundle (0 = disabled) |
| `bundling.group_by` | str\|null | Grouping strategy: `null`, `school`, or `board` |

**Inputs:** PDFs from `output/pdf_individual/`

**Outputs:** Bundle PDFs in `output/pdf_combined/` with a manifest JSON

This step runs independently of encryption — both can be enabled simultaneously. Per-item recovery applies.

---

## Step 9 — Cleanup

**Module:** `pipeline/cleanup.py`

Removes intermediate files after a successful pipeline run. Behavior is controlled entirely by configuration flags.

**Configuration keys read:**

| Key | Type | Description |
|-----|------|-------------|
| `pipeline.after_run.remove_artifacts` | bool | Remove `output/artifacts/` (QR codes, Typst files) |
| `pipeline.after_run.remove_unencrypted_pdfs` | bool | Remove unencrypted individual PDFs after encryption/bundling |

When `remove_unencrypted_pdfs: true` and neither encryption nor bundling is enabled, individual PDFs are assumed to be the final output and are preserved regardless of this setting.
