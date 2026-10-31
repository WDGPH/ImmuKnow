# Contributor guidance

Read [README.md](README.md) and the relevant guides before changing behavior.
Follow the [shared language and project responsibilities](docs/developer_guide/documentation.md#shared-language-and-project-responsibilities)
for documentation, application messages, code, comments and docstrings.

Core owns native inputs, validation, notice selection, shared rendering resources,
saved runs and delivery. Browser editing belongs in ImmuKnow Studio; workstation
setup and helper commands belong in ImmuKnow Template. Update the owning guide
and link to it from the other projects instead of copying the explanation.

Follow the [testing strategy](docs/developer_guide/testing.md), including the
boundaries between Core, Studio and Template. Test the behavior that changed;
avoid repeating another repository's validation suite. Documentation-only changes
need documentation checks, not native or browser rebuilds.

Keep changes small and focused. Use a branch for changes and preserve unrelated
work. Keep real client data and private assets out of examples and test fixtures.
