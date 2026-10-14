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

Internal preparation, rendering and delivery functions may change together.
See the [workflow](architecture.md), [configuration](../user_guide/configuration.md)
and [template contract](../user_guide/phu_templates.md) for their current boundaries.
