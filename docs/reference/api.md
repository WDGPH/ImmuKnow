# Python interface

`immuknow.orchestrator.run_pipeline` runs one CSV cohort with exactly one
selector: `notice_assignments=Path(...)` for explicit per-client filenames, or
`notice_template=Path(...)` for one selected file applied unchanged to every row.
`config_dir` selects source references and run options; `template_dir` selects the
complete authored tree in manifest mode.

```python
from pathlib import Path
from immuknow.orchestrator import run_pipeline

record_path = run_pipeline(
    Path("clients.csv"),
    Path("runs"),
    notice_assignments=Path("assignments.json"),
    template_dir=Path("my-phu"),
)

record_path = run_pipeline(
    Path("clients.csv"),
    Path("runs"),
    notice_template=Path("my-phu/overdue_diseases_v1.en.typ"),
)
```

The filename `<version>.<language>.typ` supplies the selected identity, with
`en` and `fr` supported. The callable returns the authoritative
`runs/<run-id>/run.json` path, including partial outcomes and warnings. Shared
setup failures save a `failed_setup` record before propagating an exception.
Expected row failures are recorded while independent rows continue. The CLI
uses the same workflow and returns nonzero for failed rows or delivery steps.
Previous runs are retained.

The run freezes source bytes, selected resources and compiler inputs. Raw source
values, normalized facts, assignments, placed findings and original/delivery
results are recorded by stable original-order row keys. Password values are
excluded from saved configuration. Python supplies facts; authored Typst owns
prose, display choices, QR construction and component findings.

## Resources for authoring tools

`immuknow.resources.resource_root()` returns the installed package directory.
The supported resource directories are `templates/`, `config/` and `schemas/`.
Treat them as read-only and copy files before customization. Resources are
included in wheels and source distributions; no source checkout is needed.

`immuknow.resources.rendering_build_info()` returns the engine version, native
Typst version, rendering schema version, Core source identity, and a file/hash
manifest covering the payload schema and complete shared Typst library. Tools
such as Studio add their own application and browser compiler identities.

These resource functions and `run_pipeline` are supported interfaces. Internal
preparation, rendering and delivery functions may change together. Studio's
example generator currently uses those internal preparation functions against
an exact locked Core commit; this does not make them a public API.
See the [workflow](architecture.md), [configuration](../user_guide/configuration.md)
and [template contract](../user_guide/phu_templates.md) for their current boundaries.
