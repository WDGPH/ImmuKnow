# Agent development guidelines

Read [contributing](docs/developer_guide/contributing.md),
[testing](docs/developer_guide/testing.md), and
[documentation](docs/developer_guide/documentation.md) before changing behavior.

## Application boundary

`immuknow.orchestrator.run_pipeline` owns one complete cohort; `immuknow` is
its thin CLI. Every run takes one CSV cohort and exactly one notice selector:
a JSON manifest with an explicit `template` filename per client, or one named
`<version_id>.<language>.typ` file for all accepted clients. Parse both selectors
by the same filename contract; only `en` and `fr` are supported. Manifest
filenames resolve inside the selected template tree and cannot contain paths.
The catalog checks version eligibility but supplies no language. Group internal code around input
preparation, native rendering,
output checks, and delivery. Internal signatures and intermediate schemas may
change together. Preserve user-facing configuration semantics and complete
end-to-end results, not obsolete step APIs.

Python owns source checks, normalized facts, applicability warnings, explicit
assignment reconciliation, encryption, and grouping. Upstream systems assess
immunization status. Typst owns notice prose, labels, dates, dose wording,
history display, QR destinations and drawing, and layout findings. The authored entry points and assets live under
`immuknow/templates/`, including project translations; factual configuration
lives under `immuknow/config/`. PHU template and configuration directories are isolated.
Use a bounded run workspace and never write into installed package files.
Native compilation uses system fonts; ship no font files in the native package
and do not stage or verify a supplied font set. Studio owns its FreeSans/FreeSerif
web assets and includes them with licences in project downloads for manual
installation. Downloading fonts does not install them for native Typst.
Keep client details and destinations correct, and check representative English
and French PDFs after font or presentation changes.
Keep dependencies inside the project. `run_typst` isolates native package paths
and blocks downloads before connecting, including for computed imports.
Keep the complete `lib/immuknow/` tree unchanged. Native staging, every delivery
attempt and Studio compilation/import/export/draft loading compare it with the
engine's supplied files, independently of project-declared hashes. Custom helpers
belong outside that directory; supplied library files are read-only in Studio.
Use its `report-v2.json` for report fields, components and render rule definitions.
Native and browser validators share test cases; check page/range bounds and row
association as well as structure. Studio commands generate validation functions
from those schemas. Never enable runtime code evaluation for schema validation.

Keep one authoritative resolved `version_id` and language per notice.
Persist one authoritative `run.json` and generate its escaped HTML view.
Create a separate run directory; preserve every original source row under a
stable row key before sorting and retain original PDFs, facts and resource
hashes. Password settings stay in memory and are redacted from saved resources
and effective configuration. Pass prepared objects between responsibilities;
do not add mutable client, validation or completion manifests. Compilation,
checking, encryption and bundling record actual per-entry outcomes. Expected
notice failures retain independent results; shared setup errors and unexpected
programming errors save honest partial evidence before propagating. Bundle
only known usable PDFs with unique membership; never reuse stale outputs.
Recoverable quality problems warn and retain the row. Invalid history, identifier
collisions and missing or ambiguous assignments reject the whole input before
rendering. History is parsed once with exact `Valid`/`Invalid` tokens; all source
fragments are checked before exclusions. Use the existing vaccine lookup to
check that forecasted agents cover the overdue diseases. Missing coverage rejects
the cohort; additional coverage warns. Flag exact nonblank ID collisions as
errors. Demographic duplicate matching and duplicate remediation are out of scope. Render
checks come from placed Typst metadata. Missing evidence keeps a readable PDF
with a failed mandatory evidence check.
Read shared JSON/YAML through `structured_input.py`; reject repeated fields,
unknown settings and wrong value types before rendering.
Every native Typst operation uses the validated deadlines owned by
`compile_notices.CompilerTimeouts`. Preserve row continuation, useful originals
after evidence timeouts, and committed bundles after review timeouts. Failed
checks affecting originals always route to review. Individual warning acceptance
is bound to run/row/PDF/evidence/rules in `validation_policy.py`; no blanket
allowance or force-delivery path is supported. Encryption failures affect the
separate encrypted copy. Use explicit AES-256 revision 6, verify the written
settings and password access, and preserve originals and existing copies on failure.
Hold the per-run operating-system lock across saved-run delivery reads, recovery
and writes. New runs hold it through the final report. Never load a saved
record before acquiring the lock or add a global lock that blocks other runs.
Fixed notice length means an explicit PDF page count per notice in delivery
bundles. Add no blank pages and allow no per-client exception or warning waiver.
Read back written bundles and compare each page with its selected source before
replacement. Record the current delivery code, resources and review tools on
every attempt; retain earlier attempt records.

## Working method

Keep each change small, check it, and commit before starting the next change.
Prefer direct edits and deletions; add a helper or dependency only when the
current task needs it.

1. Trace a change from CLI or orchestrator to the final notice and delivery.
2. Change the maintained code and the one guide that owns its contract.
3. Add or update tests that prove behavior at the real boundary. Retire tests
   of deleted internal signatures when they no longer protect behavior.
4. Run focused checks, then the relevant full gates from the testing guide.
   For presentation changes, compile actual Typst and inspect representative
   PDFs, including long records and addresses.
5. Describe resulting behavior, checks, and limits in the pull request. Use
   Git history for change history; do not commit dated journals or scorecards.

Keep code direct and typed. Imports belong at the top; avoid wildcard imports,
silent fallbacks, global mutable configuration caches, and wrappers kept only
for compatibility. Catch exceptions only where there is a meaningful recovery
or actionable error. Lock dependency versions in `uv.lock`; upgrades require
a matching lockfile and tests. Use `uv run ty check`,
`uv run pytest`, and `uv run pre-commit run --all-files` as applicable.
Native build records belong in wheel/source-archive staging, never tracked
package source. Studio keeps browser pins in its separate repository. Project and
draft compatibility compares shared resources and compiler identity, not an
unrelated package version or checkout revision. Use non-mutating type/lint checks
and locked dependencies in CI.

Studio owns its browser build, example scenarios and editing workflows in a
separate repository. Core exposes read-only resources through
`immuknow.resources`; its internal preparation APIs remain internal. Studio
locks an exact Core commit when using those APIs for its examples.

Follow the [shared language and project responsibilities](docs/developer_guide/documentation.md#shared-language-and-project-responsibilities)
standard in documentation, code, comments and application messages. Maintain
Core's native contracts here and link to Studio and Template for their workflows.

Do not commit private PHU assets or real client data. Client-linked diagnostics
are sensitive run output. The [template guide](docs/user_guide/phu_templates.md)
defines the JSON and native assertions; [architecture](docs/reference/architecture.md)
defines complete output evidence.
