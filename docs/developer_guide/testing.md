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

The PDF fixtures also require FreeFont TTF **20120503-10build1**. Font releases
can change line wrapping even when the family name remains `FreeSans`. The
`Install pinned notice fonts` step in `.github/workflows/test.yml` downloads
that package from Ubuntu's archive, verifies its SHA-256 checksum, and installs
its fonts in `/usr/share/fonts/truetype/freefont/`. Use those same font files
for local layout comparisons. To exclude unrelated system fonts:

```bash
TYPST_FONT_PATHS=/usr/share/fonts/truetype/freefont \
TYPST_IGNORE_SYSTEM_FONTS=true uv run pytest
```

Keep exact text and page-boundary comparisons. A deliberate font upgrade needs
layout review before changing the fixtures; a different local font installation
is not a reason to rewrite expected output.

Use markers for focused feedback:

```bash
uv run pytest -m unit
uv run pytest -m integration
uv run pytest -m e2e
uv run pytest --cov=pipeline --cov-report=html
```

## Test boundaries

Unit tests cover normalization, eligibility, assignment conflicts, configuration,
and precise failure diagnostics. Use ordinary records rather than deeply mocked
objects when testing data contracts.
Assignment tests also check that each manifest row has a valid `version_id` and
that an explicit input `version_id` agrees with it.

Integration tests compile real maintained templates from ordinary JSON. Their
temporary directories deliberately live outside the checkout and include spaces
and Unicode. Never change Typst's file root to the filesystem root to make a test
pass.

| Test module | Evidence |
|---|---|
| `test_native_templates.py` | Every maintained entry point; baseline prose, history, identity, and markers; direct language/version assertions; missing agents; literal punctuation |
| `test_native_pipeline.py` | Mixed cohorts; assigned/default language in both directions; QR and encryption options; size/school/board bundles; stale and missing outputs; failure propagation |
| `test_custom_templates.py` | External custom directories, single-language PHUs, isolation, unsafe identifiers, and missing native entry points |
| `test_installed_package.py` | Wheel and sdist contents, clean installation with locked dependencies, read-only installed resources, unrelated working directory, packaged and custom resources |
| `test_full_pipeline.py` | Complete fixed-mode English and French CLI paths |

Mock subprocess calls only when testing compiler discovery or version diagnostics.
A mocked successful compiler call cannot prove rendering, assertions, layout, or
the handling of failed jobs.

Each test should state the user-visible behavior it protects. Prefer assertions
about structured values, PDF contents, expected-client coverage, and errors over
assertions that repeat the implementation.

## Review template changes

The native template tests compile the maintained entry points with synthetic
records. Their fixtures in `tests/fixtures/notice_baseline/` protect notice text
and page counts. Keep those assertions current when approved wording or layout
changes. Review representative PDFs for branding, QR images, validity symbols,
page numbering, history continuation, signature placement, long records, and
long addresses. A text fixture cannot show a visual layout problem.

For a PHU template, use the same cases with that PHU's assets and wording. Check
envelope-window measurements and review the resulting PDFs before use. Compilation
and validation prove only the records and templates exercised by the run.

To inspect coverage while changing pipeline behavior, run:

```bash
uv run pytest --cov=pipeline --cov-branch --cov-report=html
```

Open `htmlcov/index.html` and use the gaps to find important untested behavior.
