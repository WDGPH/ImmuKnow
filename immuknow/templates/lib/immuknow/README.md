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

## Page and letter layout

```typst
#show: ik.notice-page.with(language: notice.language, font: "FreeSans", font-size: 10pt)
#ik.notice-header(logo: image(notice.logo_path, width: 6cm), title: "Local notice title")
#ik.client-block(notice, window: (
  x: 1.75cm, y: 165.1pt, width: 202.28pt, height: 81pt, padding: 11pt,
))
#ik.signature-block(
  signature: image(notice.signature_path, width: 3cm, height: 1cm, fit: "contain"),
  name: "Sample signer", title: "Sample title",
)
```

`notice-page` is a show-rule wrapper: language (`en` or `fr`), Canadian region,
`paper` (`us-letter`), `margins` (top 1cm, bottom 2cm, left 1.75cm, right 2cm),
`font`, `font-size`, and `page-numbers` (true). Its body remains ordinary Typst.
`notice-header` accepts already resolved image content, `logo-width` (6cm),
`title`, `title-size` (16pt), `fill` (black), `placement` (`left` or `right`),
and `spacing` (12pt). Resolve all project images in the entry point before
passing them into a package, including when using `@local` imports.

`client-block` positions the address window using absolute physical lengths
from the **top-left of the printed page**, not the text area. Its preset
matches the former contact row's position and 81pt height; width 202.28pt is
that row's address column. `padding` is a safety inset on all four edges.
Changing margins does not change these physical coordinates. A window above
preceding content or left of the text margin produces a diagnostic; move the
window or reduce that preceding content. Keep the window within the paper.

The client block accepts `font-size` and `min-font-size` (both 10pt),
`addressee` (`auto` uses the prepared `over_16` fact), `province` (`Ontario`),
`school-label` (`auto` localizes), `show-birth-date` and `show-school` (true),
`details` (`right` or `below`), `spacing` (0pt), and `border` (none). Client ID
is always present. `address-block(client, language:, addressee:, province:)`
is the composable address text used inside it. Address content grows rather
than being clipped or automatically shrunk. An oversized address emits its
full measured height, and the `envelope_window` PDF validation rule reports
when it exceeds the safe rectangle. Use `error` severity to block delivery.

Layout evidence version 1 contains the rectangle, safety padding, address
bounds and page, and compatibility contact height, all in PDF points (72pt
per inch). The helper emits both `<immuknow-layout>` Typst metadata and
extractable `MEASURE_*` PDF markers. Use these same values for preview guides;
do not draw guides into the template or export. Digital checks do not certify
physical envelope alignment: review actual-size printing and the intended
folds with the real stationery.

`signature-block` accepts resolved `signature` content (or none), `name`,
`title`, and `spacing` (2pt). It keeps the block together and emits the required
signature-end evidence. An oversized block may move to a later page; the
`signature_overflow` validation rule detects that. Missing evidence fails
an enabled rule rather than counting as a pass.

`project-layout(settings, notice-key, window: envelope-preset)` resolves project
layout-settings schema 1 into `(paper: ..., window: ...)`. The consumer reads
its project JSON and passes it explicitly. Per-notice paper defaults to
`us-letter`; `us-legal` and `a4` are also supported. The `authored` envelope uses
the supplied window. Named project presets supply numeric `width_pt` and
`height_pt`, preserving that window's position and safety padding. The helper
validates the resolved window; it does not infer folding or physical alignment.
