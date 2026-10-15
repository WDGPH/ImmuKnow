# Testing

Run commands from the Core repository root. Studio has its own repository,
examples and browser checks. Core builds and tests do not require Node or Rust.

## Prepare a clean checkout

Install Git, uv, Python 3.10 or later, and native Typst 0.15.1. Put `typst` on
`PATH`, or set `TYPST_BIN` to its absolute path. Install system FreeSans and
FreeSerif fonts for notice tests (`fonts-freefont-ttf` on Debian/Ubuntu).

```bash
uv sync --locked --all-groups
```

Native CI covers Linux with Python 3.10, 3.12 and 3.14. Other operating systems
are not covered by that suite.

## Run the checks

```bash
uv run --locked ty check
uv run --locked ruff check --no-fix .
uv run --locked ruff format --check .
uv run --locked pytest
uv run --locked pre-commit run --all-files
uv run --locked python docs/generate_schema_docs.py
uv run --locked --group docs mkdocs build --strict --site-dir /tmp/immuknow-docs-check
```

For focused feedback, select affected files or use `-m unit`, `-m integration`
or `-m e2e`. Run the full Python suite before handoff. Coverage helps find
untested decisions; it does not establish complete workflow behavior:

```bash
uv run --locked pytest --cov --cov-branch --cov-report=term-missing --cov-report=xml
```

For local documentation editing:

```bash
uv run --locked --group docs mkdocs serve --dev-addr 0.0.0.0:8000
```

## What the tests protect

| Boundary | Coverage | Tests |
| --- | --- | --- |
| Input preparation | Original row identity, complete histories, disease mappings, source warnings, ambiguous assignments and malformed configuration | `tests/unit/`, `test_pipeline_contracts.py`, `test_input_rejection.py` |
| Typst presentation | Placed findings, English/French wording, client details, QR destinations, continuation and suspension layout | `test_typst_package.py`, `test_native_templates.py`, `test_render_evidence.py` |
| Native runs | Both selectors, independent failures, setup failures, retained facts and authoritative run records | `test_run_accounting.py`, `test_native_deadlines.py`, `tests/e2e/` |
| Delivery | Encryption, warning review, page identity, fixed page counts, saved-run recovery and process locks | `test_delivery_checks.py`, `test_encrypted_pdfs.py`, `test_saved_run_delivery.py`, `test_run_lock.py` |
| Installed distribution | Relocated wheel, public resource access, provenance and operation without checkout imports or browser tooling | `test_installed_package.py`, `test_native_build.py` |

Payload and report schemas define the rendering contract. Core's validation
cases live in `tests/fixtures/render-contract.json`; Studio maintains its own
copy of useful contract cases and its own fictional scenarios.

Native build tests compare source bytes before and after packaging, rebuild a
source archive without Git or Studio, and verify native file hashes. The
installed-wheel journey reads the resource API from an unrelated directory
before generating and reviewing notices with packaged and external resources.

Native compilation uses system fonts and refuses ambient Typst packages before
network access. Component tests reject changed, missing, extra, renamed and
linked library files even if project-declared hashes have been rewritten.

Failed applicable checks retain useful originals for diagnosis and prevent
release. Individual warning acceptance is tied to the run, row, original PDF,
evidence and effective rules. An accepted warning cannot release a failed batch.
Saved-run tests cover concurrent attempts, interrupted replacement, retained
bundles and earlier decisions. Encryption tests verify AES-256 revision 6 with
independent PDF readers and preserve originals. Studio's separate browser suite
also checks representative encrypted notices in Chromium's ordinary PDF viewer.

Inspect representative English/French PDFs after presentation or compiler/font
changes: include long names, addresses and histories, QR links, signatures,
envelope windows and the one-page suspension order. This repository split does
not change notice presentation or validation policy.
