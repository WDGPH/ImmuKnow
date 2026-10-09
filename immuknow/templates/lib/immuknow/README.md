# ImmuKnow Typst package

Package version: `0.1.0`. Minimum compiler: Typst `0.15.1`. License: MIT.

Import the vendored package from a template entry point:

```typst
#import "lib/immuknow/lib.typ" as ik
#let template-version = "overdue_diseases_v1"
#let template-language = "en"
#let notice = json(sys.inputs.at("data"))
#ik.check-notice(notice, version: template-version, language: template-language)
```

`check-notice(notice, version: ..., language: ...)` validates rendering schema
`1`, required factual fields, rendering defaults, and the caller's literal
notice identity. It returns no visible content. The entry point must supply
both named arguments; they cannot be inferred from the payload. Language must
be `en` or `fr`. Validation does not perform assessment or decide eligibility.

Importing the package requires no client data and reads no `sys.inputs`.
The consuming entry point owns client-file reads and project assets.
The package version, payload schema version, and notice version are independent.

For local installation, copy this entire directory to
`<package-path>/local/immuknow/0.1.0/`, set `TYPST_PACKAGE_PATH=<package-path>`,
and import `@local/immuknow:0.1.0`. The vendored relative import is the portable
default and requires no registry or network cache.
