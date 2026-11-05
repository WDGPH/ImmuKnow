# Contributing

Trace a change through the Rust workflow in `src/pipeline.rs`: preserve source rows, prepare facts and assignments, compile independent notices, record findings, create requested encrypted copies, assemble bundles, and write the report. Change tests and user guidance at the boundary affected by the behavior.

Core owns input preparation, native rendering and delivery. The upstream system assesses immunization status. Authored Typst projects own prose and presentation; Core's unbranded fixtures are for tests. See the [template guide](../user_guide/phu_templates.md) for the rendering contract and the [architecture](../reference/architecture.md) for saved-run behavior.

Install the pinned Rust toolchain and run the [relevant checks](testing.md). For presentation or compiler changes, inspect representative English and French output, including long names, addresses and histories. Explain the resulting behavior, verification and material limits in the pull request. Do not commit real client data, derived passwords, run artifacts or private PHU assets.
