# Testing

Tests should prove the notice workflow at its real boundaries: normalized client
records, resolved assignments, structured render inputs, compiled PDFs, and
complete downstream accounting.

## Run the checks

Install the locked development tools and Typst **0.15.1**:

```bash
uv sync --all-groups
uv run ty check
uv run pytest
uv run pre-commit run --all-files
```

Use `TYPST_BIN` to select a different executable path for the same pinned version.
The CI test job installs 0.15.1 from its versioned official release URL and runs
the full suite. Native acceptance tests fail when the compiler is unavailable;
they never substitute a mock or silently skip.

Use markers for focused feedback:

```bash
uv run pytest -m unit
uv run pytest -m integration
uv run pytest -m e2e
uv run pytest --cov=pipeline --cov-report=html
```

## Test boundaries

Unit tests cover normalization, eligibility, assignment aliases, configuration,
and precise failure diagnostics. Use ordinary records rather than deeply mocked
objects when testing data contracts.

Integration tests compile real maintained templates from ordinary JSON. Their
temporary directories deliberately live outside the checkout and include spaces
and Unicode. Never change Typst's file root to the filesystem root to make a test
pass.

| Test module | Evidence |
|---|---|
| `test_native_templates.py` | Every maintained entry point; baseline prose, history, identity, and markers; direct language/version assertions; missing agents; literal punctuation |
| `test_native_pipeline.py` | Mixed cohorts; assigned/default language in both directions; QR and encryption options; size/school/board bundles; stale and missing outputs; failure propagation |
| `test_custom_templates.py` | External custom directories, single-language PHUs, isolation, unsafe identifiers, and actionable Python-template migration errors |
| `test_installed_package.py` | Wheel and sdist contents, clean installation with locked dependencies, read-only installed resources, unrelated working directory, packaged and custom resources |
| `test_full_pipeline.py` | Complete fixed-mode English and French CLI paths |

Mock subprocess calls only when testing compiler discovery or version diagnostics.
A mocked successful compiler call cannot prove rendering, assertions, layout, or
the handling of failed jobs.

Each test should state the user-visible behavior it protects. Prefer assertions
about structured values, PDF contents, expected-client coverage, and errors over
assertions that repeat the implementation.

## Migration provenance and baseline

The native migration starts from PR #214, `feat/notice-version`, verified at
`14b24ae85a18746103baaca31da1b84a96ff47dc` on 2026-10-08. Work is on its child
branch `no-more-python-generator`; the intended merge target is
`feat/notice-version`, not `main`.

The official release API identified **0.15.1** as the latest stable compiler at
the start of the work. The compiler pin and baseline capture were committed
separately from the template migration. The
[0.15 migration guide](https://typst.app/docs/changelog/0.15.0/#migration-guide)
calls out layout baselines, list alignment, and forward-slash path handling.

Before removing the Python generators, seven synthetic cases were compiled with
both Typst 0.14.2 and 0.15.1. Their client records and extracted PDF text are
retained in `tests/fixtures/notice_baseline/`. Both compiler versions produced
the same text and page counts; one text copy is retained. The capture used the
repository configuration with `preprocess.show_validity_markers: true`, synthetic
QR links/images, dose labels, and the repository's sample assets.

The pre-change full suite reported **625 passed, 2 skipped**. The pre-change type
check reported **51 diagnostics**. That was a baseline failure, not a passing
check. The migration replaced tests of deleted source serialization and dynamic
imports with tests of native compilation; raw test counts are not a coverage
comparison.

## Final local checks

After the native migration and removal of obsolete code and tests, the full suite
reported **514 passed, no skips** on 2026-10-08. Type checking, repository-wide
Ruff lint, formatting of all changed Python files, and the strict documentation
build passed. The suite includes the installed-wheel CLI and library checks with
read-only package resources.

Local coverage measured **94.7% of executable lines** and **89.1% of branches**
(93.4% combined). Coverage now traces CLI subprocesses through
`patch = ["subprocess"]`; the earlier 82% report omitted those processes and is
not a comparable measure of test quality. Generate the local report with:

```bash
uv run pytest --cov=pipeline --cov-branch --cov-report=html
```

Open `htmlcov/index.html` to inspect gaps. Uncovered paths include QR error
recovery, interactive CLI choices, thin wrappers, and invalid external artifact
or configuration branches. The cleanup retained real rendering and failure
checks, removed tests for retired APIs and repeated implementation assertions,
and added checks for duplicate or missing jobs and encryption/client mismatches.
Coverage was used to review these boundaries, not as a target for adding tests
to every line. These are local results; no hosted CI run is claimed.

## Semantic and visual comparison

The native templates reproduce the captured text exactly for every case. All
**19 pages** were also rasterized at **90 DPI** and compared in two separate pairs:

1. Legacy renderer versus native templates, both on Typst 0.15.1.
2. Legacy renderer on Typst 0.14.2 versus the same source on Typst 0.15.1.

Both comparisons produced **zero changed pixels on every page**. This checks the
captured cases and raster resolution; it is not a promise about arbitrary PHU
templates, fonts, or inputs, and does not compare PDF bytes.

| Synthetic case | Pages | Legacy 0.15.1 compilation | Native 0.15.1 compilation |
|---|---:|---:|---:|
| Legacy English | 3 | 0.374 s | 0.390 s |
| Legacy French | 3 | 0.381 s | 0.376 s |
| Versioned overdue English | 2 | 0.381 s | 0.370 s |
| Versioned overdue French | 3 | 0.384 s | 0.367 s |
| Affirmative English | 2 | 0.375 s | 0.415 s |
| Long history | 3 | 0.415 s | 0.397 s |
| Long address | 3 | 0.382 s | 0.399 s |

These are single local compilation observations, excluding preparation.
They do not establish a performance improvement.

Visual inspection covered the English and French letters, affirmative letter,
long-address block, signature placement, and history continuation pages. Prose,
branding, validity symbols, QR images, page numbering, and validation markers
were retained. Several baseline notices already occupy three pages; the French
overdue signature can move to page two. Those are preserved baseline limitations,
not new migration defects or a claim of universal two-page output.

Generated baseline PDFs and source are retained locally under
`output/native_typst_baseline/`. Native PDFs, page images, and comparison
measurements are under `output/native_typst_review/`. These synthetic review
artifacts are ignored by Git; the source records and semantic baselines are
committed. Regenerate current notices through the native integration tests.
