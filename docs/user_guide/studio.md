# ImmuKnow Studio

Studio lets you edit a Typst notice and preview it with prepared, fictional
clients. It uses the same facts contract, authored project and native findings
as the Python pipeline. Upstream systems assess immunization status; Studio
does not assess a client or choose their notice.

## Edit and review

Use **Template** for letter wording, **Settings** for page/envelope setup,
dates, QR destinations and display choices, and **Theme** for fonts, colours,
logo, signature and an additional image. Template starters and Theme starters
are in Theme. Shared Settings changes can affect several entry points; check
each notice you intend to use. The question mark opens the guided walkthrough.

Theme controls use the supplied Settings layout and ignore commented examples,
including nested comments. Changes preserve surrounding text and line endings.
For calculated values, repeated definitions or more complex source, use the
Settings editor; controls that cannot safely read a value show **Edit in Settings**
or explain where to edit it. A refused theme change leaves the project unchanged.

The editor keeps native imports such as `#import "settings.typ": *` visible.
Use Ctrl+/ to comment a selection and Ctrl+[ or Ctrl+] to change indentation.
Drag the divider to resize the panes. The preview shows all pages in one scroll;
use its plus/minus controls to zoom. Double-click supported preview content to
jump to its source when the preview is current and the text has a unique source match. Compiler diagnostics can also link to a source location.

Example navigation shows only prepared variants for the selected entry point.
The five scenarios cover short history, long history, source warnings, an
up-to-date notice and a suspension order. Across them, eleven explicit variants
exercise six maintained filenames: English/French overdue disease and agent
notices, an English affirmative notice and an English suspension order. Names,
addresses and schools match the selected language. Switching examples never
changes a client's clinical facts or invents a missing language variant.

Findings combine source-preparation warnings, compiler diagnostics and placed
Typst checks. Examples contain valid source history. Invalid history rejects a
native input file before rendering, even if a template omits the history table.
Display checks, such as unknown dose validity, follow the components actually placed.
Expand **Measurements** for layout details. Long content stays
visible with a warning where possible. A readable preview with missing checking
evidence retains a finding; it is not treated as checked success. During ordinary edits, the last successful preview remains visible while the
refresh icon spins. Temporary errors retain those pages and leave the icon visible.
The icon's tooltip and accessible label describe the preview state. Findings and envelope
measurements describe the displayed pages; new errors describe the current
source. Old diagnostics are removed as soon as you edit, so their locations
cannot underline different source text.

Updates preserve zoom and your page position, including scrolling while a
replacement is being prepared. Removing pages clamps the position to the
remaining document. All replacement pages are prepared before the notice changes.
Scrolling and zooming keep the painted pages available. Extremely large output
may exceed the preview resource limit; Studio reports this and retains the last
usable preview. There is no five-page output limit. Switching examples or languages, importing a project,
resetting a file and restarting the compiler clear the previous preview.
During continuous typing, newer successful versions can appear while the refresh
icon continues to spin.

Examples use fixed prepared facts and dates. Editing their source CSV or
configuration in an imported project does not prepare new browser facts. Use
the native pipeline for a different cohort or factual configuration.

## Keep your work

Studio saves the current draft as you edit, including file bytes, uploaded
images, the selected template and example, and the project's starting files.
The status shows **Saving…**, **Saved**, or a storage error. Wait for **Saved**
before closing or reloading. Pending or failed saves keep the browser's
leave-page warning active. Download the project for a portable copy; storage
errors leave your open work available to download, and another edit retries saving.

Only one tab can edit Studio on a site at a time. A second tab asks you to close
the editing tab and reload. Another device or site address has separate storage.
Current drafts use format 2 in `immuknow-studio-drafts-v2`; older browser storage
is left untouched. Drafts and imported ZIPs check the same supported build requirements.
These cover shared components, fonts, the data format and the compiler build.
Projects can move between application releases when those requirements still
match. The selected file must be an English or French notice under `templates/`.

**Reset current file** restores the file as it was when the starter or imported
project was opened. That starting point is kept when a draft is reopened.
**Clear saved draft** removes the stored draft, including pending edits, while
keeping the open project available to download; later edits save it again.
**Restart compiler** retries the open project after a compiler problem.

Import project accepts the current complete ZIP format. Authored source,
companions and assets keep their bytes; Studio performs no source rewriting or
format migration. An unsupported draft/project format produces an actionable
error. An imported entry without a prepared example can still be exported,
but has no preview.

## Download the project

**Download project** saves the complete authored Typst tree with Settings,
translations, components, images, configuration and example inputs.
Authored files keep their bytes and relative paths. Import the ZIP to resume
editing, or use it with a separately installed native ImmuKnow engine.
The download includes no Python runner, dependency environment or engine wheel.
If the project changes while the ZIP is being prepared, download it again.
A project with unfinished edits or no prepared example can still be saved.

Downloads omit fonts by default. Select **Include fonts** to add Studio's
FreeSans and FreeSerif files and licences for manual installation. The production
pipeline uses system fonts; downloading the files does not install them.
The ZIP's `immuknow-project.json` records format version, selected entry, build identity
and SHA-256 file hashes, which are verified on import. Files are limited to
12 MiB each and 32 MiB in total. Absolute/traversal paths, duplicate paths,
symlinks and corrupt archives are rejected.

## Use the project with the native engine

Keep the extracted project tree together and install ImmuKnow and the supported
Typst compiler separately. Follow [getting started](getting_started.md) to run a
cohort with one template or an assignment file. Pass the exported `config/` and
`templates/` directories to the native engine. Studio previews use prepared
example data; changes to source CSVs or configuration require native preparation
before comparing their results.

Native runs retain originals, checks and delivery results in `run.json` and
`report.html`. Follow [PDF validation and delivery](pdf_validation.md) for review
decisions. Review example wording, branding, contacts, dates and signatures
before production use.
