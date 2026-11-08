# ImmuKnow Studio

[ImmuKnow Studio](https://immuknow.phiz.ca/) is a separate browser editor and
preview environment. [ImmuKnow Template](https://github.com/WDGPH/ImmuKnow-Template)
supplies starter notices, Settings, translations and example branding. Core
creates PDF notices and supplies the shared Typst components. See the
[project responsibilities and handoffs](../ecosystem.md).

## Compatibility with standalone Core

Use the reviewed compatible Template revision, `625f0b5`, and its
[setup instructions](https://github.com/WDGPH/ImmuKnow-Template/blob/625f0b5c83d338c9ed1eda41f9de7d6e16adcbfd/README.md)
and recorded Core revision. These links identify the reviewed project independently
of branch names. Studio's pinned resource package is a separate compatibility
target; a newer Template checkout does not update Studio automatically.

The published Studio version still targets the earlier Python Core package.
The native adoption is available in [Studio PR #33](https://github.com/WDGPH/ImmuKnow-Studio/pull/33),
paired with [Template PR #16](https://github.com/WDGPH/ImmuKnow-Template/pull/16).
That integration pins Core `e7a8de1`, prepares facts with native `prepare`, exports
the matching library and schemas, and verifies browser previews and downloaded
projects with the same executable. Both companions must be adopted together;
changing a Template pin alone is insufficient. Projects from the published
Python-based Studio should not be assumed compatible with standalone Core.
Check the Studio build identity and its own setup instructions. Standalone Core uses fonts installed on
the workstation; see [getting started](getting_started.md) and
[template authoring](../developer_guide/templates.md).

Studio owns this handoff: its build verifies the reviewed native executable,
reads Template's `core-revision.txt`, uses exported schemas and the complete
library, and records source and resource identity. Its downloaded-project tests
cover native runs and saved-run holds/releases. Template's
[contributor guide](https://github.com/WDGPH/ImmuKnow-Template/blob/625f0b5c83d338c9ed1eda41f9de7d6e16adcbfd/CONTRIBUTING.md#starter-resources-for-studio)
describes the resource package. Core and Template updates do not change a
published Studio build automatically.
