# ImmuKnow Studio

ImmuKnow Studio is developed in a separate repository. It edits the default
Typst notices with its own fictional examples and exports complete authored
projects for the native engine.

Core supplies the default templates, shared Typst components, configuration
and rendering schemas. Its [resource API](../reference/api.md#resources-for-authoring-tools)
lets Studio build against an installed, pinned Core package.

Keep an exported project together and pass its `templates/` and `config/`
directories to Core. See [getting started](getting_started.md) for native runs
and [template authoring](phu_templates.md) for the rendering contract.

Studio's own repository contains its editor, draft, import/export and build
instructions. Core installation and documentation builds do not require Studio.
