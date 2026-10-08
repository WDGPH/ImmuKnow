# PDF validation

Each run validates the explicit expected PDF set from its render jobs after
whole-set compilation succeeds. It never discovers notices by scanning a
language prefix or selecting every PDF in a directory. Missing outputs fail;
stale files and encrypted copies cannot satisfy an expected job. The
extracted client ID is compared with the job's client ID.

Configure each rule under `pdf_validation.rules` in
`parameters.yaml` as `disabled`, `warn`, or `error`:

| Rule | Check |
|---|---|
| `client_id_presence` | Expected 10-digit client ID appears in the PDF |
| `exactly_two_pages` | The notice has two pages |
| `signature_overflow` | `MARK_END_SIGNATURE_BLOCK` remains on page one |
| `envelope_window_1_125` | `MEASURE_CONTACT_HEIGHT` fits 1.125 inches |

Typst emits invisible, extractable ASCII markers. Contact height is emitted
in PostScript points and divided by 72 for inches. The validator uses
`pypdf` for text and marker extraction; it does not infer geometry from text
positions. A warning is reported but lets the run continue. An error-level
finding fails the run before final delivery. The console gives per-rule
counts, and `metadata/validation_<run_id>.json` keeps per-PDF results and
measurements.

For a new rule, add a clear Typst marker or measurement, parse it in
`immuknow/validate_pdfs.py`, configure its severity, and test both passing
and failing PDFs. Review representative rendered pages as well: extractable
text and measurements cannot establish visual quality.
