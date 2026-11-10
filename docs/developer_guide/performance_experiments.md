# QR and CSV reporting acceptance

The v2 acceptance uses a new fictional workload with unique clients, realistic
history lengths and long QR destinations. It does not replay the supplied private
run or repeat the earlier short-history benchmark. The [aggregate measurements](../assets/csv-qr-benchmark.json)
retain individual times, input/font/binary/resource identities, limits and checks.
The [maintainer harness](performance_harness.md) creates the fixture,
measures complete commands and verifies artifacts outside timing.

## Styled QR results

The two changes are bulk conversion to an integer grid and arithmetic finder
bounds. The vendored WASM is unchanged. Four balanced alternating 1,000-row pairs
compare the same reporting implementation at `f133ee8`, changing only
`qr-encode.typ` and `qr-style.typ`. Ordinary cached rebuilds produce byte-identical
control executables and refresh embedded resource identities. Two control versus
control pairs range from 58.10 to 58.86 seconds; their largest paired wall
variation is 1.31% and CPU variation 1.83%.

| Pair | Control wall, s | Integer grid wall, s | Control CPU, s | Integer grid CPU, s |
| --- | ---: | ---: | ---: | ---: |
| 1 | 59.29 | 50.99 | 138.50 | 123.10 |
| 2 | 59.29 | 51.05 | 138.52 | 124.39 |
| 3 | 59.00 | 50.73 | 137.22 | 120.68 |
| 4 | 57.10 | 51.41 | 134.67 | 123.34 |

Median paired command-wall reduction is **13.95%** (range 9.97–14.02%); CPU
reduction is **10.66%** (8.41–12.05%). Peak RSS decreases in every pair, with a
median 5.21% reduction. These changes are repeatably beneficial beyond the
measured rebuild variation. No OOM occurred.

One matched 5,800-row confirmation takes 358.61 versus 310.46 seconds and 832.65
versus 741.54 CPU seconds. That is one pair, not a distribution or capacity
promise. A separate historical HTML baseline takes 373.77 seconds, with 3.65 GB
peak RSS, versus 2.43 GB for the combined candidate. Reporting and QR effects
must not be added to one another or to earlier results.

The timed cohort uses both English variants equally, median 19 history entries,
32 schools, school/variant grouping, last-name/DOB ordering, encryption off,
timestamp `1793534400`, and compilation/encryption/bundle workers 2/2/4. The
shared environment has a four-CPU quota, 8 GiB memory limit and warm uncontrolled
filesystem caches. Builds, profiling, PDF parsing and spreadsheet work are outside
native timing. Separate 200-row RGB-SVG and CMYK-run context pairs preserve exact
outputs; those paths bypass the changed helpers, so their small timing differences
do not establish an optimization benefit.

All 15 timed main trials pass artifact hashes, facts, routing, bundle order and
semantic evidence comparisons, including every retained per-check measurement.
Only deliberately removed passing layout duplicates are excluded. Independent
PyMuPDF checks verify all 5,800 originals, 11,600 original pages and 64 bundles:
each source is bundled exactly once, inclusive ranges match physical pages, and
bundled page streams, text, dimensions and URI rectangles match their originals.
Separate renderer acceptance decodes 28 actual English/French PDFs across module
and corner styles, custom finder/alignment colors, SVG/CMYK paths, safe logos,
masks and long histories. Unsafe structural overlaps and out-of-bounds masks stay
rejected. Deliberately long address stress content retains pre-existing clipping
in both arms; this work does not establish perfect presentation for arbitrary
content or printed QR sizes.

## Reporting size and latency

At 5,800 rows the selected pair is **3,279,991 bytes**, versus 122,083,197 bytes
of old HTML plus 17,516,622 bytes of bundle CSVs: **2.35%** of the old presentation
bytes, below the proposed 25% target. There are no HTML or per-bundle CSV writes.
The canonical record keeps the facts, observed/effective evidence, provenance,
review history and artifact membership separately from these review tables.

