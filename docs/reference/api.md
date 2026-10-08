# Python interface

The supported callable interface is `immuknow.orchestrator.run_pipeline`.
It accepts an input Excel or CSV path, an output directory, optional fixed
language, and selected configuration, template, or assignment paths. It returns
the successful run's completion-record path, or `None` when the user cancels
an output-directory prompt. The CLI `immuknow` calls the same workflow.

```python
from pathlib import Path
from immuknow.orchestrator import run_pipeline

completion = run_pipeline(
    Path("students.xlsx"),
    Path("notices"),
    language="fr",
)
```

Internal preparation, rendering, validation, and delivery functions may change
together with the end-to-end workflow. See the [workflow](architecture.md),
[configuration](../user_guide/configuration.md), and
[template contract](../user_guide/phu_templates.md).
