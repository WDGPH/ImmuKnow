# Documentation

Keep one current guide for each contract: [getting started](../user_guide/getting_started.md)
for inputs and the complete workflow, [configuration](../user_guide/configuration.md)
for user options and reference data, [template authoring](../user_guide/phu_templates.md)
for native JSON and assertions, and [testing](testing.md) for checks.
The [architecture](../reference/architecture.md) explains output evidence.
Link to these guides instead of copying them into new step descriptions.

Module docstrings should state purpose and important inputs, outputs, and
failures. Use types and examples when they clarify behavior. Test names and
docstrings should identify the user-visible behavior protected, especially
for compilation, mixed cohorts, and missing outputs.

Use plain words that tell readers what a field or step actually does.
Prefer "prepared client records", "disease names", or "selected version"
over abstract labels when those are the facts meant.

Keep point-in-time results and implementation rationale in the pull request
and Git history. Repository guides describe current behavior and repeatable
checks.
