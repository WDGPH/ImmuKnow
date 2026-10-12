# Workflow and run evidence

`immuknow.orchestrator.run_pipeline` owns one cohort; `immuknow` is its CLI.
Read its main workflow from top to bottom: preserve inputs, prepare clients and
assignments, render independent notices, check completed PDFs, encrypt if
requested, bundle usable notices, then finish the report.

Each invocation creates a new directory under `--output`. Earlier runs are
preserved. Input, configuration and template paths must be outside that output
tree. Installed package files are never changed.

```text
runs/<run-id>/
  run.json        # authoritative facts, checks, outcomes and delivery attempts
  report.html     # escaped readable view generated from run.json
  originals/      # unchanged compiled notice PDFs
  facts/          # exact saved notice payloads
  resources/      # input and template/config snapshots
  encrypted/      # optional individual encrypted copies
  overrides.json  # current routing choices
  bundles/        # one active delivery/ and review/ result
  logs/run.log
  work/           # disposable preparation/compiler/assembly files
```

The existing `pipeline.after_run.remove_artifacts` setting removes only `work/`.
Facts, originals, reports and resource snapshots survive cleanup. Settings that
previously cleared all output or deleted unencrypted originals no longer do so.
Manual deletion of an entire run removes it.

## Source identity and preparation

The orchestrator reads raw CSV cells into report entries before validation or
sorting. Row keys such as `row-000001` identify original source rows, including
missing or repeated client IDs. Report entries stay in source order; the notice
sequence may use a different order. Original paths use row keys so client IDs
cannot overwrite another row's output or introduce paths.

Source columns and shared resources must be usable. Per-row missing addresses,
invalid optional dates, unparsed history, unknown school matches and known
assignment conflicts become findings while preserving the row. Unknown ages
remain unknown. Repeated client IDs and missing or ambiguous assignments fail
the affected rows without choosing a substitute. Unreadable shared resources
stop setup with a saved report.

Python preserves normalized history independently of display choices. Typst
Settings owns display options, translations, QR destinations and prose.
Components emit metadata only when placed; an omitted component has an explicit
`not_applicable` result without requiring its facts.

Both explicit selectors share the filename rule: `<version_id>.<language>.typ`,
with `en` or `fr`. A manifest selects a basename inside the chosen template tree;
`--template` selects that same file for every client. Neither route automatically
changes the assigned template based on language or clinical facts.

## One authoritative record

`run_report.py` writes format version 1. It replaces `run.json` and `report.html`
atomically as individual files after completed responsibilities and on exit.
JSON is authoritative if writing its HTML view is interrupted. There is no
separate mutable assignment, validation, compilation or completion manifest.
Immutable build manifests describe resources; they do not duplicate run state.

The top-level fields are `format_version`, `run_id`, `version`, `started_at`,
`finished_at`, `status`, `input`, `configuration`, `resources`, `entries`,
`checks`, and `delivery_attempts`. Application and compiler versions are actual
installed versions. Packaged `build.json` records source/base revisions, schema,
package and pinned compiler toolchains; the artifact builder refreshes it for
the source being packaged.

Each entry has `row_key`, `source`, `client_id`, `assignment`, `facts`, `checks`,
`original`, `encryption`, `routing`, and `bundle`. Source values remain available
beside normalized prepared facts and the saved payload. Assignments retain
passive experiment labels. Original and encrypted artifacts record relative
paths and full SHA-256 hashes; originals also record actual page counts. Bundle
membership records actual start/end pages and the bundle's hash, with separate
review-sheet and notice page spans.

Checks use the shared `CheckResult` shape: `code`, `stage`, `status`, `message`,
and optional `component`, `page`, and `measurements`. Status is `pass`, `warn`,
`fail`, `not_applicable`, or `not_run`. Every finding remains accessible in the
HTML report, which escapes source text and links to actual outputs.

Resources include per-file full hashes and one fingerprint of the staged file
manifest, including supporting templates, translations and assets. Native
compilation uses system fonts and does not stage or distribute font files.

Native compilation and `typst eval --in` use the same frozen payload, resources,
system fonts and creation timestamp. One `<immuknow-report>` summary supplies identity,
actual pages, component presence, checks, measurements and QR destinations.
Python verifies PDF readability, exact labelled client identity, hash and page
count against that evidence. It does not repeat Typst geometry rules. Compiler
warnings remain findings; missing or malformed summary evidence fails checking
and adds a warning that defaults the readable PDF to review.

Passwords and expanded password values are never recorded. Encryption password
settings remain in memory and are omitted from both saved effective settings
and the staged `parameters.yaml`; configuration records that redaction and the
original parameters hash. Encrypted outputs are separate from retained originals.

## Outcomes and delivery

A notice preparation, compilation or checking failure records the affected row
and allows independent clients to continue. A readable PDF remains available
when checking fails. Optional encryption creates separate per-client artifacts;
a failure is recorded and adds a delivery warning without changing originals.
Password placeholders consume normalized facts and cannot silently use missing
values to produce an empty password.

Delivery routing is explicit client override, then unallowed warnings to review,
then delivery. All findings remain in the record. Review bundles group by client
count, with all findings on a sheet immediately before each marked notice copy.
Delivery may group by school or board; missing grouping facts use Unknown.
Every readable original appears once in the active set, and failed rendering
creates no membership.

`immuknow-rebundle` loads a saved run and current overrides, verifies every
original hash, and uses the same assembly function as generation. It neither
reads current source/templates nor repeats encryption. Review sheets and stamps
use fixed application templates and available system fonts. The red mark occupies an added
outer band, preserving all original content at its original scale.

Assembly prepares `bundles.next` before replacing `bundles`. The previous set
stays in `bundles.previous` until the successful attempt and memberships are
saved. Attempt statuses in `run.json` support recovery after an interrupted
replacement; no second journal is maintained. Invalid overrides, changed
originals and failed assembly preserve the previous committed set. Successful
replacement removes stale membership in the former destination. Prior attempts
remain audit facts, and rebundle exit status describes the current attempt.

Overall status is `completed`, `completed_with_warnings`,
`completed_with_failures`, or `failed_setup`. Warnings return CLI exit 0;
failed entries or steps return nonzero. A shared setup error saves its report
before propagating. Unexpected programming errors also save partial evidence
and remain diagnosable. An unwritable output path raises directly without
claiming a report exists.

Run logging uses an application handler that is removed on exit; caller logging
is preserved. Client-linked facts, diagnostics, saved resources and originals
are sensitive run output and belong outside Git. The
[template guide](../user_guide/phu_templates.md) owns the rendered JSON contract.
