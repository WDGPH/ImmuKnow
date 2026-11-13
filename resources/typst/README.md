# ImmuKnow notice components

Import `lib.typ` from the authored project. Importing the package does not read
client data, inspect compiler inputs, or render components. Core supplies the
prepared facts described by `resources/schemas/rendering.json`.

Text links and URL helpers live in `src/links.typ`; QR rendering lives in
`src/qr.typ`. Use the public helpers exported by `lib.typ` in your templates.

The public helpers take prepared notice data explicitly. Projects can wrap them
to provide shared defaults; see
[ImmuKnow Template's documentation](https://github.com/WDGPH/ImmuKnow-Template/blob/main/README.md)
for its project setup. Core imports never load client data.

For a direct library import, wrap the whole document with
`#show: immuknow.letter.with(notice: notice)`.
The wrapper requires the prepared notice and emits one `<immuknow-report>`
metadata element. `notice-page` applies page styling; `notice-section(title)[body]`
starts a named section and checks whether it continues onto another page.
Set `allow-overflow: true` for intentional continuation. Overflows produce
warnings while preserving visible content.

- `check-notice(notice, version: ..., language: ...)` checks the authored filename
  identity against prepared facts. The caller obtains the trusted identity from
  `notice-version` and `notice-language` compiler inputs.
- `requirements(notice, eligibility: ..., coverage: ...)` must be placed once
  in each notice. Eligibility is `any`, `has_overdue`, `has_overdue_agents`,
  `no_overdue` or `has_ispa_overdue`; coverage is `agents`, `diseases` or
  `neutral`. The neutral declaration is explicit. Conditions that do not fit
  the source facts produce a finding while keeping a readable notice for review.
  Place one declaration in the active branch of a conditional notice.
- `intended-reader(notice)` returns `"student"`, `"guardian"` or `none`. An explicit
  `notice.intended_reader` takes priority over the age default. Address helpers use this
  same selection. `notice-flags(notice)` exposes boolean `to_student` and
  `to_guardian` flags, with both false when the reader is unknown. Reader choice never changes
  age facts or supplies another person's contact details.
- `notice-flags(notice)` returns `to_student`, `to_guardian`, `up_to_date` and
  `no_records` booleans. Reader flags follow `intended-reader(notice)`. `up_to_date`
  means the supplied overdue-disease list is empty, regardless of overdue
  immunizing agents. `no_records` means there were no source administrations,
  before exclusions and history display choices. Both may be true. Projects
  can expose these names from shared setup for `#if` expressions.
  `include-ispa: true` adds `ispa_up_to_date`, using the same birth-cohort-aware
  disease selection as `overdue-diseases(ispa-only: true)`. ISPA selection needs
  a birth date for cohort-dependent diseases and, for earlier meningococcal
  cohorts, `date_as_of`. Missing required facts fail the ISPA-specific operation.
- `notice-dates(notice)` returns localized delivery, as-of, due, suspension and birth dates.
  `long-date(iso, language, required: false)` leaves unknown dates blank.
- `notice-header(title: ..., logo: ..., title-align: center)` places the title
  beside the logo and warns when it exceeds three lines. Set `title-align` to
  `left`, `center`, or `right` to align the title within its column. The same
  option is available on `notice-section`.
- `client-block(notice, window: envelope-preset)` places the address and labeled
  client ID, with details beside the address or below it (`details: "below"`).
  `id-label: "Record number"` changes the label. Each placed ID records its
  source row, value and measured area in the document report.
  The source province is the default. An unknown reader uses a neutral addressee;
  unknown birth dates remain blank and produce a warning when displayed.
  It warns if the client-details area enters the first-page envelope window.
  `window: none` keeps the default block layout without claiming window fit.
  A notice with addresses but no specified window produces a warning.
- `address-block(notice)` places an address on its own and records the source
  row, text and measured area, just as the full client block does. Addresses
  stay on one page; `addressee` and `province` options accept plain text.
- `signature-block(signature: ..., name: ..., title: ...)` permits continuation
  and reports a warning when the signature moves or spans pages. Its
  `allow-overflow: true` option declares intentional continuation.
- `overdue-diseases(notice, include-dose: false)` and `overdue-agents(notice)`
  produce bullets or comma-separated lists. Repeated exact agent names display
  once in their first-occurrence order; the supplied facts remain unchanged.
  Disease names also display once in first-occurrence order; when `include-dose`
  is true, entries with different dose numbers remain distinct.
  `overdue-agents(..., ignore-agents: ("name",))` omits exact matching agent
  names from that list; it is independent of the history table's `ignore-agents`.
  If all agents are omitted, `empty` supplies optional displayed text but the
  empty recommendation still fails the agent display check. Use a visible
  `agent-alternative(notice)[...]` instead when the notice intentionally uses
  other wording; place exactly one agent list or alternative on agent notices.
  Dose numbering describes the
  overdue requirement. Both helpers accept `no-records: auto` to replace their
  list with an English/Canadian French request for records when the source
  contains no administrations. A string or content overrides the message;
  `none` (the default) retains the list. Surrounding prose is unaffected.
  This differs from `empty`, which applies when the overdue list is empty.
  `overdue-diseases(..., ispa-only: true)` filters the displayed disease list
  without changing supplied facts. Varicella applies from the 2010 birth cohort;
  meningococcal scope also follows birth cohort and age. Mixed lists remain
  supported. `ispa-only: true` on `overdue-agents` raises an explicit error.
  See the [authoring guide](https://docs.phiz.ca/immuknow/latest/developer_guide/templates/#ispa-disease-display-and-requirements)
  for the rules and notice requirements.
- `immunization-history(notice, diseases: (...), include-other: true,
  ignore-agents: (), show-validity: true, omit-invalid: false)` derives the
  displayed table from prepared administrations. Valid and invalid doses have
  distinct marks; legend entries appear only for marks used in visible columns.
  Validity display is enabled by default. A history with no validity flags uses
  ordinary recorded-dose marks and no validity legend. A history mixing flagged
  and unflagged doses fails rendering before display exclusions. Explicitly
  disabling validity display uses ordinary recorded-dose marks for all doses.
  `legend-labels` overrides
  the `valid` and `invalid` dose labels and the `unspecified` formulation
  footnote; each has English and Canadian French defaults. Optional age display uses an em dash for unknown ages.
- `qr-code(notice, url: ...)` requires an explicit URL string or function of the
  notice. Disabled QR components do no work. Colours and square, dotted, or
  rounded modules are configurable. The resolved destination is shared by the
  drawn code, PDF link, and report.

`link(destination)[label]` records an external link's destination and
starting page for PDF checks. The label is optional, as with Typst's `link`.
Destinations are checked as HTTPS web addresses, email (`mailto:`) or phone
(`tel:`) links. These checks inspect the address format; they do not contact the
website, email address or phone number. For an extension, use
`link("tel:+18005550100;ext=1234")[1-800-555-0100 ext. 1234]`.
Link text stays together by default and moves to the next line when needed. If it
is wider than a whole line in its enclosing paragraph, column or box, it wraps
normally and reports `layout.link_width` as a warning. Text is not shrunk or
clipped by the helper. Explicit line breaks in an authored label remain. Use
`link(destination, keep-together: false)[label]` to allow normal wrapping
without this width warning.

For client-specific links, encode raw query values once:

```typst
#let record-url(notice) = immuknow.query-url("https://example.test/record", (
  client: notice.client_id,
  name: notice.client_data.name,
))
#let immunization-history(..options) = immuknow.immunization-history(
  notice, diseases: ("Measles", "Mumps", "Rubella"), show-validity: true,
  ..options,
)
```

Insert `#immunization-history()` only where the history should be displayed.
With this wrapper, `#immunization-history(show-age: true)` changes just that table;
options passed at the call override the project defaults.
Unused content emits no component findings. `url-encode(string)` encodes UTF-8
query/path components with RFC 3986 unreserved characters; `query-url` applies
it to raw dictionary keys and values. A fixed URL string is used verbatim.

The report follows `report.json`: `schema_version: 4`, `identity` (`row_key`,
`template`, `client_id`, `version_id`, `language`), actual `page_count`, `checks`,
`qr_urls`, `measurements`, the placed `requirements`, `blocked_checks`, and the `notice` data used for layout. Native and
browser checks compare that data with the prepared input. Each placed personal
component also records `source_matches`; changed helper data is refused even
when its row and client IDs are unchanged. Use helper options for display changes.
`components` has boolean keys `page`, `section`, `header`, `address`, `client`,
`signature`, `history`, `overdue_diseases`, `overdue_agents`, `qr`, `privacy`, and `link`.
Every absent known component has a `not_applicable` check. Checks use `code`,
`stage: "render"`, `status`, `message`, and optional `component`, `page`, and
`measurements`. They are invisible metadata, never hidden PDF text.
Component measurements must agree with presence and absence findings. Page
numbers must fall within the notice and ranges must run forwards. Address,
client, history, overdue-list and QR measurements must name the selected client
and source row, including when the external ID is blank. Unsupported report versions are
refused; there is no conversion of older reports. Successful layout checks omit
duplicate measurements. Address/window and client geometry remains in the placed
component measurements for Studio guides and source targets. Warning/failure
comparisons retain useful detail; coverage and source/display evidence remain
available even when checks pass. See the [evidence retention table](https://github.com/WDGPH/ImmuKnow/blob/main/tests/fixtures/render-evidence.md).

Compile and inspect the same immutable project with a frozen creation timestamp,
then read its report with Typst 0.15.1:

```sh
typst eval --in notice.typ 'query(<immuknow-report>).map(it => it.value)' \
  --format json --creation-timestamp 1780272000
```

QR encoding uses the bundled Rust/WebAssembly plugin in `vendor/qr/`, with
its [third-party notices](vendor/qr/THIRD_PARTY_NOTICES). It includes an explicit UTF-8 encoding declaration
for non-ASCII destinations. URL construction and styled drawing remain in Typst;
plain square symbols use SVG for RGB/grayscale foregrounds and horizontal runs
for other colour spaces. Styled symbols and centre images use a cell matrix;
structural marker geometry is derived from Codetastic. See the
[QR developer guide](https://github.com/WDGPH/ImmuKnow/blob/main/docs/developer_guide/qr.md)
for the protocol, source and build instructions. Native use and Studio need no
Rust installation or downloaded Typst packages.

Bullet lists use `indent: 0.8cm` by default. Set `indent` on the overdue helper
to change that list without changing later lists in the template.

For signature images, names and titles, see the
[template authoring guide](https://github.com/WDGPH/ImmuKnow/blob/main/docs/developer_guide/templates.md).
