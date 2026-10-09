# Testing

Use tests to prove the complete notice workflow at its real boundaries:
prepared client records, selected notices, structured render inputs, compiled
PDFs, and complete downstream accounting.

## Run the checks

Install locked dependencies and Typst 0.15.1:

```bash
uv sync --all-groups
uv run ty check
uv run pytest
uv run pre-commit run --all-files
uv run python docs/generate_schema_docs.py
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
measurements. Compile default/custom windows and long addresses at the safe-area
boundary; missing evidence and overflow must fail error-level validation.
Check actual rendered text displacement when changing physical coordinates,
and reject Typst convergence warnings in layout tests. Native assertions must reject wrong language, wrong version,
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

Check that one run log covers preparation and later stages, and that both
success and failure remove the run handler without changing caller logging.
Failure tests should also verify that incomplete output is not delivered.

## Browser and static-site gates

Install Node.js 24, Rust `1.92.0` with `wasm32-unknown-unknown`, and
`wasm-bindgen-cli 0.2.118` (`cargo +1.92.0 install --locked wasm-bindgen-cli
--version 0.2.118`). From the repository:

```bash
npm ci --prefix playground
bash playground/scripts/build-compiler.sh
uv run python -m playground.scripts.notices --compiler-source playground/.compiler-build
uv run python -m playground.scripts.prepare-fonts
uv run python -m playground.scripts.prepare-proof
npm run typecheck --prefix playground
npm run lint --prefix playground
npm run test:unit --prefix playground
uv run python -m playground.scripts.build-site
cd playground
npx playwright install --with-deps chromium
IMMUKNOW_SITE=1 npm run test:browser
cd ..
uv run python -m playground.scripts.compare-proof
uv run python -m playground.scripts.compare_examples
```

Set the pinned native font environment described above for native comparisons.
`build-site` runs strict MkDocs, checks fixture freshness, builds Vite, and copies
it into `site/playground/`. PR CI tests that complete artifact at its configured
`/ImmuKnow/playground/` subpath. For manual review, run
`uv run python -m playground.scripts.serve-site` and open
`http://localhost:4173/ImmuKnow/playground/`. The server is local QA tooling only;
the published artifact contains no server. Main deployments publish this same
combined artifact through the existing docs workflow.

For a notebook reverse proxy, build with its public path prefix (everything
before `/ImmuKnow/playground/`), then start the same local server:

```bash
export IMMUKNOW_PROXY_PREFIX=/notebook/justin-angevaare/immuknow-playground/proxy/4173
uv run python -m playground.scripts.build-site
uv run python -m playground.scripts.serve-site
```

Open the proxy URL followed by `/ImmuKnow/playground/`. The build prefixes
scripts, compiler/PDF workers, WASM, fonts, and generated fixtures consistently.
The local server accepts either a stripped prefix (normal notebook proxy
behavior) or the full prefix. Leave the variable unset for the normal Pages
build. To verify the proxy build locally, stop the manual server and run
`IMMUKNOW_SITE=1 npm run test:browser --prefix playground -- tests/proxy.spec.ts`
with the same exported prefix.

The real Chromium suite edits source and dependencies, navigates clients and
languages, restores local drafts/ZIPs, downloads current PDFs, recovers from
syntax errors, blocked remote imports, missing fonts and a fault-injected stuck
worker, and checks narrow layouts and keyboard resizing. Unit tests cover
revision/coalescing races, timeout behavior, and malformed/bounded archives.
Third-party requests are blocked and asserted absent during ordinary authoring
and all 37 maintained template/example combinations.

The edited-project browser test changes list columns and history options,
exports exact source and project bytes, builds and installs a wheel in a clean
environment, relocates the project, and runs both real CLI selectors for eight
synthetic clients. It checks completion, unchanged sources, and browser/native
PDF equivalence, with empty Typst package caches. Production needs no frontend
dependencies. The separate installed-wheel integration test covers maintained
packaged templates and read-only installed resources.

Comparisons check page counts, complete semantic text, text-run order, origins
and font sizes (within 0.01 PDF points), and rasterized pages at 144 dpi (mean
channel difference at most 0.05/255). Review images, PDFs, and reports appear in
`playground/test-results/`. Playwright clears that directory at the start of
**each invocation**: run the whole suite before the comparison commands.
Generated proof inputs and resources are synthetic, ignored by Git, and rebuilt
from canonical sources. Dependency notices ship beside the compiler and fonts.

## Synthetic playground examples

`playground/examples/scenarios.json` contains invented source records and short
scenario descriptions. Regenerate their committed prepared payloads and assemble
the static project resource bundle with:

```bash
uv run python -m playground.scripts.examples
uv run python -m playground.scripts.examples --check
```

The check runs in CI and fails if the committed facts have drifted. Preparation
uses the same CSV validation, normalization, assignment eligibility, age, QR,
and rendering-payload functions as production. All 37 offered notice/language
variants compile with real Typst in the integration suite; tests assert source
facts, identity, language, long-record continuation, literal text, and envelope
geometry. The assembled project also runs through both real CLI selectors and
its resulting payloads are compared with the browser fixtures.

Known-status and all-unknown examples are prepared separately to retain their
actual cohort coverage. The full test suite separately protects mixed-cohort
validity errors. The browser never parses clinical source strings or changes an
assessment to make a selected notice eligible. See the examples' README for the
synthetic CSVs and reproduction commands included in a complete project.
