# Measured notice throughput

The current CSV-first implementation and styled QR changes are measured on a
fictional cohort with median 19 history entries and long QR destinations. Four
balanced 1,000-row pairs show median wall reduction of 13.95% and CPU reduction of
10.66% for the QR changes, with no peak-memory regression. One 5,800-row matched
confirmation takes 358.61 versus 310.46 seconds; encryption is off. These figures
describe that workload, not a capacity guarantee for other notices or machines.

At 5,800 records the CSV pair is 3.28 MB, versus about 140 MB of old HTML and
bundle CSVs. Gnumeric's headless engine verifies all row-key joins and the expected
variant filter; import client identifiers as text to preserve leading zeros.
Whole saved-run recovery still exceeds the proposed two-second target. See the
[acceptance report](../developer_guide/performance_experiments.md) for individual
measurements, correctness checks, latency limits and reproducibility.

The remaining comparisons describe earlier revisions that generated HTML and
per-bundle CSVs. Their shorter histories, QR styles and encryption mix differ;
do not combine their times or percentages with the current experiment.

## Historical checkpoint and parsing comparisons

The following historical comparisons use the reduced pipeline below as their baseline. Three alternating paired commands at each batch size changed the report checkpoint schedule while retaining full passing-check details:

| Notices | Every 100 notices | Adaptive checkpoints | Elapsed reduction |
| --- | ---: | ---: | ---: |
| 1,000 | 25.20 s | 23.31 s | 7.5% |
| 5,000 | 175.83 s | 121.44 s | 30.9% |

At 5,000 notices, median process CPU time fell from 432.80 to 381.27 seconds. The highest process peak RSS was 2.34 GiB for both schedules. The final report, findings, source-row identity, routing, original PDFs and bundles matched; randomized encryption fingerprints and timings were excluded from record equality. Every run's artifact hashes were checked after timing.

