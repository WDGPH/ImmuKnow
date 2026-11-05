# Documentation

Keep each contract in its owning guide. [Getting started](../user_guide/getting_started.md) describes a run; [configuration](../user_guide/configuration.md) describes settings; [PDF review](../user_guide/pdf_validation.md) describes delivery decisions; and [template authoring](../user_guide/phu_templates.md) describes the Typst project and facts. The [architecture](../reference/architecture.md) explains the native workflow and record. Link to the owning guide when another page needs context.

Use exact CLI options, paths, schema fields and statuses. Explain behavior for the person performing the task, including the distinction between warnings, failed checks and output failures. Keep user instructions separate from contributor implementation details. Use fictional examples and do not put client information in documentation.

Check source links, commands and key schema references locally:

```sh
cargo test --release --locked --test documentation
```

The documentation hub consumes this repository's Markdown and `mkdocs.yml`; the Core build and its documentation check require no documentation framework. The separate notification workflow informs the hub of changes. It does not publish the site or give the hub access to run data.
