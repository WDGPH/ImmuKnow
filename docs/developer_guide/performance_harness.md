# Fictional performance acceptance

These maintainer helpers are separate from the standalone application. They use
Python 3.12 or later; only `verify_pdf_membership.py` additionally needs PyMuPDF.
The isolated Rust operation probe uses Linux process CPU clocks. None of these
tools is needed to create or review notices.

Use an exact Core executable and a compatible fictional Template checkout. Keep
builds, profilers, PDF parsing and spreadsheet applications outside native command
timing. Record the revisions, executable/resource/font hashes, worker settings,
filesystem/cache conditions and every individual measurement. Do not use real
client data or commit generated runs.

## Create and measure a cohort

From the Core checkout:

```sh
python scripts/performance/workload.py /tmp/fictional-cohort \
  --template-project ../ImmuKnow-Template --rows 1000 --style styled
/path/to/immuknow project sync --project /tmp/fictional-cohort/project --replace
python scripts/performance/measure.py measure /path/to/immuknow \
  /tmp/fictional-cohort /tmp/new-trial
```

The generator copies authored Template notices/configuration, creates unique
fictional clients and QR destinations, and freezes the resulting input hashes.
It uses two English notice variants, varying history lengths, 32 schools, school
and variant grouping, source-independent name/DOB sorting, two compilation
workers and encryption off. Its settings patches deliberately require the
maintained Template layout; it is not an importer for arbitrary projects.
`styled` uses distinct finder/alignment colors to exercise the styled grid;
`svg` and `runs` provide separate default RGB and CMYK fast-path contexts.

`measure.py` measures the complete process through exit with Linux `wait4`,
including CPU, peak native RSS, page faults and block I/O. Output is created in a
new directory. `stdout.txt` contains the canonical record path; inspect the exit
status before interpreting a time. Builds, project synchronization and checks
are outside that interval. Block-operation counters are OS accounting, not an
exact measurement of physical storage traffic.

Verify after timing:

```sh
python scripts/performance/measure.py verify /path/to/run.json \
  /tmp/fictional-cohort /tmp/first-verification.json
python scripts/performance/measure.py verify /path/to/paired-run.json \
  /tmp/fictional-cohort /tmp/paired-verification.json \
  --expected /tmp/first-verification.json
python scripts/performance/verify_pdf_membership.py /path/to/run.json \
  /tmp/physical-page-verification.json
```

The first verifier is deliberately limited to these successful, grouped,
unprotected cohorts. It hashes every original and bundle, compares source facts,
observed/effective finding semantics, retained source evidence, routing and
membership, and checks the selected CSV generation. It understands the historical
saved-run v1 baseline only for this experiment; the application does not load old
runs. Successful layout arithmetic and editor geometry intentionally removed by
v2 are excluded from the semantic comparison. It writes a verification manifest
and compressed canonical record, and never deletes a run.

The independent PyMuPDF verifier reads actual page counts and inclusive bundle
ranges, then compares each bundled page's decoded content streams, extracted
text, dimensions and URI rectangles with the original page. Run it on retained
outputs outside timing. Keep these manifests outside Git; publish sanitized
aggregate results and their limits instead.

For QR attribution, build both arms from the same isolated source path and Cargo
target, with identical reporting code, changing only `qr-encode.typ` and
`qr-style.typ`. Rebuild byte-identical controls to check source/resource tracking,
then use balanced alternating pairs. The complete historical reporting baseline
is a separate comparison. Do not add separately measured percentage gains.

## Separate saved-record work

`reporting_benchmark.rs` calls the actual library checkpoint/publication functions
on an already loaded record. Copy it into `examples/` in an isolated source
snapshot and build it with that snapshot's locked release dependencies. Keep the
example outside the working checkout so it is not part of normal application
builds. Then run:

```sh
/path/to/reporting_benchmark checkpoint /path/to/run.json /tmp/new-checkpoint
/path/to/reporting_benchmark publish /path/to/run.json /tmp/new-export
```

Each output directory must be new. These commands operate on copies of the loaded
record, leaving the input run untouched. Internal wall/process CPU clocks exclude
loading; the process high-water RSS includes it. Publication includes canonical
state saves, both CSV streams and selection of the export pointer. The probe does
not measure CSV streaming alone and does not validate absent PDF files in its
scratch output.

Measure real `warnings RUN --refresh` separately. A valid selected export pair can
be reused without regeneration. To test recovery, preserve a pair outside the
run, simulate missing files, refresh under the native lock, verify unchanged
semantic revision/facts/reviews and the new selected pair, then restore the older
immutable generation. Never alter another person's run for a benchmark.

## Separate JSON reading

`json_read_benchmark.rs` measures the public strict `read_json<Value>` boundary.
Copy it into an isolated snapshot's `examples/`, build with the same locked
release dependencies, then run:

```sh
/path/to/json_read_benchmark /path/to/fictional/run.json
```

The internal clock includes file loading and recursive duplicate-field checks.
Canonical content serialization and hashing occur after that clock. Compare the
content hashes as well as all individual read times; process high-water memory is
sampled immediately after reading. `tests/json_io.rs` owns typed nested-value and
recursive duplicate-key correctness, including escaped aliases. An optimization
must preserve that boundary; ordinary permissive JSON parsing is not an
acceptable comparison arm for the supported application.
