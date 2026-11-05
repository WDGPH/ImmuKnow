# Contributor guidance

Read [README.md](README.md), [contributing](docs/developer_guide/contributing.md)
and the relevant guides before changing behavior. Follow the
[shared language and project responsibilities](docs/developer_guide/documentation.md#shared-language-and-project-responsibilities)
for documentation, application messages, code, comments and docstrings.

## Project responsibilities

Core owns native inputs, validation, notice selection, shared rendering resources,
saved runs and delivery. Studio owns browser editing, builds, fonts and preview
presentation. Template owns fictional example clients, starter letters, Settings,
display translations, example branding, project configuration, local setup and
helper commands. Core
ships no starter letters; use small unbranded fixtures for engine tests. Template
owns starter wording and page-count tests. Update the owning guide and link to it
from the other projects instead of copying its explanation.

Python prepares normalized facts, source checks, assignments and delivery.
Upstream systems assess immunization status. Typst owns prose, labels, dates,
dose wording, history display, QR destinations and layout findings. Group engine
code around preparation, rendering, output checks and delivery. Internal APIs may
change together; preserve public contracts and complete workflow behavior.
Studio uses internal preparation APIs against an exact locked Core commit; those
calls do not make the APIs public. Read-only resources are exposed through
`immuknow.resources`; the shared library lives under `immuknow/typst/`.

Keep PHU template and configuration directories isolated. Use bounded run
workspaces and never write into installed package files. Native compilation uses
system fonts; ship no font files or supplied-font staging/verification in Core.
Studio downloads fonts for manual installation; downloading does not install them.
Keep dependencies inside the authored project. Preserve `run_typst` package-path
isolation and its download block, including for computed imports.

Require the complete, unchanged project `lib/immuknow/` tree, independently of
project-declared hashes. Check it during staging and Studio
compilation/import/export/draft loading. Custom helpers belong outside that tree.
Use `report-v2.json` for report fields, components and render rules. Native and
browser validators share contract cases; verify page/range bounds and source-row
association as well as structure. Generate browser validators from schemas;
never enable runtime code evaluation for schema validation.

## Native contracts

`immuknow.orchestrator.run_pipeline` owns a complete cohort; the CLI is thin.
Each run accepts one CSV and exactly one selector: a filename assignment manifest
with an explicit template directory, or one `<version_id>.<language>.typ` file.
Only `en` and `fr` are supported. Manifest template values are basenames, not
paths. Preserve one resolved version and language per notice. Catalog rules check
applicability; they never choose a template, translate it or assess the client.

Keep one authoritative `run.json` and its escaped HTML view. Preserve every
original source row under a stable key before sorting, plus original PDFs,
facts and resource hashes. Password values stay in memory and are redacted from
saved resources and configuration. Pass prepared objects between responsibilities;
do not add mutable client, validation or completion manifests. Record actual
per-entry outcomes. Expected notice failures allow independent notices to
continue; setup failures and unexpected errors save partial evidence before
propagating. Bundle only known usable PDFs with unique membership, never stale
outputs. See [architecture](docs/reference/architecture.md) for output evidence.

Recoverable quality problems warn and retain the row. Invalid history, exact
nonblank identifier collisions, and missing or ambiguous assignments reject the
whole input before rendering. Parse history once with exact `Valid`/`Invalid`
tokens and check every source fragment before display exclusions. Retain all
parsed agents and their mapping presence in prepared facts. Formulation markers
change display names only; use no implicit agent-name exclusions. Each placed
history table fails on unknown agents unless its actual `ignore-agents` option excludes them; omitted tables have no
mapping check. Forecasted agents must cover overdue diseases: missing coverage
rejects the cohort; extra coverage warns. Demographic duplicate matching and
remediation are out of scope. Read
shared JSON/YAML through `structured_input.py`; reject repeated fields, unknown
settings and wrong types. Render checks use placed Typst metadata. Missing
evidence retains a readable PDF with a failed mandatory evidence check.
Typst owns notice content and layout validation. Native output handling records
PDF readability, hash and page count without extracting text or rechecking link
destinations. Validate the report and source binding when the compiler returns it.
Saved-run delivery trusts accepted findings and CLI-owned artifacts; manual edits
to saved runs are unsupported. Do not repeat facts/report validation or rescan
original/resource hashes during delivery.

Use validated `compile_notices.CompilerTimeouts` for every native Typst operation.
Compile each notice once and collect its placed Typst report from that compilation.
Remove temporary evidence data before publishing any notice PDF. Preserve row
continuation, sanitized readable originals when report validation fails, and
published bundles after failed later attempts. Failed original checks require review;
eligibility is metadata. Bundle all readable originals using configured grouping and size, with a findings CSV per
bundle. Review state and operator holds do not split bundles or omit pages.
Warning acceptance in `validation_policy.py` identifies the run, row, warning
occurrence and its effective rule setting; provide no blanket waiver or force-delivery path.
Encryption uses a separate copy with AES-256 revision 6. Verify settings and
password access, preserving originals and existing copies on failure.

Acquire the per-run operating-system lock before reading a saved record, and
hold it across delivery and writes. New runs hold it through the final report,
then close logs and locks before publishing their directory. Do not add a global
lock that blocks independent runs. Fixed notice length is an explicit PDF page
count: add no blank pages or per-client waivers. Open new bundles and check their
page counts; test page preservation in regression tests rather than comparing
every page during delivery. Write each run and bundle attempt in a unique
`.incomplete` directory and remove the suffix only after writing finishes.
Completed attempts keep their own PDF/CSV sets. Publish memberships with an
atomic `run.json` write after the directory rename. Leave interrupted directories
alone; add no backup, rollback or automatic recovery machinery. Record delivery
code and output hashes, referring to the original saved resource identity.

## Working method

Keep changes small and focused, use a branch, and preserve unrelated work.
Trace changes through the final notice and delivery. Check and commit meaningful
changes before starting the next one. Follow the
[testing strategy](docs/developer_guide/testing.md): test changed behavior at its
real boundary without repeating another project's validation suite. Run focused
checks, then the relevant full gates. Documentation-only changes need documentation
checks, not native or browser rebuilds. For font or presentation changes, compile
and inspect representative English/French PDFs, including long records and addresses.

Prefer direct edits, deletions and abstractions that earn their complexity.
Follow the [authoring principles](docs/developer_guide/documentation.md#template-authoring-principles).
Keep code typed and imports at the top. Avoid wildcard imports, silent fallbacks,
mutable global configuration caches and compatibility-only wrappers. Catch
exceptions only for meaningful recovery or actionable errors. Lock dependencies
in `uv.lock`; upgrades need matching locks and tests. Use non-mutating type/lint
checks and locked dependencies in CI; follow the testing guide for current commands.

Generate native build records only in wheel/source-archive staging. Project and
draft compatibility follows shared resource bytes, formats and compiler identity,
not unrelated package versions or checkout revisions. Keep browser pins in Studio.

Keep real client data and private PHU assets out of commits, examples and fixtures.
Treat client-linked diagnostics as sensitive output. PR descriptions explain the
result, rationale, verification and material limits. Git history records changes;
do not add dated journals or scorecards. The
[template guide](docs/user_guide/phu_templates.md) owns the JSON and native assertions.
