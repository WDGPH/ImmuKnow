# ImmuKnow Studio

[ImmuKnow Studio](https://immuknow.phiz.ca/) lets you edit and preview notices
in your browser using fictional examples. It owns the browser editor, examples,
drafts, and project import and download.

Download a project to keep the selected notice, configuration, supporting files,
fonts and licences together. The download includes local setup and helper scripts
from [ImmuKnow-Template](https://github.com/WDGPH/ImmuKnow-Template). Install its
dependencies and fonts, then use those scripts to check the project and run
notices with Core on your workstation. Follow Studio's
[workstation guide](https://github.com/WDGPH/ImmuKnow-Studio/blob/main/docs/local-production.md)
for the steps.

Core owns the native pipeline, input and rendering schemas, validation, default
templates and shared Typst components. Its
[resource API](../reference/api.md#resources-for-authoring-tools) lets Studio
build against a pinned Core package. The native package does not include fonts;
Typst uses fonts installed on the workstation. See [getting started](getting_started.md)
for native runs and [template authoring](phu_templates.md) for the rendering contract.