The matched throughput candidates above write pretty JSON. Later `1f2ddf8` writes
the same canonical values compactly, reducing the retained full record from
181,009,889 to 103,402,895 bytes. Isolated calls to the actual library, excluding
record loading, measure three checkpoints at 0.84–1.18 seconds and paired CSV
publication at 1.63–2.57 seconds. Publication includes two canonical saves and
selection of the immutable pair, rather than CSV streaming alone. The earlier
pretty implementation takes 1.14–1.24 and 2.70–3.48 seconds respectively.

A real missing-export recovery on the compact 5,800-row completed run takes
14.05 seconds wall and 13.83 CPU seconds, versus 18.37 and 17.91 for the earlier
pretty record. Revision, facts, findings and review/attempt semantics remain
unchanged; regenerated CSV hashes match. These are separate one-command recovery
samples, not paired evidence for a precise percentage gain. Small native
regressions cover failed/partial run refresh; the 5,800-row case is completed-run
recovery. The proposed two-second publication/refresh target is **not consistently
met**. Loading, strict validation and final canonical publication remain part of
whole refresh; preserving required evidence takes precedence over that target.

A final bounded reader experiment at `ff58660` moves already validated arrays
straight into `Value::Array`, instead of serializing their entire nested contents
again. It preserves recursive duplicate-field rejection. Three alternating pairs
on the same compact 103 MB record take 4.15–5.59 seconds for the previous reader
and 2.08–2.20 seconds for the move. Median paired read-wall and CPU reductions are
56.37% and 56.61%; read-process high-water memory falls from about 1.67 to 0.98 GB.
Every canonical-content hash is identical, and typed/nested/escaped-duplicate-key
regressions pass. These clocks measure reading only, with content hashing outside
the read interval; they are not whole-refresh speedups. No additional reader or
validation rewrite is included. The final locked release suite passes 103 tests.

The final runtime `ff58660` then completes the same 1,000-row fixture in 50.41
seconds versus 50.09 for the frozen combined `f133ee8` candidate. This single
confirmation establishes no additional throughput gain; PDF bytes, facts,
retained findings/measurements, routing and membership match exactly. Final
completed-run missing-export recovery takes 10.94 seconds. A genuine setup
failure after reading all 5,800 rows refreshes in 0.20 seconds; all records retain
error severity with pending unattempted originals, one global failure explains
the interruption, and no PDF paths are invented. Both recovery cases preserve all
non-export semantics, revision and paired CSV hashes. Full completed-run recovery
still misses the two-second target. The preserved executable exports all 29
tracked resource files byte for byte outside the checkout.

Gnumeric 1.12.51's headless engine imports the full records CSV in 1.92 seconds,
loads/recalculates a typed-text workbook in 1.25 seconds and exports calculated
CSV in 0.86 seconds. It preserves every nonempty field, verifies all 5,800
row-key joins and selects the expected 2,900 rows with a calculated variant
filter. A separate five-row case checks leading-zero IDs, quoted French and
formula-like names beginning `=`, `+` and `@`. Auto-import coerces leading-zero
IDs to numbers; explicit text cells preserve them. This measures the spreadsheet
engine, not a GUI import wizard or AutoFilter interaction. Import identifiers as
text as described in the [review guide](../user_guide/pdf_validation.md).

## Historical experiments

The remainder of this page describes earlier HTML-producing revisions. Its
retained-check policy, QR implementation, report shape and costs refer to those
recorded sources, not to the current v2 implementation. Preserve their provenance;
do not combine their speedups with the current experiment.

## Profiling the reduced pipeline

These experiments start from Core `c483af0`, whose implementation is the reduced-work pipeline at `e7a8de1`. That path already removed redundant PDF reopens. Earlier production-path estimates are not added to these results. The accepted source change is the notice checkpoint schedule in `src/pipeline.rs`; existing JSON ownership moves, buffered preparation output, streamed report JSON and single-pass HTML escaping are retained. No history, QR, schema or dependency change is included.

## Method and evidence

Three alternating paired rounds measured each complete command, from process startup through final report publication and exit. The machine was shared, with a four-CPU quota and an 8 GiB memory limit. Compilation, encryption and bundle workers were fixed at 2, 2 and 4. Filesystem caches were warm; our timing, build, profiling and acceptance jobs used one exclusive lock. That lock does not reserve the host against unrelated activity. CPU time and exact process peak RSS came from Linux `wait4`. Build time, profiler overhead and acceptance checks were outside command timing. The saved `timings.total_seconds` stops before the final report write, so the external elapsed measurement is authoritative for command time.

