# Documentation

Document the behavior that contributors and PHUs need to rely on. Explain what the code produces, its input and output contracts, and failures that require action. Keep implementation details close to the code and avoid repeating the same contract across guides.

## Docstrings

Every Python module starts with a purpose statement. Public functions use type hints and a short NumPy-style docstring. Include `Parameters`, `Returns`, and `Raises` when they add information beyond the signature. State important file reads, writes, configuration inputs, and assumptions. Keep examples executable or clearly illustrative.

For example, a PDF validator's docstring should say that it checks the expected PDFs from render jobs, compares extracted client IDs with those jobs, and writes `metadata/validation_<run_id>.json`. It should not claim that a language prefix selects the PDFs.

Test docstrings should describe the behavior protected by the test, especially for compilation assertions, mixed cohorts, and missing-output failures. Avoid restating the code line by line.

## Where to update guidance

- [Getting started](../user_guide/getting_started.md): supported inputs and CLI.
- [Template authoring](../user_guide/phu_templates.md): JSON payloads, native Typst entry points, assertions, and custom template migration.
- [Architecture](../reference/architecture.md): step boundaries and artifacts.
- [Testing](testing.md): checks and evidence limits.
- [Code analysis](code_analysis.md): tracing callers and removing duplication.

Update the existing guide that owns a contract when behavior changes. Keep point-in-time implementation evidence in the testing guide or changelog rather than creating a second set of instructions.
