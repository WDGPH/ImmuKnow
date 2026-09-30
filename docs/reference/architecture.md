# Pipeline Architecture

## Overview

The ImmuKnow pipeline transforms raw vaccination records exported from Panorama/PEAR into bilingual (EN/FR) PDF immunization notices and history charts for children overdue under CCEYA and ISPA.

The pipeline follows a **sequential, stateless step architecture**: each step reads its inputs fresh from disk and writes its outputs to disk. No in-memory state is passed between steps through the orchestrator. This design ensures that steps are independently testable and re-runnable — if Step 5 fails, you can fix the issue and re-run Steps 5–9 without reprocessing the input data.

## Pipeline flow

```mermaid
flowchart LR
    A[Excel Input] --> S1[1. Prepare Output]
    S1 --> S2[2. Preprocess]
    S2 --> S3[3. Generate QR Codes]
    S3 --> S4[4. Generate Notices]
    S4 --> S5[5. Compile Notices]
    S5 --> S6[6. Validate PDFs]
    S6 --> S7[7. Encrypt PDFs]
    S7 --> S8[8. Bundle PDFs]
    S8 --> S9[9. Cleanup]
    S9 --> Z[Output Directory]

    style S3 stroke-dasharray: 5 5
    style S7 stroke-dasharray: 5 5
    style S8 stroke-dasharray: 5 5
```

Steps shown with dashed borders are optional — they are skipped when disabled in `config/parameters.yaml`.

## Step summary

| Step | Module | Key Inputs | Key Outputs |
|------|--------|-----------|-------------|
| 1 | `prepare_output.py` | Config flags | Clean `output/` directory |
| 2 | `preprocess.py` | Excel file, `vaccine_reference.json`, `disease_normalization.json`, optional `notice_versions.yaml` + assignment manifest | `preprocessed_clients_<run_id>.json`; `notice_assignments_<run_id>.json` (manifest mode) |
| 3 | `generate_qr_codes.py` | Preprocessed JSON, QR config | PNG files in `output/artifacts/qr_codes/` |
| 4 | `generate_notices.py` | Preprocessed JSON, Typst templates (per-version subdirectories in manifest mode) | `.typ` files in `output/artifacts/typst/` |
| 5 | `compile_notices.py` | `.typ` files | PDF files in `output/pdf_individual/` |
| 6 | `validate_pdfs.py` | PDFs, artifact JSON | Console summary, `output/metadata/<lang>_validation_<run_id>.json` |
| 7 | `encrypt_notice.py` | Individual PDFs, encryption config | Encrypted PDFs in `output/pdf_individual/` |
| 8 | `bundle_pdfs.py` | Individual PDFs, bundling config | Bundle PDFs in `output/pdf_combined/` |
| 9 | `cleanup.py` | Cleanup config | Removes intermediate artifacts |

## Design principles

**Stateless steps**
Each step reads its inputs from disk and writes outputs to disk. The orchestrator never passes in-memory objects between steps. This means same input always produces the same output, and any step can be re-run independently.

**Normalized JSON artifact**
Preprocessing produces a single `preprocessed_clients_<run_id>.json` artifact that serves as the canonical source of truth for all downstream steps. Client records are deterministically ordered by school → last name → first name → client ID, and each client receives a stable sequence number (`00001`, `00002`, etc.) that persists through all downstream operations.

**Bilingual support**
Both English and French are first-class concerns. Disease names, notice text, and date formatting are all localized before being passed to Typst. In fixed mode the `language` argument selects a single rendering path shared by all clients. In manifest mode each client carries its own resolved language from the assignment manifest, enabling mixed-language runs.

**Notice versioning (manifest mode)**
When `config/notice_versions.yaml` is present and `--notice-assignments` is supplied, the pipeline enters manifest mode. Each client is mapped to a specific notice version (e.g., `overdue_standard_v1`, `affirmative_schedule_v1`) and language. A preflight gate after preprocessing catches missing clients, unknown version IDs, and eligibility conflicts before any PDF is generated. When the catalog file is absent, the pipeline behaves identically to fixed mode.

**Fail-fast vs. per-item recovery**
Critical steps (Preprocessing, Notice Generation, Compilation, PDF Validation) implement fail-fast: any error halts the pipeline immediately. Optional steps (QR Codes, Encryption, Bundling) implement per-item recovery: individual item failures are logged and skipped, and the pipeline continues processing remaining items.

## Module organization

```
pipeline/
├── orchestrator.py         # CLI entry point (viper), coordinates 9 steps
├── prepare_output.py       # Step 1
├── preprocess.py           # Step 2
├── generate_qr_codes.py    # Step 3 (optional)
├── generate_notices.py     # Step 4
├── compile_notices.py      # Step 5
├── validate_pdfs.py        # Step 6
├── encrypt_notice.py       # Step 7 (optional)
├── bundle_pdfs.py          # Step 8 (optional)
├── cleanup.py              # Step 9
├── config_loader.py        # Configuration loading and validation
├── data_models.py          # Dataclasses for client records and artifacts
├── enums.py                # Language, BundleStrategy, TemplateField enums
├── translation_helpers.py  # Disease name normalization and translation
├── validate_phix.py        # PHIX school name validation (called from preprocess)
├── notice_versioning.py    # Notice version catalog loader and eligibility validation
├── assignment_manifest.py  # Assignment manifest loader, reconciliation, and preflight summary
└── utils.py                # Template rendering and context building utilities

templates/                  # Built-in Typst templates (EN/FR)
phu_templates/              # PHU-specific template overrides (gitignored)
```
