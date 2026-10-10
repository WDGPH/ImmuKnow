# Template playground

[Open the playground](../../playground/){ target=_blank } to edit native Typst
beside a real PDF preview. Select a maintained template and language, then try
Previous, Next, or a named synthetic scenario. Client navigation preserves the
same source and options. All examples are invented and prepared by the normal
Python pipeline; the playground does not accept production CSVs.

## Paper, envelopes, and scrolling

The initial view keeps template/client selection and source/PDF downloads visible.
Expand **Project actions** for project import/export, reset, and compiler restart;
expand **Page, envelope & branding** for layout choices. PDF pages form one
continuous scrollable stack. The page counter follows scrolling, and Previous
page / Next page scroll to the corresponding sheet. Only nearby canvases are
rendered, keeping long histories manageable.

Paper choices are Letter (8½ × 11 in), Legal (8½ × 14 in), and A4.
Envelope-window choices include the authored rectangle and sample #10, DL, and
C5 windows. These change the real document, not just the guide overlay.
Selections are saved per template/language in `templates/layout-settings.json`,
which the native entry point reads and complete project export includes.
**Edit layout settings** opens that JSON in the editor; edits and undo also
update the selectors. Source downloads inline these settings; complete project exports retain the editable companion files.

Envelope size does not uniquely specify a window or fold position. The sample
windows are #10: 4½ × 1⅛ in, DL: 100 × 45 mm, and C5: 90 × 45 mm. These reflect
available [#10](https://www.eliteenvelope.com/products/10-envelopes.html?page=2),
[DL](https://majuscule.fr/enveloppes/97268-boite-de-500-enveloppes-blanches-110x220mm-90g-bande-siliconee-fenetre-45x100mm-first.html),
and [C5](https://www.antalis.ie/eshop/paper-boards-envelopes/envelopes/river-series-white-window-wallet-c5-90gsm-pdp-hq19105/sku-669089)
products, not universal window-placement standards. Presets retain the template's
page-relative x/y coordinates and safety padding; customize those in the Typst
source to match the purchased envelope and fold. Check an actual-size print.
Paper and envelope choices are independent so unusual combinations can be tested.

Older saved or imported entry points that do not consume the settings file keep
their authored layout; the selectors are disabled with an explanation. Export
any wanted edits before resetting an older entry point to the maintained version.

Advanced defaults live in `templates/settings/<template>.typ`. Use **Edit template settings** to adjust them while keeping the notice editor focused on content.

**Upload logo** and **Upload signature** accept PNG, JPEG, and WebP files up to
8 MiB and 16 megapixels. Images are decoded locally into PNG assets, preserving
transparency, and replace the project's logo/signature for all maintained
notices. Complete project exports retain them; **Restore sample images** restores
both sample assets after confirmation. A downloaded entry point still needs its
project assets. No image upload is sent to a server.

## Author and preview

The companion template settings set list columns, history disease
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

**Download .typ** inlines the maintained template’s companion settings and current
paper/window settings. It still needs
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
bytes unless edited in complete project exports. Only the individual `.typ` download flattens the marked settings import. Custom and older unmarked entry points download unchanged.

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
