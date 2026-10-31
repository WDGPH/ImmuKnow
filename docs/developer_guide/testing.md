# Testing

Run commands from the Core repository root. Studio has its own repository,
examples and browser checks. Core builds and tests do not require Node, Rust
or Pillow. Native QR checks decode grayscale page buffers directly with ZXing.

## Testing across the projects

Each project tests the behavior it owns and the handoffs it relies on. Repeated
checks should protect a distinct boundary, not meet a test-count or coverage quota.

| Project | What its tests protect |
| --- | --- |
| Core | Native input and validation rules, notice output, delivery and recovery, installed distribution, and supported Python versions. |
| [Studio](https://github.com/WDGPH/ImmuKnow-Studio/blob/main/docs/development.md) | Browser editing, UI, drafts, archives, and the browser-to-native project handoff. |
| [Template](https://github.com/WDGPH/ImmuKnow-Template/blob/main/README.md) | Local helper commands and paths, the client-data guard, shared-library integration, and one sample run through Core. It does not reimplement Core's input or output validation. |

Core and Studio deliberately run shared rendering contract cases against both
native and browser validators. Each implementation must accept and reject the
same evidence. Core owns comprehensive tests for the maintained notice families;
Studio's native handoff cases cover a customized English notice using both
selectors, a long French history spanning pages, and French source warnings
followed by saved-run rebundling.

Core's native Python matrix runs automatically. Studio's pull request and main
checks build the site and run unit tests, type checks and lint. Its full browser
and native suite is an intentional manual workflow with `full_tests=true` to
conserve GitHub Actions minutes; deployment does not depend on that manual suite.
Maintainers choose the higher-cost checks for riskier changes and releases, and
run relevant browser checks locally when UI, drafts, archives or resources change.
See Studio's development guide for the commands.

Template CI runs setup-only readiness checks and a single shared native sample
fixture through pytest on each of its three supported Python versions. It does
not also run `check.py --sample` in the same CI job. Studio's downloadable
project includes the helpers and `check.py --sample` for workstation readiness;
it does not include Template's maintainer pytest tests.

## Prepare a clean checkout

Install Git, uv, Python 3.11 or later, and native Typst 0.15.1. Put `typst` on
`PATH`, or set `TYPST_BIN` to its absolute path.

Notice tests use the FreeFont `20120503-10build1` release that Studio also ships.
Newer FreeSerif releases double accented capitals in PDF text, so French notices
fail the client details check. Use the same checksum-verified files as CI and
exclude other system fonts:

```bash
curl -fL https://archive.ubuntu.com/ubuntu/pool/main/f/fonts-freefont/fonts-freefont-ttf_20120503-10build1_all.deb \
  -o /tmp/notice-fonts.deb
echo "d1424c9d47b2a6bd0d5149ca66f2bab9b4365237bfbb6063659d961bab2f8ccb  /tmp/notice-fonts.deb" | sha256sum --check
dpkg-deb --extract /tmp/notice-fonts.deb /tmp/notice-fonts
export TYPST_FONT_PATHS=/tmp/notice-fonts/usr/share/fonts/truetype/freefont
export TYPST_IGNORE_SYSTEM_FONTS=true
```

If the archive no longer offers this package, update the pin here, in CI and in
Studio's fonts together.

```bash
uv sync --locked --all-groups
```

Native CI covers Linux with Python 3.11, 3.12 and 3.14. Other operating systems
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
