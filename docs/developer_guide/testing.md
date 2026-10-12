# Testing

Use a small set of real native journeys to check the complete workflow. Python
preparation checks source interpretation and explicit assignments; Typst checks
the components actually used; the run record accounts for every original source
row and every delivery outcome. Upstream data supplies assessment and notice
selection. Tests should never introduce automatic clinical assessment or language
selection.

## Run the checks

Install locked dependencies and Typst 0.15.1:

```bash
uv sync --all-groups
uv run ty check
uv run pytest
uv run pre-commit run --all-files
uv run --group docs mkdocs build --strict
```

Set `TYPST_BIN` if the pinned compiler is outside `PATH`. Native tests require
that compiler; mocked success cannot establish PDF behavior. Native compilation uses system fonts.
Install FreeSans and FreeSerif locally for notice checks.

For quick feedback, select the affected files or use `-m unit`, `-m integration`
or `-m e2e`. Collect tests after removing an internal interface to find stale
imports. Coordinate full-suite, installed-wheel and expensive rendering checks
on the integrated branch; repeated worker rebuilds add little evidence.

## Keep useful boundaries

The existing accounting journeys cover both notice selectors, source order and
provenance, independent rendering failures, and saved setup failures. Package
journeys cover import safety, placed component findings, QR destinations and
links, and visible content continuation. The installed-wheel journey checks
resources outside the checkout. CLI and maintained-template tests add semantic
language/content checks, filename confinement, literal source text and editable
project labels. Delivery journeys exercise saved-original routing and rebundling.

Preparation tests retain complete administrations and disease mappings,
`unknown > valid > invalid` deduplication precedence, whole-cohort validity
coverage, leading zeros, and explicit unknown birth/age. Assignment tests check
missing or ambiguous selections, duplicate source identities, and warning-level
applicability conflicts. Malformed shared inputs fail setup with a saved report.

A warning preserves a useful PDF and makes it reviewable. Tests must check the
warning, retained content and row outcome together. An omitted component has no
content requirements; native reports can mark its checks `not_applicable`.
Missing or ambiguous assignments and genuine compiler failures affect their
rows while independent rows continue. Neither warnings nor partial runs may be
reported as clean delivery success.

Retire assertions for deleted internal artifacts, Python QR images, display-row
payloads and hidden PDF markers. Preserve the behavior they protected through
facts, placed native findings or `run.json`; do not keep compatibility wrappers
for tests. Prefer extending a meaningful journey to adding another harness.

## Review rendered notices

Normalize inconsequential extraction whitespace for semantic assertions, and
keep layout checks separate. Review English/French overdue disease and agent
notices, affirmative wording and the suspension order. The suspension example
has one order page with no history or privacy appendix. Source province is
preserved, and unknown age uses neutral wording.

Check complete wording, history contents, dose wording, readable marks, QR links,
branding, page count, signatures and envelope-window measurements. Long content
remains visible with findings; declared intentional continuation can pass. Include
long addresses and histories. Input strings such as Typst syntax remain literal
text. Use synthetic records only.

Compiler or font changes need visual review before changing expected layout.
Do not update a snapshot or weaken a content assertion merely to obtain a pass.
Check failed and successful runs retain the appropriate original evidence and
that run logging restores the caller's handlers after either outcome.
