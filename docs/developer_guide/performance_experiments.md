# Profiling the reduced pipeline

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

The new schedule saves at 100 processed notice rows, then doubles the next row threshold after each successful save. It also saves at the next row boundary after 30 seconds since the previous successful save. The notice coordinator starts the clock when it begins processing worker results and resets it after writing; setup, a slow row or a report write can extend the wall-clock gap. Setup, final and caught-error reporting remain independent. This removes full serialization passes while keeping one understandable `run.json` and its complete escaped HTML view. There is no extra journal, format change or resume command.

The recovery tradeoff is less frequent intermediate snapshots. Deterministic clock tests cover row and elapsed-time thresholds. A fresh forced-interruption check observed both the 100- and 200-row snapshots, verified all 1,000 source rows and every listed original-PDF link/hash, then confirmed that the incomplete folder and readable reports remained after termination.

### Retain the existing allocation changes

Owned JSON moves, streamed report JSON, buffered preparation output and single-pass HTML escaping remain unchanged. Their individual historical savings were not re-added or estimated. The current profile supports removing repeated writes; it does not reveal a regression requiring those implementations to be reverted.

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