The fixture repeats Template's ten fictional English/French cases, with unique ten-digit client IDs, a fixed timestamp of `1793534400`, identical assignments, project data and fonts. At 1,000 notices it creates 2,000 original pages, 1,000 AES-256 revision 6 copies, ten bundles and 700 QR-bearing notices. The 5,000-row case repeats the same mix five times, producing 10,000 original pages, 5,000 protected copies, fifty bundles and 3,500 QR-bearing notices.

The [measurement data](../assets/current-pipeline-benchmark.json) records individual command lines, binary/source/dependency/input/font hashes, CPU and memory limits, stage profiles and checks. Every timed run recomputed all 3,010 or 15,050 artifact hashes after timing. Complete records matched except for timings and randomized encrypted-copy hashes; original and bundled PDF bytes matched. HTML matched after fingerprint normalization. Separate saved-output acceptance checked 1,000 protected copies for each variant using registry `lopdf` without Core helpers: encryption settings, empty/wrong password refusal, correct password access, decrypted streams/strings, pages and bundle membership. First-pair artifacts and every saved report remain available; redundant generated artifacts from later rounds were removed only after verification, outside timing.

## Accepted improvements

### Keep serial PDF parsing

With the existing 100-row report schedule, serial parsing took 25.31 seconds median; enabling only `lopdf/rayon` took 26.48 seconds. Serial reduced elapsed time 4.4% and CPU work 8.3%. Its highest peak RSS was slightly higher: 1.07 versus 1.04 GiB. Retain serial parsing for elapsed time and CPU use; this experiment does not establish a memory saving. The Cargo diagnostic build used `--features lopdf/rayon`; other features and the outer worker counts were held constant, with `RAYON_*` environment overrides unset.

### Serialize full checkpoints less often

| Notices | Every 100 notices | Adaptive checkpoints | Elapsed reduction |
| --- | ---: | ---: | ---: |
| 1,000 | 25.20 s | 23.31 s | 7.5% |
| 5,000 | 175.83 s | 121.44 s | 30.9% |

For 1,000 notices, median CPU work was 76.92 versus 74.86 seconds; highest peak RSS was 1.09 versus 1.06 GiB. For 5,000 notices, CPU work was 432.80 versus 381.27 seconds, an 11.9% reduction. Peak RSS was essentially unchanged at 2.34 GiB.

The new schedule saves at 100 processed notice rows, then doubles the next row threshold after each successful save. It also saves at the next row boundary after 30 seconds since the previous successful save. The notice coordinator starts the clock when it begins processing worker results and resets it after writing; setup, a slow row or a report write can extend the wall-clock gap. Setup, final and caught-error reporting remain independent. This historical experiment retained the then-current HTML view. The current design checkpoints `run.json` and publishes paired CSVs at final events; there is no resume command.

The recovery tradeoff is less frequent intermediate snapshots. Deterministic clock tests cover row and elapsed-time thresholds. A fresh forced-interruption check observed both the 100- and 200-row snapshots, verified all 1,000 source rows and every listed original-PDF link/hash, then confirmed that the incomplete folder and readable reports remained after termination.

### Retain the existing allocation changes

This historical experiment used owned JSON moves, streamed report JSON, buffered preparation output and single-pass HTML escaping. Their individual historical savings were not re-added or estimated. The current profile supports removing repeated writes; it does not reveal a regression requiring those implementations to be reverted.

## Remaining reporting cost

A separate baseline profile at 1,000 notices recorded 14 report writes: 1.30 seconds building HTML, 1.53 writing JSON and 0.28 writing HTML, 3.12 seconds total. The adaptive 5,000-notice profile recorded 11 full writes: 3.59, 4.93 and 0.92 seconds respectively, 9.47 seconds total. These are separate instrumented profiles at different sizes, not an additional paired speedup. Reporting runs on the coordinator; compiler and encryption span totals overlap and are not additive command-time shares.

