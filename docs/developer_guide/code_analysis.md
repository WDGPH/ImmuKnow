# Code analysis

Start at `immuknow.orchestrator.run_pipeline`, then follow the functions and
files involved in the final PDF or bundle. Search current callers and tests:

```bash
rg -n 'function_name|ClassName' immuknow tests
rg -n 'open\\(|read_text|write_text|load_config' immuknow
rg -n 'TODO|FIXME|deprecated' immuknow
```

Check whether a helper has a production caller, duplicates another path, or
exists only for an obsolete intermediate contract. Keep shared helpers only
when they reduce repetition. Confirm assignment, rendering, validation,
encryption, and bundling use the same expected notice set. See
[workflow evidence](../reference/architecture.md) and [testing](testing.md).
