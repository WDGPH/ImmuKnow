# Python interface

The supported callable interface is `immuknow.orchestrator.run_pipeline`.
Pass a CSV path and output directory, plus exactly one of
`notice_assignments=Path(...)` or `notice_template=Path(...)`. A manifest
assigns version and language per client; a named Typst file selects both for
the whole accepted cohort. `config_dir` selects configuration for either route;
`template_dir` selects a template tree for manifest selection. The function returns the successful completion
record path, or `None` when the user cancels an output-directory prompt.
The CLI `immuknow` calls the same workflow.

```python
from pathlib import Path
from immuknow.orchestrator import run_pipeline

completion = run_pipeline(
    Path("students.csv"),
    Path("notices"),
    notice_assignments=Path("assignments.json"),
)

# Or select one version and language for the whole accepted cohort.
completion = run_pipeline(
    Path("students.csv"),
    Path("notices"),
    notice_template=Path("my-phu/legacy_overdue_v1.en.typ"),
)
```

Internal preparation, rendering, validation, and delivery functions may change
together with the end-to-end workflow. See the [workflow](architecture.md),
[configuration](../user_guide/configuration.md), and
[template contract](../user_guide/phu_templates.md).
