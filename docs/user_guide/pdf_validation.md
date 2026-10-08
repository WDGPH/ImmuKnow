# PDF Validation: Markers + Measurements

This document explains how we validate compiled PDFs using invisible template markers and measurements plus pypdf text extraction. It covers the marker format, the rules we enforce, configuration, outputs, and how to extend the system.

## What we validate

We validate layout and structure using rules configured in `config/parameters.yaml` under `pdf_validation.rules`:

- `exactly_two_pages`: Ensure each notice PDF has exactly 2 pages.
- `signature_overflow`: Ensure the signature block ends on page 1.
- `envelope_window_1_125`: Ensure the contact table height fits a 1.125-inch envelope window.
- `client_id_presence`: Compare the client ID extracted from the PDF with the ID in its render job.

Each rule can be configured to `disabled`, `warn`, or `error`.

Example:

```yaml
pdf_validation:
  # Validation rules: "disabled" (skip check), "warn" (log only), or "error" (halt pipeline)
  rules:
    client_id_presence: error       # PDF must contain the expected client ID
    exactly_two_pages: warn         # Ensure PDF has exactly 2 pages (notice + immunization record)
    signature_overflow: warn        # Signature block not on page 1
    envelope_window_1_125: warn     # Contact table fits in envelope window (1.125in max height)
```

## How the markers work

The Typst templates embed invisible text markers that we can reliably extract from the compiled PDF text. We use two categories:

- MARKers: Boolean/positional markers
    - `MARK_END_SIGNATURE_BLOCK` — emitted at the end of the signature block. We scan pages for this marker to find the page where the signature block ends.
- MEASUREments: Numeric metrics in points
    - Format: `MEASURE_<NAME>:<value>` (e.g., `MEASURE_CONTACT_HEIGHT:81.0`). Values are in PostScript points. Conversion: 72 points = 1 inch.

These markers are rendered invisibly in the PDF (e.g., zero-opacity/white/hidden), but remain extractable by text extraction. They should be ASCII and simple to ensure robust extraction across renderers.

### Example measurements we emit

- `MEASURE_CONTACT_HEIGHT` — The height of the contact information table on page 1 (in points). We convert this to inches and compare to the envelope window limit.
- `MARK_END_SIGNATURE_BLOCK` — A marker string included where the signature block ends.

## Extraction pipeline

Module: `pipeline/validate_pdfs.py`

Key functions:

- `extract_measurements_from_markers(page_text: str) -> dict[str, float]`
    - Parses all `MEASURE_...:<value>` markers from page text and returns a dict of measurements (in points).
- `validate_pdf_layout(pdf_path, reader, enabled_rules) -> (warnings, measurements)`
    - Uses `pypdf.PdfReader` to extract page text.
    - Locates `MARK_END_SIGNATURE_BLOCK` to determine `signature_page`.
    - Reads `MEASURE_CONTACT_HEIGHT` and converts to inches as `contact_height_inches`.
- `validate_pdf_structure(pdf_path, enabled_rules) -> ValidationResult`
    - Counts pages, adds `page_count` to `measurements`.
    - Applies page-count rule and then layout rules.

We centralize reading via `pypdf.PdfReader` and only extract plain text; we do not rely on PDF layout coordinates.

## Rules: logic and outputs

- exactly_two_pages
    - Logic: page_count must equal 2.
    - Warning message: `exactly_two_pages: has N pages (expected 2)`
    - Measurement included: `page_count: N`

- signature_overflow
    - Logic: Find the page containing `MARK_END_SIGNATURE_BLOCK`; it must be page 1.
    - Warning message: `signature_overflow: Signature block ends on page P (expected page 1)`
    - Measurement included: `signature_page: P`

- envelope_window_1_125
    - Logic: Extract `MEASURE_CONTACT_HEIGHT` on page 1; convert to inches. Must be <= 1.125 in.
    - Warning message: `envelope_window_1_125: Contact table height H.in exceeds envelope window (max 1.125in)`
    - Measurement included: `contact_height_inches: H`

## Outputs: console and JSON

Console summary includes per-rule status for all rules (including disabled), with pass/fail counts and severity labels. The output may omit the high‑level pass count and focus on rule lines when run via the orchestrator.

Example (current orchestrator output):

```
Validation rules:
  - envelope_window_1_125 [warn]: ✓ 5 passed
  - exactly_two_pages [warn]: ✓ 5 passed
  - signature_overflow [warn]: ✓ 5 passed

Detailed validation results: output/metadata/en_validation_<timestamp>.json
```

JSON summary is written to `output/metadata/validation_{run_id}.json` and has:

- `rule_results`: per-rule pass/fail with severity
- `results`: per-PDF details, warnings, and measurements

Example excerpt:

```json
{
  "rule_results": [
    {"rule_name": "exactly_two_pages", "severity": "warn", "passed_count": 5, "failed_count": 0},
    {"rule_name": "signature_overflow", "severity": "warn", "passed_count": 5, "failed_count": 0},
    {"rule_name": "envelope_window_1_125", "severity": "warn", "passed_count": 5, "failed_count": 0}
  ],
  "results": [
    {
      "filename": "en_notice_00001_...pdf",
      "warnings": [],
      "passed": true,
      "measurements": {
        "page_count": 2.0,
        "signature_page": 1.0,
        "contact_height_inches": 1.125
      }
    }
  ]
}
```

