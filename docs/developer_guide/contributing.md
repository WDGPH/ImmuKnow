# Contributing

Trace a change from `immuknow.orchestrator.run_pipeline` to the notice and
delivery output it affects. Update the maintained implementation, meaningful
tests, and the guide that owns the changed user-facing contract. The complete
run matters more than an unused internal function signature.

Python supplies validated client data and notice assignments; Typst formats and localizes
the document. Use [template authoring](../user_guide/phu_templates.md) when
changing notices. Run the [testing checks](testing.md) and inspect representative
English and French PDFs for presentation changes.

In the pull request, explain the resulting behavior, verification, and
remaining limits. Git history and the pull request carry change history.
Do not commit private PHU materials or real client data.

Keep pipeline stage imports in `orchestrator.py` in the order of the main
workflow: output preparation, client preparation, QR codes, render inputs,
compilation, PDF validation, encryption, bundling, and cleanup. The marked
`isort: off` / `isort: on` block is a deliberate exception to alphabetical
sorting. Imports make modules available; calls inside `run_pipeline` determine
execution order. Keep supporting imports outside that block.
