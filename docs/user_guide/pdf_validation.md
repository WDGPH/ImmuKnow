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
| `envelope_window` | Measured address bounds fit the template’s page-relative window and safety padding |
| `envelope_window_1_125` | Compatibility check: measured contact height fits 1.125 inches |

The maintained defaults enable `envelope_window` at warning severity. The older
fixed-height rule is disabled by default; enable it only for that compatibility
preset. Configure `envelope_window: error` to block delivery for overflow.

The shared `client-block` emits the window rectangle and measured address bounds
from the same layout. Coordinates start at the top-left of the printed page,
with an internal safety inset on all sides. The check requires geometry version
1, page one, a window inside the paper, and address content inside its safe area.
Missing, duplicate, or invalid required measurements fail an enabled rule.
Missing or duplicate signature evidence also fails its enabled rule.

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

Digital geometry checks do not certify physical print alignment. Review an
actual-size print with the intended envelope and folds. Keep preview guides out
of the document source so they do not appear in exported or production PDFs.