## Validate the expected notice set

Step 6 reads `artifacts/render_jobs.json` and requires the whole-stage
`artifacts/compilation.json` record. It passes each job's expected PDF path and
client ID to the validator. A missing expected PDF fails the run; unrelated PDFs,
old files, and encrypted copies are not selected. Filenames label the outputs,
but the render jobs supply the expected client identities.

The `client_id_presence` rule searches extracted text for a 10-digit ID and
compares it with that job's client ID. The rule is markerless and is enabled at
`error` severity in the packaged configuration. It catches absent or mismatched
IDs without relying on a language prefix in the filename.

## Why we prefer template‑emitted measurements over PDF distance math

We strongly prefer emitting precise measurements from the Typst template (via `measure()` and `MEASURE_...` markers) instead of inferring sizes by computing distances between two markers in extracted PDF text. Reasons:

- **Deterministic geometry:** Typst knows the actual layout geometry (line breaks, spacing, leading, table cell borders). Emitting a numeric measurement captures the truth directly.
- **Robust to text extraction quirks:** PDF text extraction can lose exact ordering, merge or split whitespace, and is affected by ligatures/kerning and font encodings. Geometry in points is stable; text streams are not.
- **Locale‑safe:** Measurements are invariant across languages (EN/FR) even as word lengths and hyphenation change.
- **Unit consistency:** We always emit PostScript points and convert with 72 pt = 1 in. No need for pixel/scale heuristics.
- **Clear rule contracts:** Rules assert against explicit metrics (e.g., `contact_height_inches <= 1.125`) instead of implicit heuristics (e.g., count lines, guess distances).
- **Testability:** Numeric outputs are easy to assert in unit tests and in JSON `measurements`.

When marker pairs are useful

- Presence/ordering checks (e.g., `MARK_END_SIGNATURE_BLOCK` on page 1) — use a boolean/positional marker.
- Avoid using two markers and computing a distance in the extracted text; prefer a single numeric `MEASURE_...` emitted by the template that already accounts for the exact box height/width.

Recommended Typst pattern (illustrative)

```typst
// Compute height of the contact block and emit an invisible measurement
#let contact_box = box(contact_table)
#let dims = measure(contact_box)
// dims.height is in pt; emit a plain ASCII marker for pypdf to read
// The text should be invisible (e.g., white on white or zero‑opacity) but extractable
MEASURE_CONTACT_HEIGHT: #dims.height

// Place the signature end marker where the block actually ends
MARK_END_SIGNATURE_BLOCK
```

Validator side (already implemented)

- Parse `MEASURE_CONTACT_HEIGHT:<points>` via `extract_measurements_from_markers()`.
- Convert to inches (`points / 72.0`) as `contact_height_inches`.
- Compare to configured threshold (e.g., 1.125in) and surface the actual value in warnings and JSON.

## Adding a new rule

1. Emit a marker in the Typst template:
    - For a numeric metric: output `MEASURE_<NAME>:<points>` (points are recommended for consistency).
    - For a position marker: insert a unique text token like `MARK_<SOMETHING>` at the desired location.
2. In `validate_pdfs.py`:
    - Extend `extract_measurements_from_markers` if needed (it already parses any `MEASURE_...:<value>` tokens).
    - Read the measurement or locate the marker in `validate_pdf_layout`.
    - Convert units as needed (use 72 points = 1 inch for inches).
    - Store the measurement using its natural Python type so downstream JSON preserves meaning (e.g., counts as `int`, dimensions as `float`, identifiers as `str`). The `ValidationResult.measurements` dict accepts `int | float | str`; adding other types should include a deliberate type hint update.
    - Add a warning message under the new rule key when conditions fail.
3. Add the rule to `config/parameters.yaml` under `pdf_validation.rules` with `disabled|warn|error`.
4. Add tests validating both the pass and fail paths, checking that `measurements` includes the new key with the expected value and type.

## Troubleshooting

- No markers found in text
    - Ensure the marker strings are plain ASCII and not removed by the template’s visibility settings.
    - Ensure text extraction is possible: pypdf reads the pages and returns text (some fonts/encodings may complicate extraction).
- Units confusion
    - `MEASURE_...` values should be in points; convert with `inches = points / 72.0`.
- False negatives for `signature_overflow`
    - Confirm `MARK_END_SIGNATURE_BLOCK` is emitted exactly where the signature block ends and not earlier.
- Missing measurements in JSON
    - Check that the rule is enabled and the markers are present on the expected page (page 1 for contact height).

## How to run

Run validation through the orchestrator so it receives the complete expected
PDF list and client IDs from the render jobs:

```bash
uv run viper students.xlsx en
```

The validator writes `output/metadata/validation_<run_id>.json` and prints
per-rule counts. A rule at `error` severity fails the pipeline. For library
use, pass the explicit expected PDF paths and client ID mapping to
`pipeline.validate_pdfs.main`; a directory scan is not the notice-set contract.