A synthetic replay isolates repeated report generation from PDF generation. It starts from saved notice data, progressively replaces pending rows and writes the full record/view at each chosen checkpoint. Each case is one replay, so use the three-pair commands above for the accepted effect size. The doubling replay omits the 30-second trigger and setup writes.

| Rows | Every 100: writes / seconds | Doubling: writes / seconds | Compact passes, every 100: seconds |
| --- | ---: | ---: | ---: |
| 1,000 | 10 / 2.01 | 5 / 1.03 | 1.46 |
| 5,000 | 50 / 47.57 | 7 / 5.28 | 35.67 |
| 10,000 | 100 / 203.25 | 8 / 12.07 | 147.66 |

The 10,000-row result is report-only replay evidence, not a measured 10,000-notice command or a throughput forecast.

## Experiments not adopted

### Compact passing-check details

The compact replay removes `message` and `measurements` from every passing check in observed checks, effective checks and render evidence. Warnings, failures, codes, statuses, page/component identifiers and policy reasons remain. Some overlapping component evidence survives, but it cannot reconstruct every removed check-specific measurement.

At 5,000 rows, the final replay JSON shrank from 176.83 to 125.45 MB and HTML from 97.00 to 73.51 MB. The 50-write replay fell from 47.57 to 35.67 seconds. Users lose the explanation of why a check passed and its check-specific numeric evidence; passed rows become less understandable when expanded. This is a separate report-only experiment, not a whole-command speedup. Full passing-check detail is retained; reducing checkpoint frequency already provides the accepted improvement without this information loss.

### History preparation and a new plugin boundary

The actual ten-case notice mix has 1–8 administrations per history. Isolated tests use 10, 50 and 200 administrations on unique dates, comparing a blank baseline, display-row projection alone, and the complete native table. The complete table includes projection, cell construction, native layout, findings and PDF export; subtracting the projection compile does not isolate pure native layout.

| Administrations | Projection-only total, ms | Full table total, ms | PDF export included in full total, ms |
| --- | ---: | ---: | ---: |
| 10 | 4.13 | 18.74 | 3.04 |
| 50 | 10.68 | 55.87 | 6.15 |
| 200 | 92.58 | 255.33 | 15.37 |

Values are medians of three isolated compilations and include fixed compiler overhead. Separate Typst traces identify native `layout_table` and the repeated per-date filtering at `history.typ:27`:

| Administrations | Per-date filter self time, ms | Native table layout inclusive time, ms |
| --- | ---: | ---: |
| 10 | 0.26 | 10.86 |
| 50 | 5.09 | 24.23 |
| 200 | 79.78 | 84.64 |

These single trace samples have tracing overhead and overlapping inclusive scopes; do not add them to the uninstrumented medians. Native table layout ranged from 1.77 to 13.81 ms in the ten actual notice traces. Projection is small in the measured notice mix. The 200-administration case exposes repeated filtering as a separate scaling limit. No whole-command benefit has been demonstrated for a history Rust/WASM plugin, so adding serialization and another maintained implementation is not justified by these results. Native table layout stays in Typst, and agent-to-disease mappings continue to come from the project's editable `vaccine_reference.json`.

### QR protocol and geometry micro-optimizations

QR probes use the production persistent compiler and shipped plugin. Three isolated compilations per case each render five distinct payloads. Totals below are amortized per code and include compilation and export. Marker colors, corner styles, module shapes, CMYK fallback and a short-payload logo are represented.

| Style | 33-byte payload, ms/code | 129-byte payload, ms/code | 513-byte payload, ms/code |
| --- | ---: | ---: | ---: |
| Square, RGB SVG | 5.99 | 9.10 | 27.89 |
| Square, CMYK runs | 7.88 | 15.50 | 46.93 |
| Dots | 17.07 | 31.06 | 95.49 |
| Rounded modules | 18.20 | 30.40 | 101.16 |
| Separated modules | 16.50 | 32.12 | 103.97 |
| Rounded corners | 18.67 | 36.21 | 123.59 |
| Marker colors | 22.36 | 44.97 | 176.74 |
| 10% center logo | 20.28 | — | — |

A 129-byte logo case was separately rejected for overlapping a structural marker, preserving the existing guard. Logo viability depends on matrix structure; omitted long-logo cells do not imply supported combinations were removed.

