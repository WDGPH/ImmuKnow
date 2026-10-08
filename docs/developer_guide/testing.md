# Testing

Use tests to prove the complete notice workflow at its real boundaries:
canonical clients, resolved assignments, structured render inputs, compiled
PDFs, and complete downstream accounting.

## Run the checks

Install locked dependencies and Typst 0.15.1:

```bash
uv sync --all-groups
uv run ty check
uv run pytest
uv run pre-commit run --all-files
uv run --group docs mkdocs build --strict
```

Set `TYPST_BIN` to the pinned compiler if it is outside `PATH`. Native tests
require the real compiler. The CI job installs a checksum-verified FreeFont TTF
`20120503-10build1` package; font metrics affect notice wrapping and page
geometry. Use the same files for local layout checks and exclude unrelated
system fonts:

```bash
TYPST_FONT_PATHS=/usr/share/fonts/truetype/freefont \
TYPST_IGNORE_SYSTEM_FONTS=true uv run pytest
```

For focused feedback:

```bash
uv run pytest -m unit
uv run pytest -m integration
uv run pytest -m e2e
uv run pytest --cov=immuknow --cov-branch --cov-report=html
```

Coverage gaps guide test choices; coverage percentage is not a reason to keep
obsolete interface tests. Unit tests should protect normalization,
eligibility, assignment conflicts, malformed configuration, and precise
diagnostics. Integration tests should compile maintained Typst entry points
and verify mixed cohorts, manifest filenames confined to the selected tree,
one-file cohort selection,
disease and agent notice assignments, QR links, encryption, bundles,
installed-wheel resources, path isolation, and failure propagation. Mock a
compiler only for discovery or version diagnostics; mock success cannot prove
PDF behavior.

## Review rendered notices

Keep semantic text checks separate from layout checks. PDF extraction may vary
in inconsequential whitespace, so semantic comparisons normalize that
whitespace while asserting the complete wording. Separately check page
boundaries/counts, chart contents, signature placement, and envelope-window
measurements. Native assertions must reject wrong language, wrong version,
and missing agents for the agent-based notice. Typst syntax inside client
strings must remain literal data.

Compile and inspect English, French, affirmative, long-record, and
long-address cases. Check branding, QR images, validity symbols, page
numbering, history continuation, and visible date and dose wording.
Changing a compiler or font requires layout review before fixture changes.
Use synthetic records only. PHU-specific templates need the same review with
their own assets and wording.

Tests that fail on an error-level validation finding or incomplete output set
must remain meaningful; do not update a snapshot or weaken an assertion merely
to obtain a pass.
