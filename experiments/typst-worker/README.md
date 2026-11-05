# Persistent Typst worker experiment

This proof of concept keeps official Typst 0.15.1 compiler state in a native
process. Core's production pipeline still invokes the stock CLI per notice.
This directory adds no runtime dependency, packaged executable or public option.
It uses neither `typst watch` nor the unofficial Python binding.

## Build and check

From this directory, build with the pinned Rust toolchain:

```bash
cargo build --locked --release --jobs 1
cargo fmt --check
```

The executable is `target/release/immuknow-worker-probe`. Its first build compiles
Typst and can take several minutes. The lock freezes official compiler, PDF and
tooling crates. It is not a byte-identical build of the upstream CLI executable.

From the Core checkout, install its locked development dependencies and run the
focused Linux check. It requires stock Typst 0.15.1 and FreeFont under
`/usr/share/fonts/truetype/freefont`; choose a new output directory each time:

```bash
uv sync --all-groups --locked
uv run --locked python experiments/typst-worker/check.py \
  --worker experiments/typst-worker/target/release/immuknow-worker-probe \
  --out /tmp/immuknow-worker-check
```

The check compares default fonts, math, page appearance, links, outlines,
metadata and unrelated attachments with a fresh CLI compilation. It exercises
input removal, changed timestamps, edited/deleted/restored imports and images in
one retained worker. Missing or malformed reports pass through Core's existing
caller and must retain a readable PDF. A stopped child and a large request check
that the parent deadline includes blocked transmission. These are maintainer
checks; ordinary Core tests and installation do not build this executable.

## Interface

Start `immuknow-worker-probe PROJECT_ROOT`. Send one JSON object per line on stdin
and read one response per line on stdout. Process one request at a time:

```json
{"id":"notice-1","inputs":{"immuknow-template-path":"/letter.typ"},"notice":{"row_key":"notice-1"},"output":"/absolute/path/notice.pdf","timestamp":1793842452,"direct_report":true}
```

`inputs` replaces the complete `sys.inputs` dictionary each request. The host
overrides `data` with a stable virtual JSON file containing `notice`. Each response
echoes `id` and includes `ok`, compiler diagnostics, an optional error and reports.
Output directories must already exist. Project files are resolved through
official `FileStore`/`FsRoot`; package roots are rejected and no downloader is
configured.

The default mode creates Core's existing internal evidence attachment.
`direct_report: true` returns placed `<immuknow-report>` values separately and
exports the PDF without adding that attachment. A template-created root attachment
named `immuknow-evidence.json` is rejected, preserving the name reservation already
imposed by the CLI wrapper. Report validation remains Python's responsibility.

`transport.py` supplies the small Python process interface used by the check.
Its I/O thread handles blocking pipes while the caller enforces one deadline.
Close the session after its batch. It is an experimental adapter, not a supported
Core API.

## State and adoption limits

A worker retains fonts and the official file store for one project root and
batch. Every request resets file state, replaces inputs/data/time, compiles once,
exports the PDF and evicts memoized work older than ten generations. Font
discovery follows CLI order: system, upstream embedded fonts, explicit paths.
The CLI environment variables for font paths and ignored providers are honored.
Restart the worker between batches instead of watching for installed font changes.
Cache eviction is not a hard memory cap.

Production adoption still requires supported-platform release artifacts and
licenses, validation of the actual worker's compiler/protocol identity, and
integration with existing timeout and independent-notice failure handling.
Worker death, failed exports/writes, and varied templates/assets need checks at
that integration boundary. Native and browser compiler/font compatibility must
remain explicit. No automatic backend fallback or installation behavior is
implemented here.
