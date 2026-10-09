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

## Display components

```typst
#ik.overdue-diseases(notice, columns: 2, include-dose: auto)
#ik.overdue-agents(notice, columns: 3)
#ik.immunization-history(
  notice,
  diseases: ("Diphtheria", "Tetanus", "Pertussis", "Polio"),
  ignore-agents: (),
  include-other: true,
  show-validity: auto,
  min-rows: 5,
)
```

These functions return composable content. An explicit option overrides the
corresponding `notice.rendering_defaults` value; `auto` inherits that default.
Empty arrays and `false` remain explicit choices. Language defaults to
`notice.language`; an explicit language must be `en` or `fr` and affects
component text only, not authored prose.

Both overdue functions accept `columns` (a positive integer; `auto` uses the
package default of two), `spacing` (12pt between columns), `row-spacing` (4pt),
and `empty` (default `none`, rendering nothing). Items fill left to right, then
top to bottom. Cells grow with content and the grid continues across pages.
Diseases and agents use separate prepared fields. Only the disease function
adds supplied dose wording; it never infers doses or agents. Maintained agent
entry points still require a nonempty agent list.

The history function filters normalized, case-sensitive agent identifiers
before computing membership and grouping. `diseases` contains unique canonical
identifiers, not translated headings. Use `include-other` for Other; do not
include it in `diseases`. Other includes any retained agent with a mapped
disease outside the selected set, or no recognized mapping. One agent may
contribute to both a named column and Other. Disabling Other never removes rows.
Zero disease columns are supported.

With validity off, a filled marker means an administration is recorded. With
validity on, filled/open/question-mark indicators mean valid/invalid/unknown.
Same-date agents are grouped separately by status (valid, invalid, unknown),
with a merged date cell. This deliberately preserves every status, including
unknowns alongside known conflicts. Mixed *source coverage* rejects an enabled
validity display, even when the YAML default was off. All-absent coverage stays
unknown. Filtering recomputes groups and date spans.

History supports `min-rows` (nonnegative integer), `font-size` (11pt),
`date-width` (75pt), `disease-width` (20pt), `agent-width` (1fr), `inset` (4pt),
and `stroke` (0.5pt). Headings repeat across pages; dates and labels follow the
component language. Row counts and all spans derive from the selected columns.
There is no truncation or automatic font shrinking to fit a page-count limit.

Default disease labels live only in `locales/`. For PHU overrides, load the
project's dictionaries in the entry point and pass a `labels` dictionary keyed
by names such as `fr_diseases_chart` or `en_diseases_overdue`. A supplied domain
replaces that domain; a missing required label is an error. Uncatalogued source
labels remain literal. Project paths must be resolved by the entry point, so
the same component works when installed as a local package.
