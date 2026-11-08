# ImmuKnow Studio

[ImmuKnow Studio](https://immuknow.phiz.ca/) is a separate browser editor and
preview environment. [ImmuKnow Template](https://github.com/WDGPH/ImmuKnow-Template)
supplies starter notices, Settings, translations and example branding. Core
creates PDF notices and supplies the shared Typst components. See the
[project responsibilities and handoffs](../ecosystem.md).

## Compatibility with standalone Core

Use the reviewed compatible Template revision, `782d8d4`, and its
[setup instructions](https://github.com/WDGPH/ImmuKnow-Template/blob/782d8d4543519b6459ad1c1cfb1e0cbcae537581/README.md)
and recorded Core revision. These links identify the reviewed project independently
of branch names. Studio's pinned resource package is a separate compatibility
target; a newer Template checkout does not update Studio automatically.

The current Studio integration has **not yet adopted standalone Rust Core**.
Studio pins an earlier Python Core package and a Template resource package for
its existing browser previews and downloaded-project workflow. A project
downloaded from that Studio version should not be assumed compatible with this
standalone executable. Check Studio's version instructions and test the complete
handoff before using the two together. Standalone Core uses fonts installed on
the workstation; see [getting started](getting_started.md) and
[template authoring](../developer_guide/templates.md).

Studio owns the integration update: adopting the reviewed native executable and
matching Template resources, preparing preview facts through native commands,
using the exported schemas and library, and verifying browser previews and a
downloaded project with the native engine. Template's
[contributor guide](https://github.com/WDGPH/ImmuKnow-Template/blob/782d8d4543519b6459ad1c1cfb1e0cbcae537581/CONTRIBUTING.md#starter-resources-for-studio)
describes the required handoff. Core and Template updates do not change Studio's
pins automatically.
