# ImmuKnow projects and contracts

| Project | Description |
| --- | --- |
| Core | Native CSV preparation, validation, Typst compilation, PDF encryption, bundling and reporting. Supplies the shared Typst library and JSON schemas. |
| Template | Starter notices, wording, translations, settings, branding, project configuration and reference lists. |
| Studio | Browser editing, previews, local drafts and project import/export. |

Your organization adapts an authored notice project from Template. Keep Core's
shared library intact in `templates/lib/immuknow/`. Core reads the project,
CSV and explicit notice choices to produce PDFs, bundles and reports. The source
system assesses immunization status; operators review notices before delivery.

See the [getting started guide](user_guide/getting_started.md) for a native
project and [Studio](user_guide/studio.md) for the current integration status.
Template's [native starter instructions](https://github.com/WDGPH/ImmuKnow-Template/blob/77ef0f65c783cce4d523953363e6b22f4736ffd4/README.md)
describe its setup and project files. Each project is updated independently;
updating Core does not update Studio's pins or a project's reference lists.

The published Studio still targets Python Core. Its native companion is
[Studio PR #33](https://github.com/WDGPH/ImmuKnow-Studio/pull/33), coordinated with
[Template PR #16](https://github.com/WDGPH/ImmuKnow-Template/pull/16). Check
[Studio compatibility](user_guide/studio.md#compatibility-with-standalone-core)
before exchanging projects.

## Native handoff

`immuknow resources --output DIR` exports `schemas/input_schema.json`,
`schemas/rendering.json`, the `typst/` library including `typst/report.json`,
and `resource-manifest.json`. Export into a new directory when updating and
copy the entire library into the project. Existing identical files are accepted;
different files are not overwritten. The manifest identifies resources, not a
source commit. An executable's version alone does not establish its source
revision.

`immuknow prepare` writes JSON to standard output without creating PDFs. Its
version 1 envelope identifies the engine, resources and input hash and contains
one entry per source row with its `row_key`, `client_id`, source, assignment,
notice and checks. The row key preserves source-row identity even where an
external client ID is absent. Notice facts use schema version 1; rendering
reports use version 2. The unversioned schema filenames identify the current
contracts; the data's `schema_version` identifies its format. Render evidence
is checked against the prepared notice and its identity. See the
[command and facts reference](developer_guide/cli.md) for options and the
[template guide](developer_guide/templates.md) for authoring details.

## Testing the handoffs

Core owns native input, rendering evidence, PDF validation, reporting and bundle
behavior. Template tests its setup, helpers, resource package and one fictional
native sample journey, including starter presentation. Studio tests browser
previews, drafts, import and export, and the downloaded project's journey through
its pinned compatible engine. Adoption of this standalone Core needs the
separate [Studio integration checks](user_guide/studio.md). Each project tests its own boundary rather than
repeating another project's complete validation suite. See Core's
[testing guide](developer_guide/testing.md), Template's
[contributor guide](https://github.com/WDGPH/ImmuKnow-Template/blob/77ef0f65c783cce4d523953363e6b22f4736ffd4/CONTRIBUTING.md),
and Studio's [development guide](https://github.com/WDGPH/ImmuKnow-Studio/blob/main/docs/development.md).
