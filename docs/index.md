# ImmuKnow

**Current version:** v1.0.0

ImmuKnow is a Python-based pipeline for generating bilingual (EN/FR) **personalized immunization history charts and notice letters** for children overdue for mandated vaccinations under the Child Care and Early Years Act (CCEYA) and ISPA. It is designed for use by Public Health Units (PHUs) across Ontario and produces publication-quality PDFs using [Typst](https://typst.app) as the typesetting engine.

## What it does

For each client in an input dataset extracted from Panorama/PEAR, the pipeline:

- Validates and normalizes raw vaccination records
- Generates a bilingual immunization history chart
- Renders a personalized notice letter with the client's overdue vaccines
- Optionally encrypts individual PDFs and bundles them by school or board

Output is ready for direct mailing or electronic delivery.

## Pipeline architecture

The pipeline runs nine sequential, stateless steps. Each step reads its inputs from disk and writes its outputs to disk — no in-memory state is passed between steps. This design makes individual steps independently testable and re-runnable.

| Step | Module | Purpose |
|------|--------|---------|
| 1 | `prepare_output.py` | Output directory setup |
| 2 | `preprocess.py` | Data validation & normalization → JSON artifact |
| 3 | `generate_qr_codes.py` | QR code PNG generation (optional) |
| 4 | `generate_notices.py` | Localized JSON and static template preparation |
| 5 | `compile_notices.py` | Typst → PDF compilation |
| 6 | `validate_pdfs.py` | PDF validation (rules, summary, JSON report) |
| 7 | `encrypt_notice.py` | PDF encryption (optional) |
| 8 | `bundle_pdfs.py` | PDF bundling & grouping (optional) |
| 9 | `cleanup.py` | Intermediate file cleanup |

## Navigation

<div class="grid cards" markdown>

-   **User Guide**

    ---

    Install the pipeline, configure it for your PHU, and run your first batch.

    [:octicons-arrow-right-24: Get started](user_guide/getting_started.md)

-   **Reference**

    ---

    Pipeline architecture, per-step details, and full API documentation.

    [:octicons-arrow-right-24: Architecture](reference/architecture.md)

-   **Developer Guide**

    ---

    Contributing, branching strategy, testing standards, and AI agent workflow.

    [:octicons-arrow-right-24: Contributing](developer_guide/contributing.md)

-   **Changelog**

    ---

    Release history and version notes.

    [:octicons-arrow-right-24: Changelog](changelog.md)

</div>
