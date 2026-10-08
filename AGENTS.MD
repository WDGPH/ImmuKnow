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

Python owns source validation, canonical disease and dose facts, assessment,
eligibility, assignment reconciliation, QR payloads, encryption, and grouping.
Typst owns notice prose, labels, dates, dose wording, chart headings, and
layout. The authored entry points and assets live under
`immuknow/templates/`; package configuration and translations live under
`immuknow/config/`. PHU template and configuration directories are isolated.
Use a bounded run workspace and never write into installed package files.

Keep one authoritative resolved `version_id` and language per notice.
Persist the canonical cohort, selected resources, expected outputs, and
successful completion where they help reproduce a run. Pass validated objects
between internal responsibilities instead of writing files solely to separate
functions. Compilation, validation, encryption, and bundling must account for
the same expected set by identity and uniqueness. A failure must not publish
a successful bundle or reuse stale PDFs.

## Working method

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

Do not commit private PHU assets or real client data. Client-linked diagnostics
are sensitive run output. The [template guide](docs/user_guide/phu_templates.md)
defines the JSON and native assertions; [architecture](docs/reference/architecture.md)
defines complete output evidence.
