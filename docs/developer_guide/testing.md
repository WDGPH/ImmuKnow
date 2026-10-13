# Testing

Run commands from the repository root unless a step explicitly changes directory.
For a clean checkout, complete setup and the artifact build before starting Studio.
If the assets are already prepared, skip to [Start a local server](#start-a-local-server).

The payload schema and `templates/lib/immuknow/report-v2.json` define native and
browser data checks. Studio's dev, type, unit and build commands generate the
browser validation functions automatically. The generated JavaScript stays out
of Git; edit the source schemas instead.
The browser does not compile schemas or enable runtime code evaluation.
Both implementations run the cases in `tests/fixtures/render-contract.json`.

Native CI runs on Linux with Python 3.10, 3.12 and 3.14. Other operating systems
are not covered by that suite. Studio's compiler build is tested on Linux and
uses Bash 4 or later and GNU `sha256sum`; the browser app itself is served as
static files.

## Prepare a clean checkout

1. Install Git, [uv](https://docs.astral.sh/uv/getting-started/installation/),
    Python 3.11 or later, Node.js 24 with npm, and the native
    [Typst 0.15.1 executable](https://github.com/typst/typst/releases/tag/v0.15.1).
    Put `typst` on `PATH`, or set `TYPST_BIN` to its absolute path.
    Rust builds also need your platform's native compiler/linker and development
    libraries; on Debian/Ubuntu these include `build-essential`, `pkg-config` and
    `libssl-dev`.

2. Install [Rust via rustup](https://rust-lang.org/tools/install/) if absent.
    On Linux:

    ```bash
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
    ```

    Then load its shell environment and install the pinned build tools. These
    versions are recorded in `studio/compiler-pins.json`:

    ```bash
    . "$HOME/.cargo/env"
    rustup toolchain install 1.92.0 --profile minimal
    cargo +1.92.0 install --locked wasm-bindgen-cli --version 0.2.118
    ```

3. Install the project's locked dependencies:

    ```bash
    uv sync --all-groups
    npm ci --prefix studio
    ```

## Build Studio

```bash
uv run python -m studio.scripts.build-site
```

This prepares the browser compiler, license notices, fonts and examples,
then builds docs and Studio into
`site/`. The first compiler build can take a while; subsequent builds reuse a
compiler whose source/toolchain identity and file hashes match.

Rust is a **build-time** dependency. License generation also needs Cargo and the
pinned compiler source checkout, even when the compiled WebAssembly is cached.
Neither the dev server nor a static production server needs Rust once the assets
exist. To use a separate compiler checkout, pass `--compiler-source /path/to/checkout`
or set `IMMUKNOW_COMPILER_BUILD_DIR`. Building does not publish anything.

## Start a local server

After the build above, choose one server. For Studio development with hot reload:

```bash
npm run dev --prefix studio -- --host 0.0.0.0 --port 5173
```

Open <http://localhost:5173/>. CSS updates in place; TypeScript and HTML edits
reload the page.
`npm run dev` checks for these assets but does not build them or install tools.
These generated resources are not rebuilt by Vite: rebuild when their inputs
change. To load updated starter templates instead of a saved draft, export any
work you want to keep, choose **Clear saved draft**, then reload.

When a notebook proxy serves Studio under a path, set that complete path as
`IMMUKNOW_DEV_PROXY_BASE` (including both slashes). Set the allowed hostname
separately; neither value needs to be committed:

```bash
IMMUKNOW_DEV_PROXY_BASE=/notebook/example/proxy/5173/ \
__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS=notebook.example.com \
npm run dev --prefix studio -- --host 0.0.0.0 --port 5173 --strictPort
```

Open the matching proxy URL with its trailing slash. The dev configuration keeps
module and hot-reload WebSocket URLs under that prefix, including when the proxy
strips it before forwarding. Production builds keep relative asset URLs.

To preview the built docs and Studio when `site/studio/index.html` exists:

```bash
npm run serve --prefix studio
```

Open <http://localhost:4173/studio/> (keep the trailing slash). Through a
notebook proxy, append `studio/` to the proxied server URL, for example
`https://notebook.example.com/notebook/example/proxy/4173/studio/`.
Relative asset URLs keep scripts, workers and generated resources under that
prefix; no proxy environment variables or hostname configuration are needed.
The command uses `uv run python -m http.server` for a local preview of the
production artifact. This serves the last build; it does not reload source
changes. After updating Studio sources, [rebuild the artifact](#build-studio),
then run the same server command. The test suite is not required just to preview the app.

For documentation editing only, the Python dependencies from setup are sufficient;
skip the Studio build and use:

```bash
uv run --group docs mkdocs serve --dev-addr 0.0.0.0:8000
```

Open <http://localhost:8000/>. This previews documentation only; use the built
site above to review Studio.

## What the tests protect

Test the contract at the layer that owns it. Use real Typst compilation for PDF
behavior and example client records throughout. Assessment, language and notice
selection come from explicit upstream inputs; tests must not invent them.

| Boundary | Intentional coverage | Existing tests |
| --- | --- | --- |
| Python preparation and selection | Every source row, leading zeros, unknown age, complete history/disease mappings, validity precedence, missing/ambiguous assignments and malformed shared inputs | `tests/unit/`, `test_pipeline_contracts.py` |
| Typst components and maintained notices | Placed component findings, literal source text, English/French wording, visible continuation, QR destinations, affirmative content and one-page suspension order | `test_typst_package.py`, `test_native_templates.py` |
| Native workflow and delivery | Both selectors, source order, independent rendering failures, saved setup failures, decryptable copies, warning review and rebundling unchanged originals | `test_run_accounting.py`, `test_saved_run_delivery.py`, `tests/e2e/test_full_pipeline.py` |
| Installed distribution | Relocated wheel, packaged resources, provenance, custom templates and operation without Node/Rust or checkout imports | `test_installed_package.py` |
| Studio components | Archive integrity and path limits, authored-byte preservation and stale-input export refusal | `studio/unit/` |
| Served Studio workflow | Real compiler recovery, current-preview state, editing/drafts/import/export, then a downloaded Typst project run outside the checkout with a separately installed engine through both selectors | `studio/tests/` |

The downloaded-project journey compares preview canvases with browser/native PDF
rasters, including page dimensions, white backgrounds, visible ink and decoded QR
destinations. Native/browser checks allow small font differences and movement
between pages, require at least 95% text coverage across the document, and retain
page images for review. Page counts, sizes, language and QR destinations must
agree. Selected cases cover both
overdue notice types and languages, long history, affirmative content, suspension
and source warnings. It also checks review/rebundle and refuses delayed project
downloads when the open project changes. Installed-package checks remain separate.

Draft browser checks cover pending and failed writes, immediate reload protection,
import/reset across reloads, clearing, unsupported drafts, and two-tab conflicts.
They use the current v2 store and verify that older storage remains untouched.

Encryption checks inspect the written AES-256 revision 6 settings, reject wrong
and empty passwords, and use MuPDF to open copies and compare their page images
with originals. The installed-wheel journey verifies that the required encryption
backend is installed with the package. `studio/tests/encryption.spec.ts` uses
the full Chromium browser’s PDF viewer, checks password rejection and opening,
and retains a screenshot and the reader version under `studio/test-results/`.
Recipient-reader acceptance remains separate.

Saved-run process tests hold one delivery attempt open while another tries the
same run and a different run. They also stop writers before replacement, after
replacement and after the saved commit, then check recovery, earlier decisions
and bundle bytes. New-run checks cover the first and final report writes.
Delivery checks also compare each written page with its selected source page,
refuse changed page order or contents, and exercise fixed page counts across
mixed-length batches. An accepted signature warning cannot release a batch that
fails its page count. Successful delivery pages are compared with originals using
MuPDF. Tool records cover changed review templates and refusal of changed saved
resources, unsupported payloads and compiler versions.

A warning must retain the useful PDF, content and row outcome together. Partial
runs and warning runs must stay distinguishable from clean delivery. An omitted
component can be `not_applicable`; a compiler failure must not block independent
rows. Extend these journeys when behavior changes instead of duplicating them in
mocks or adding tests solely to raise a coverage percentage.

## Run the checks

After setup, run the Python and documentation checks:

```bash
uv run ty check
uv run ruff check --no-fix .
uv run ruff format --check .
uv run pytest
uv run pre-commit run --all-files
uv run --group docs mkdocs build --strict --site-dir /tmp/immuknow-docs-check
```

The separate docs output directory preserves the built `site/studio/` artifact.
CI uses locked dependencies and these checks without rewriting files. Native
build tests compare source bytes before and after packaging, rebuild a source
archive without Git or Studio, and verify every native file hash in the wheel.
Documentation-only pull requests build the docs without Node, Rust or Typst.
Changes to product code, shared resources or examples still run product checks.
Publishing on the main branch continues to build the complete docs/Studio site.

For focused feedback, select the affected test files or use `-m unit`,
`-m integration` or `-m e2e`. Run the full Python suite before handoff. Coverage
reports help find untested decisions; they do not establish end-to-end behavior:

```bash
uv run pytest --cov --cov-branch --cov-report=term-missing --cov-report=xml
```

Set `TYPST_BIN` if the pinned compiler is outside `PATH`. Native tests require
that compiler. Native compilation uses system fonts. Test actual PDF font use and saved
delivery, and verify that native distributions contain no font files. Studio
uses its web assets; project downloads omit fonts unless requested. Comparisons
allow small appearance differences.
Native package tests prove that an outside package is loadable without ImmuKnow,
then verify refusal in compilation and evidence evaluation. A local proxy records
connection attempts; package refusal must occur before any request.

Component-library checks reject changed, missing, extra, renamed and linked
files before native rendering. Saved-run and Studio archive checks also refuse
changes when project-declared hashes have been rewritten. Browser cases cover
compiler recovery after refusal, retained drafts with changed libraries or reset
baselines, and read-only navigation into a supplied component after an error.

Compiler/font changes require visual review before changing expectations. Inspect
wording, history, readable marks, QR links, branding, signatures and envelope-window
measurements. Include English/French notices, long addresses/history and the
one-page suspension order. Semantic PDF checks do not replace visual review.

For focused Studio feedback after relevant source changes:

```bash
npm run typecheck --prefix studio
npm run lint --prefix studio
npm run test:unit --prefix studio
```

Complete the artifact build and stop any preview server on port 4173 before
browser checks. Install Chromium and its system dependencies once, then run the
served-site journeys:

```bash
cd studio
npx playwright install --with-deps chromium
IMMUKNOW_SITE=1 npm run test:browser
cd ..
```

The test configuration serves `site/` on port 4173 and opens `/studio/`. To inspect
that same artifact locally or through a notebook proxy, follow
[Start a local server](#start-a-local-server).
Workers, compiler resources, fonts and assets use relative paths. Against an
already served artifact, set `IMMUKNOW_BASE_URL` to its complete Studio URL
(including any proxy prefix) when running browser checks from `studio/`.
Do not rebuild while the browser is using the artifact.

`typst-project.spec.ts` retains downloaded archives, preview/native page images,
browser/native PDFs, run records, comparison results and command logs under `studio/test-results/`.
CI uploads this directory as `studio-render-evidence`, including after failures.
Save any manual comparisons separately: a later Playwright run clears its prior
results. Inspect representative PDFs and the actual proxy path, and report which
checks ran and which evidence remains unverified. A docs build, archive unit test
or coverage score alone does not establish the complete workflow.

## Preview measurements and compiler reuse

After building, start the static server described above. In another terminal:

```bash
IMMUKNOW_BASE_URL=http://127.0.0.1:4173/studio/ SAMPLES=30 \
  node studio/scripts/benchmark-preview.mjs /tmp/preview-measurements.json
```

The harness uses one-page and two-page English/French notices, approximately
five-page history, and an explicitly selected supplied font. Each sample changes visible text, awaits the matching
visible-page commit, and records scheduling, request preparation/transfer,
worker reconciliation, layout, vector-artifact generation, evidence and canvas preparation/commit
durations. PDF export is measured separately. Cold compiler startup and the first render are separate
from warm median/p95 samples. The JSON includes browser, CPU, document sizes,
worker starts, resource requests and remapped bytes. Render completion plus DOM
commit is a software milestone, not a measurement of physical screen paint.
Run comparisons on the same machine without concurrent builds or test suites;
there is no per-device latency threshold in CI.

The scheduler keeps one active compilation and one newest full snapshot. It
waits 75 ms after typing, capped at 150 ms from the start of a pending burst;
explicit context changes dispatch promptly. Readiness and completion respect
that deadline. Same-context successes may advance the preview while newer edits
are pending. Context and revision checks separately govern displayed pages,
diagnostics, findings and download eligibility. The viewer paints every replacement
page offscreen before committing the complete notice and its overlays. It preserves
the latest page-relative position, including horizontal scrolling. Zoom and fit-width
changes rescale retained canvases; scrolling does not repaint or evict them.
Canvas allocation is bounded at 32 million pixels per document and 8192 pixels per
edge. Resolution may decrease for larger notices; output requiring less than half
a pixel per Typst point is refused explicitly while keeping the last preview.
There is one displayed document, one preparation, and one newest pending candidate.
The locally bundled renderer stays initialized; each preparation frees its session.

Normal edits never generate PDFs or start a PDF parser worker. An explicit download
captures the complete snapshot and gets its own operation identity. The compiler
serializes that operation with preview compilation, refuses duplicate exports, and
rejects an export if its context or revision changes. The next preview reconciles
its own complete snapshot normally. Export errors retain the painted notice.

The browser compiler source revision remains pinned in `studio/compiler-pins.json`. Its
`reset()` calls VFS age eviction; `reset_shadow()` removes mapped inputs.
`map_shadow()` and `unmap_shadow()` invalidate the affected paths and advance
VFS revisions. `add_source()` is another shadow mapping, not an incremental
text-edit API. The pinned VFS reuses parsed sources by content and calls
`Source.replace()` on the previous source when bytes change. `set_fonts()` replaces a shared resolver; each `snapshot()` owns
its entry, inputs and world clock. Worker reconciliation compares complete
snapshots, maps only changed bytes and removes deleted files. Supplied font
bytes and manifests are compared before rehashing or rebuilding a resolver.
Worlds are freed after artifact and evidence extraction, including on errors.

The upstream snapshot wrapper omits the compilation actor's memoization-age
step and does not evict its separate parsed-source history.
`studio/scripts/patches/compiler-cache.patch` ages memoization and evicts that
history through the pinned APIs in `reset()`. This version's source-cache shard
age is not refreshed, so that eviction discards old source variants; unchanged
managed sources remain reusable. Studio does not promise incremental parsing of
the changed file.
The build applies it to the pinned source temporarily, restores the checkout,
and records the patch SHA-256 and feature list in the artifact identity. Cache
reuse requires that identity and artifact checksums to match. The maintained
compiler enables `web,pdf,svg`; format 0 is a complete binary vector artifact,
not SVG markup. The matching renderer is built from the same pinned source with
only `render_canvas`. Neither compiler `incr` nor renderer worker features are
enabled. `compiler-preview.patch` exposes page dimensions and ordinary text boxes
from the same paged document, independently of optional render evidence.
Translated text can navigate through the existing unique source matcher;
unsupported transformed positions and stale source mappings do not navigate.
Plain document text is supplied separately for assistive readers. No generated
HTML or executable document markup is inserted into the page.
`renderer-canvas.patch` fixes upstream conditional compilation for this minimal
feature set and releases raster-cache entries, image buffers and SVG load handlers
when each complete render session ends. Both patches, compiler/renderer features, versions and artifact
checksums are recorded by the same reproducible build and license inventory.
