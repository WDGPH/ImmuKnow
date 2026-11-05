# PDF backend comparison

This optional executable compares pinned pdf_oxide 0.3.78 with the pipeline's
lopdf 0.47.0 on already generated fictional notice PDFs. It is built separately,
contains no Typst dependency, and is never linked into the notice executable.
Its independent dependency lock does not change the pipeline's dependency graph.

From `experiments/rust-pipeline`:

```sh
CARGO_TARGET_DIR="$PWD/target" cargo build --release --locked --jobs 1 \
  --manifest-path pdf-backend-probe/Cargo.toml

target/release/immuknow-pdf-backend-probe --backend lopdf bench \
  --record /path/to/rust/run.json --output /path/to/new-directory \
  --operation encrypt --workers 4
```

Repeat with `--backend oxide`, `--operation merge`, and one versus four workers.
Each output directory must be new. Encryption uses the original DOB password,
AES-256 revision 6, passwordless refusal and passworded reopening with matching
page counts. Both backends call the **same** lopdf post-save verifier. Source
loading/writing uses the selected backend. Merge tests use the source run's
existing bundle memberships and reopen the output to verify page counts. The
probe does not include Typst, reports or the complete notice workflow; these are
component timings, not end-to-end results.

Using Core's Python development environment, independently check six fictional
notices (Unicode password, pixels, links and standalone tags), six-notice bundles,
inherited page resources/geometry/rotation, and internal cross-page links:

```sh
python pdf-backend-probe/check.py \
  --binary "$PWD/target/release/immuknow-pdf-backend-probe" \
  --record /path/to/rust/run.json --output /path/to/new-check-directory
```

The checker records each backend/case result, including rejected candidates,
in `results.json`. It compares link behavior rather than document-specific
object numbers. A backend's elapsed time is not evidence of page/link fidelity;
read its independent case outcomes before considering a pipeline replacement.

## Measured result

The PDF-only comparison used the same 1,000 original fictional notice PDFs and
ten existing 200-page bundle memberships, one or four application workers, and
default library threading. Both backends were in one optimized executable with
one dependency lock. These are individual runs; they exclude Typst and final
cohort reporting.

| Component | Workers | lopdf | pdf_oxide |
| --- | ---: | ---: | ---: |
| Encrypt 1,000 notices and verify output | 1 | 34.6 s | Rejected |
| Encrypt 1,000 notices and verify output | 4 | 11.1 s | Rejected |
| Merge ten bundles and verify page counts | 1 | 5.3 s | 5.6 s |
| Merge ten bundles and verify page counts | 4 | 3.9 s | 2.9 s |

The rejected encryption attempts failed the required post-save readback, so their
elapsed times are not successful encryption throughput. Both ordinary ASCII DOB
and Unicode passwords exposed a missing `/Perms` entry in pdf_oxide's revision-6
encryption dictionary. Independent pikepdf/qpdf rejected those files as missing
V=5 encryption parameters; MuPDF authenticated them. This is an interoperability
failure, not evidence of an incorrect password or a Unicode-only issue.

Both backends preserved the six starter notices' bundle pixels/URI links and the
inherited resources, page boxes and rotation fixture. pdf_oxide failed an internal
link case using two **different** two-page source PDFs: the first page of the
second notice linked to bundle page one instead of bundle page four. lopdf
preserved both targets. That regression remains even though all page counts and
page pixels match. The four-worker pdf_oxide bundles were also about 23% larger
(594 MB versus 482 MB, decimal).

Keep lopdf for the pipeline. A roughly one-second isolated bundle-stage gain does
not justify adopting these regressions or maintaining a PDF-writer fork. The
existing encrypted-output reopening earns its cost by rejecting these outputs;
there is no new per-page runtime comparison. Shared PDF/queue unit tests belong
to the parent crate; this executable's real CLI behavior is checked here with
independent readers.
