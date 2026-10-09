# Template playground

[Open the playground](../../playground/){ target=_blank } to edit native Typst
beside a real PDF preview. Select a maintained template and language, then try
Previous, Next, or a named synthetic scenario. Client navigation preserves the
same source and options. All examples are invented and prepared by the normal
Python pipeline; the playground does not accept production CSVs.

## Author and preview

The controls near the top of each entry point set list columns, history disease
columns, ignored agents, Other, validity markers, branding, and envelope layout.
`auto` inherits prepared defaults; `false` and `()` are explicit overrides.
The [template guide](phu_templates.md) defines the shared component API and
configuration precedence. Expand **Components and authoring tips** for snippets.

**Files & assets** exposes dependencies and configuration. Text files have syntax
highlighting, undo/redo, and clickable compiler diagnostics. Binary assets can be
replaced in an exported ZIP and imported again. Translation overrides under
`config/translations/` affect preview rendering. Examples have fixed prepared
facts: edits to preprocessing, vaccine references, or eligibility configuration
must be tested through the native CLI. They do not reprepare browser examples.

Drag the divider or use its Left/Right keys to resize the panes. Narrow screens
stack them. Use fit width, zoom, and page navigation for long notices. The
optional envelope guide reads measurements from the same shared Typst layout;
it is a nonprinting overlay. Overflow warnings help authoring, while production
[PDF validation](pdf_validation.md) enforces configured rules. Check actual-size
printing and folds before using an envelope layout.

An error marks the last preview stale and disables PDF export. Source/client
revisions prevent an older compile from replacing current output. Compilation
runs in a worker, coalesces edits, and stops after 20 seconds; **Restart compiler**
replaces an unresponsive worker. Initial compiler/font loading allows 45 seconds.
First loading can take time because the pinned compiler is about 32 MB before
HTTP compression.

## Save and move a project

Drafts are stored locally in this browser after edits, including separate files
and template selections. Private browsing, disabled storage, quota limits, or
clearing site data can remove them. Download a project for a durable copy.
**Reset current file** restores that file; **Clear all drafts** restores the
maintained project after confirmation.

**Download .typ** preserves the active entry point's source bytes. It still needs
its package and assets. **Export project** includes edited templates, the shared
package, project assets, configuration/labels, version and file-hash metadata,
and reproduction instructions. Optional invented CSVs live separately under
`examples/`; example QR assets contain harmless demonstration destinations.
**Export PDF** downloads the actual currently previewed PDF, with no guide overlay.

To restore a project, ZIP its contents with `immuknow-project.json` at the root
and choose **Import project**. Import replaces the project only after validation
and confirmation. Limits are 400 entries, 8 MiB per file, and 24 MiB expanded or
compressed. Unsafe paths, links, duplicate paths, corrupted entries, unsupported
versions, and runtime payload replacements are rejected. Files retain their
bytes unless edited; no source regeneration or transpilation occurs.

Use the exported README's real CLI commands for single-template or manifest
selection. Both preserve production validation, eligibility, assertions,
encryption, and delivery. An export is a draft, not approval. Register a deliberate
new notice version explicitly in `config/notice_versions.yaml`, update its literal
assertion, and follow local approval procedures. Browser scenarios cover the
maintained identities; custom identities require native prepared inputs.

## Privacy and dependencies

Normal authoring, compilation, navigation, and export use self-hosted static
assets only. No source goes to a compiler server, URL parameters, analytics, or
telemetry. Remote Typst package downloads and HTTP filesystem fallback are
disabled. Vendor additional dependencies into the project using relative imports.
PDFs render to canvas without executing document links, JavaScript, or embedded
HTML. The application needs no backend and no cross-origin isolation headers.

The [testing guide](../developer_guide/testing.md) covers local builds, nested-path
browser checks, native comparisons, and exported-project CLI tests. See
[architecture](../reference/architecture.md) for compiler and dependency pins.
