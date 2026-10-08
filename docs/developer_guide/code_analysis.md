# Code analysis

Before changing a function, trace its callers and the notice output it affects. Start with the orchestrator for pipeline flow, then follow the files read and written by the step.

```bash
rg -n 'function_name|ClassName' pipeline tests
rg -n 'open\(|read_text|write_text|load_config' pipeline
rg -n 'TODO|FIXME|deprecated' pipeline
```

Check whether a function has production callers, whether similar logic exists elsewhere, and whether changing it affects the canonical cohort, render jobs, PDFs, or completion evidence. Test-only use does not necessarily make a helper dead; inspect its contract first.

Keep helpers beside the step that uses them. Move one to `pipeline/utils.py` when two or more modules need it and the move makes the flow clearer. Prefer one assignment and localization path over parallel implementations. For native notices, Python prepares structured data and Typst owns prose and layout.

When a change touches output selection, check that every expected notice is accounted for and stale files cannot enter later steps. Update tests and documentation with any contract change. See [Testing](testing.md) for checks and [Architecture](../reference/architecture.md) for the disk contracts.