The coordinator now saves after the first 100 notices, then at doubling row counts, or at the next completed row after 30 seconds since the previous successful save. Setup, slow rows and report writes can extend that interval. Final and caught-error reports remain independent. Interrupted snapshots can be older than with the previous 100-row schedule; the saved record retains the checkpoint evidence. See [recovery](getting_started.md) and [saved-run behavior](../developer_guide/architecture.md#save-runs-and-later-changes).

A separate three-pair comparison on the reduced pipeline retained serial `lopdf` parsing: median elapsed time was 25.31 seconds versus 26.48 with its internal Rayon pool. Serial parsing used 76.50 CPU seconds versus 83.44, with peak RSS 1.07 versus 1.04 GiB. Outer compilation, encryption and bundle workers stayed fixed at 2, 2 and 4.

Profiling, compact-detail experiments, history preparation versus native table layout, QR styles and payloads, and remaining limits are in the [experiment report](../developer_guide/performance_experiments.md). [Measurement data](../assets/current-pipeline-benchmark.json) includes individual runs, binary and source hashes, component profiles and acceptance results. These results apply to this fictional workload on a shared machine limited to four CPUs and 8 GiB RAM. The comparisons measure separate changes and their percentages must not be added to each other or to historical results.

## Earlier work-reduction comparison

The earlier work-reduction comparison created **1,000 notices in a median 25.29 seconds**, compared with **34.75 seconds** for the previously integrated bounded-worker version. Three alternating paired runs used a shared machine limited to four CPUs and 8 GiB RAM. Each command created 2,000 original pages, 1,000 AES-256 revision 6 protected copies and ten PDF/CSV bundles, including 700 QR-bearing notices.

| Measurement | Previously integrated workers | Reduced work |
| --- | ---: | ---: |
| Three runs, seconds | 33.83, 34.75, 35.22 | 25.29, 24.19, 25.49 |
| Median command time | 34.75 seconds | 25.29 seconds |
| Median child CPU time | 118.10 seconds | 76.11 seconds |
| Highest sampled process memory | 1.28 GiB | 1.07 GiB |

Elapsed time fell **27.2%**, and aggregate CPU work fell **35.6%**. The equivalent rate is about **142,000 notices/hour for batches of this size**. Neither an hour-long run nor a single 100,000-row batch has been measured.

Both versions used two compilation workers, two encryption workers and four bundle workers. The timed interval includes startup, preparation, compilation, retained notice checks, original writes, protection, grouping, fingerprints and final reports. Builds, profilers and acceptance checks were outside timing; one exclusive lock covered all six measured commands and their comparisons. Filesystem caches were warm. The fixture was recreated from Template's ten fictional clients after the earlier temporary measurement files were lost; compare these paired runs with each other rather than combining their samples with earlier experiments.

Every run completed all artifacts with identical full findings, render evidence, routing, prepared facts, original PDFs and bundled PDFs. All 3,010 recorded artifact hashes were recomputed for each run. Protected copies preserve independent encryption randomness. A separate saved-output acceptance check exercises passwords, encryption settings, decrypted content and bundle membership outside the timed command.

The baseline is [2fedadb](https://github.com/WDGPH/ImmuKnow/commit/2fedadb615762f84e4d37b201920be0d46f9c0b3); the implementation is [e7a8de1](https://github.com/WDGPH/ImmuKnow/commit/e7a8de1c9c54073b02a44c6e36f5ba646d3faf8a). [Measurement data](../assets/work-reduction-benchmark.json) records binary and source hashes, exact workload and font hashes, individual results and acceptance findings. See [testing](../developer_guide/testing.md#measure-the-complete-command) for timing guidance.

## Initial bounded-worker comparison

The standalone Rust pipeline created **1,000 personalized notices in a median 34.93 seconds** on a shared machine limited to four CPUs and 8 GiB RAM. Each command produced 2,000 original pages, 1,000 separate AES-256 revision 6 protected copies, and 10 PDF/CSV bundles. This is equivalent to about **103,000 notices per hour for batches of this size**; an hour-long run and a single 100,000-row batch have not been measured.

Three paired whole-command measurements compared the previous single compiler with two persistent compilers and two encryption workers. The coordinator still commits notices in source-row order, and a fixed window limits compilation to four outstanding notices. In this measured version, the shared Typst cache was swept every two committed rows with half the previous generation limit. Four bundle workers run afterward.

| Measurement | Previous pipeline | Bounded compilation |
| --- | ---: | ---: |
| Three runs, seconds | 52.28, 52.57, 51.32 | 34.93, 35.21, 33.64 |
| Median command time | 52.28 seconds | 34.93 seconds |
| Highest sampled process memory | 1.19 GiB | 1.29 GiB |
| Median child CPU time | 110.03 seconds | 118.60 seconds |

Elapsed time fell **33.2%** while aggregate CPU work rose about 7.8%. Compilation and encryption each default to two workers when at least four CPUs are available to the process, otherwise one. Explicit worker options are described in the [command reference](../developer_guide/cli.md).

## What was held constant

The input repeated ten fictional Template cases equally, with unique client IDs, English and French notices, and 700 QR codes. Both versions used the same project, assignments, fonts, timestamp, clinical mappings, security settings and checks. Every run completed all requested artifacts with identical findings and routing. All 1,000 prepared-fact files and original PDFs had identical SHA-256 hashes across both versions; protected copies retain independent encryption randomness.

For this historical comparison, the timed interval included process startup, input preparation, compilation, evidence and PDF checks, original writes, encryption and password verification, bundle assembly and final reports. Builds, profiling and comparison checks were outside that interval. Runs were sequential, in alternating paired order, with warm filesystem caches and an exclusive lock excluding other planned benchmark work.

The baseline executable contains the QR implementation at `c5d8b5a`; the concurrency implementation is [2fedadb](https://github.com/WDGPH/ImmuKnow/commit/2fedadb615762f84e4d37b201920be0d46f9c0b3). The local measurement commit `e3509c5` contains the same implementation; the data records source-file hashes as well as executable hashes. [Measurement data](../assets/throughput-benchmark.json) records exact binary and input hashes, source-file hashes, fonts, worker settings, per-run CPU time, memory and stage timings. See [testing](../developer_guide/testing.md#measure-the-complete-command) to repeat a whole-command comparison, and [architecture](../developer_guide/architecture.md) for ownership and worker boundaries.

## Why bounded workers

Stage timers and Typst timing traces identified serial notice compilation as the main scheduling bottleneck. Callgrind instruction profiling also showed substantial hashing work in PDF protection. That worker-only change overlapped existing implementations and retained PDF inspection and password verification. Subsequent changes reduce repeated work while retaining content evidence and successful file operations. Profiling runs were separate from the uninstrumented measurements above.

The worker count remains deliberately small: each compiler retains its own document world, and additional workers compete with encryption for CPU and memory. Source-order commits and a four-notice window bound the extra in-flight work. The measured improvement comes with higher aggregate CPU use and memory, as shown above.

## Reducing repeated work

Production now trusts successful PDF export from the pinned Typst library, using the page count from that same compiled document. Encryption checks the constructed AES-256 revision 6 settings, password preparation and unchanged page count before writing. Bundling checks its assembled page tree before saving. It does not reopen the newly saved output to authenticate a password or recount pages. Saved-file password refusal/access and content preservation remain round-trip regression and acceptance tests. See [PDF checks and review](pdf_validation.md#what-core-checks-during-a-run) for the boundary between these checks.

PDF writers also compute SHA-256 as bytes are written, avoiding a second full-file read of protected copies and bundles. Other changes remove a repeated manifest scan during preparation, avoid cloning owned JSON arrays, buffer prepared JSON output, stream saved-record JSON, and sweep the shared Typst cache every five committed rows with a maximum generation age of two. Disabling `lopdf`'s optional inner parsing pool keeps small-PDF parsing on the existing notice and bundle workers. SHA-256 dependencies are consolidated without claiming a measured hashing speed improvement.

A three-compiler experiment was slower than two on this four-CPU workload; the existing limit remains. A faster native hashing backend was not adopted because it required a private PDF-library fork and additional native build dependencies. Small history-projection and file-cache experiments did not demonstrate a whole-command improvement. The history table still uses Typst's native layout, with agent-to-disease mappings supplied as project data.

## Applying the result

These measurements establish repeatable improvement for this 1,000-row fixture, not a capacity guarantee for other documents or machines. Page counts, history lengths, font choices, encryption, storage and available CPUs affect performance. The earlier comparisons used a complete saved-record and HTML rewrite every 100 notices. The adaptive schedule above reduces repeated serialization, but each checkpoint still writes the canonical record and large single batches retain different reporting and memory costs. Measure the intended batch size and template mix before extrapolating capacity.

An [earlier profile](../assets/notice-timings.json) used six fictional cases and the prior sequential workflow. Its activity shares describe that older workload and should not be added to the overlapping worker times above.