A disposable plugin adds no-op, encoding-only, pre-encoded SVG-geometry and SVG-transfer exports. It is never shipped. Thirty distinct calls per case separate these costs; base URLs are 32, 128 or 512 bytes before a one- or two-digit counter. The following single-trace means are inside `call plugin`, in milliseconds per call:

| Base URL bytes | Encoding only | SVG geometry from matrix | SVG byte transfer | Full encode + SVG |
| --- | ---: | ---: | ---: | ---: |
| 32 | 2.882 | 0.419 | 0.007 | 3.438 |
| 128 | 5.671 | 1.417 | 0.011 | 6.965 |
| 512 | 19.882 | 4.370 | 0.023 | 24.043 |

Warm no-op calls were about 0.003 ms; SVG transfer was about 0.007–0.023 ms. The first no-op case also included cold initialization. Geometry probes paint a pre-encoded matrix using the same SVG writer; transfer echoes SVG bytes. Allocations and copies remain included, inputs differ, and these timings are not additive estimates of a production call. Encoding dominates the default plugin work. The actual notice traces showed warm plugin calls around 4.60–4.71 ms, with an 8.19 ms cold first call.

For default square codes, median PDF export was 0.61, 0.58 and 1.79 ms per code at 33, 129 and 513 bytes. At 513 bytes, dots and rounded modules used about 11.4–11.6 ms per code in export, while marker colors used 5.56 ms out of 176.74 ms total. Most of the extra cost of complex styles is in Typst geometry/content construction and layout. Protocol batching and small SVG-geometry changes do not address the dominant work identified here, and no current whole-command benefit was demonstrated for them. QR code and vendored WASM are unchanged.

Independent ZXing-C++ decoding of the exported PDFs, rasterized by PyMuPDF at 216 dpi, recovered all 110 expected payloads across the tested style/size cases. Codes were 8 cm wide for this check. The normal release tests also cover all correction levels, UTF-8, version 1/2 capacity transitions, version 40 limits, matrix/run/SVG agreement and customization option validation. These checks establish the tested cases; they do not establish readability at every printed size or with arbitrary logos.

## Unresolved scaling limits

- Every checkpoint and the final report still serialize all source rows. Doubling thresholds reduce repeated writes; the elapsed-time trigger means very long batches still repeat full serialization. This is not a general linear-scaling guarantee.
- Prepared notices, observed/effective findings and the full HTML buffer remain in memory. The 5,000-notice case still peaks near 2.34 GiB. Its final saved JSON is about 177.08 MB and HTML 97.03 MB. Browser behavior at much larger sizes was not measured.
- Long histories with many distinct dates incur repeated filtering as well as substantial native table layout. The 200-administration stress case is not the ordinary 1–8-administration notice mix.
- Dense payloads and complex QR styles remain more expensive than default RGB SVG codes. Their customization and decoding behavior are preserved; there is no new fast path with reduced options.
- No hour-long run, 100,000-row batch or history-plugin whole-command benefit is established. Do not combine obsolete estimates or overlapping profile spans with these current command results.

## Verification and reproduction

The release suite passed 41 tests, including the new clock/row checkpoint test, CLI failure and saved-run behavior, rendering contracts, PDF round trips and QR checks. Formatting, the locked release build and `typst-plugins/qr/build.sh --check` passed. Post-run checks separately established complete-record/HTML equivalence, every timed artifact fingerprint, early interrupted checkpoints, protected-copy passwords/content and styled PDF QR decoding.

See [whole-command measurement guidance](testing.md#measure-the-complete-command). Build the current serial executable with `cargo build --release --locked`; build the parsing comparison at the same source with `cargo build --release --locked --features lopdf/rayon`, preserving both executables. For the checkpoint comparison, use the recorded baseline source and the candidate source hashes in the data. Use identical CSV, assignments, project, fonts and timestamp; explicitly pass `--compile-workers 2 --encryption-workers 2 --bundle-workers 4 --progress off`. Alternate order for three pairs, time through process exit, and run acceptance after stopping the timer. Component and instrumented timings explain work; the paired uninstrumented commands establish the accepted performance change.
