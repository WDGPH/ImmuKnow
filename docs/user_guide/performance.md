# Measured notice throughput

The standalone Rust pipeline created **1,000 personalized notices in a median 34.93 seconds** on a shared machine limited to four CPUs and 8 GiB RAM. Each command produced 2,000 original pages, 1,000 separate AES-256 revision 6 protected copies, and 10 PDF/CSV bundles. This is equivalent to about **103,000 notices per hour for batches of this size**; an hour-long run and a single 100,000-row batch have not been measured.

Three paired whole-command measurements compared the previous single compiler with two persistent compilers and two encryption workers. The coordinator still commits notices in source-row order, and a fixed window limits compilation to four outstanding notices. The shared Typst cache is swept every two committed rows with half the previous generation limit. Four bundle workers run afterward.

| Measurement | Previous pipeline | Bounded compilation |
| --- | ---: | ---: |
| Three runs, seconds | 52.28, 52.57, 51.32 | 34.93, 35.21, 33.64 |
| Median command time | 52.28 seconds | 34.93 seconds |
| Highest sampled process memory | 1.19 GiB | 1.29 GiB |
| Median child CPU time | 110.03 seconds | 118.60 seconds |

Elapsed time fell **33.2%** while aggregate CPU work rose about 7.8%. Compilation and encryption each default to two workers when at least four CPUs are available to the process, otherwise one. Explicit worker options are described in the [command reference](../developer_guide/cli.md).

## What was held constant

The input repeated ten fictional Template cases equally, with unique client IDs, English and French notices, and 700 QR codes. Both versions used the same project, assignments, fonts, timestamp, clinical mappings, security settings and checks. Every run completed all requested artifacts with identical findings and routing. All 1,000 prepared-fact files and original PDFs had identical SHA-256 hashes across both versions; protected copies retain independent encryption randomness.

The timed interval includes process startup, input preparation, compilation, evidence and PDF checks, original writes, encryption and password verification, bundle assembly and final reports. Builds, profiling and comparison checks were outside that interval. Runs were sequential, in alternating paired order, with warm filesystem caches and an exclusive lock excluding other planned benchmark work.

The baseline executable contains the QR implementation at `c5d8b5a`; the concurrency implementation is [2fedadb](https://github.com/WDGPH/ImmuKnow/commit/2fedadb615762f84e4d37b201920be0d46f9c0b3). The local measurement commit `e3509c5` contains the same implementation; the data records source-file hashes as well as executable hashes. [Measurement data](../assets/throughput-benchmark.json) records exact binary and input hashes, source-file hashes, fonts, worker settings, per-run CPU time, memory and stage timings. See [testing](../developer_guide/testing.md#measure-the-complete-command) to repeat a whole-command comparison, and [architecture](../developer_guide/architecture.md) for ownership and worker boundaries.

## Why bounded workers

Stage timers and Typst timing traces identified serial notice compilation as the main scheduling bottleneck. Callgrind instruction profiling also showed substantial hashing work in PDF protection. The workers overlap those existing implementations; they do not replace Typst layout, change cryptography or omit evidence, PDF inspection, password verification or durable writes. Profiling runs were separate from the uninstrumented measurements above.

The worker count remains deliberately small: each compiler retains its own document world, and additional workers compete with encryption for CPU and memory. Source-order commits and a four-notice window bound the extra in-flight work. The measured improvement comes with higher aggregate CPU use and memory, as shown above.

## Applying the result

These measurements establish repeatable improvement for this 1,000-row fixture, not a capacity guarantee for other documents or machines. Page counts, history lengths, font choices, encryption, storage and available CPUs affect performance. The existing report checkpoints rewrite the complete saved record and HTML every 100 notices; much larger single batches therefore have different reporting and memory costs. Measure the intended batch size and template mix before extrapolating capacity.

An [earlier profile](../assets/notice-timings.json) used six fictional cases and the prior sequential workflow. Its activity shares describe that older workload and should not be added to the overlapping worker times above.
