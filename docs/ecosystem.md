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

See the [getting started guide](user_guide/getting_started.md) for native notice
generation, [Template's setup instructions](https://github.com/WDGPH/ImmuKnow-Template/blob/main/README.md)
for a starter project, and [Studio's documentation](https://docs.phiz.ca/immuknow-studio/latest/)
for browser editing and project export. Each project owns its setup,
compatibility and maintenance instructions.

## Native handoff

Core exports its schemas and complete Typst library for projects and authoring
tools. Template supplies authored notices and configuration; Studio consumes
Core's contracts for previews and exported projects.

The [command and facts reference](developer_guide/cli.md) owns export commands,
resource identity, schema versions and the preparation envelope. The
[template guide](developer_guide/templates.md) owns the authoring contract.

## Testing the handoffs

Each project tests its own behavior and the files it hands to its consumers.
Core's [testing guide](developer_guide/testing.md#test-ownership-and-execution)
defines these boundaries and the checks needed for resource and pin updates.
See Template's
[contributor guide](https://github.com/WDGPH/ImmuKnow-Template/blob/main/CONTRIBUTING.md)
and Studio's
[development guide](https://docs.phiz.ca/immuknow-studio/latest/development/)
for their execution instructions.
