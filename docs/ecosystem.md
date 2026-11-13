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
Template's [native starter instructions](https://github.com/WDGPH/ImmuKnow-Template/blob/625f0b5c83d338c9ed1eda41f9de7d6e16adcbfd/README.md)
describe its setup and project files. Each project is updated independently;
updating Core does not update Studio's pins or a project's reference lists.

## Native handoff

Core exports its schemas and complete Typst library for projects and authoring
tools. Template owns authored notices and configuration; Studio owns adoption of
compatible Core and Template revisions. Check
[Studio compatibility](user_guide/studio.md#compatibility-with-standalone-core)
before exchanging projects. An executable's version alone does not establish
its source revision.

The [command and facts reference](developer_guide/cli.md) owns export commands,
resource identity, schema versions and the preparation envelope. The
[template guide](developer_guide/templates.md) owns the authoring contract.

## Testing the handoffs

Each project tests its own behavior and the files it hands to its consumers.
Core's [testing guide](developer_guide/testing.md#test-ownership-and-execution)
defines these boundaries and the checks needed for resource and pin updates.
See Template's
[contributor guide](https://github.com/WDGPH/ImmuKnow-Template/blob/625f0b5c83d338c9ed1eda41f9de7d6e16adcbfd/CONTRIBUTING.md)
and Studio's
[development guide](https://github.com/WDGPH/ImmuKnow-Studio/blob/main/docs/development.md)
for their execution instructions.
