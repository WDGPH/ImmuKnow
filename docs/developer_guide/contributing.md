# Contributing to ImmuKnow

ImmuKnow produces immunization notices for Public Health Units (PHUs). Keep
changes understandable, testable, and traceable to the notice workflow.

## Make a change

1. Describe the behavior being changed in an issue or pull request. Use a
   focused branch and explain the reason for the change.
2. Trace the affected pipeline steps and disk artifacts. Update the code,
   relevant tests, and the guide that owns the changed contract.
3. Run the checks in the [testing guide](testing.md). For notice changes,
   compile and review representative English and French PDFs, including long
   records and addresses. Check any PHU-specific templates with their own assets.
4. In the pull request, explain the resulting behavior, checks run, and any
   remaining limits. Keep point-in-time results in the pull request and Git
   history rather than adding dated reports to the repository.

The complete pipeline matters more than preserving unused internal function
signatures. When changing a step, check its downstream consumers so that the
expected clients, render jobs, PDFs, validation, encryption, and bundles remain
consistent. [Architecture](../reference/architecture.md) describes the disk
contracts, and [code analysis](code_analysis.md) gives a tracing checklist.

Python prepares validated data and render jobs; Typst owns notice prose and
layout. Use the [template authoring guide](../user_guide/phu_templates.md) when
changing or adding PHU templates. Do not commit PHU-specific private assets or
real client data.
