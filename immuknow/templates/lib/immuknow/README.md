# ImmuKnow notice components

Import `lib.typ` from the authored project. Importing the package does not read
client data, inspect compiler inputs, or render components. Python supplies the
prepared facts described by `immuknow/schemas/rendering-v1.json`.

Wrap the whole document with `#show: immuknow.notice-style.with(notice: notice)`.
The wrapper requires the prepared notice and emits one `<immuknow-report>`
metadata element. `notice-page` applies page styling; `notice-section(title)[body]`
starts a named section and checks whether it continues onto another page.
Set `allow-overflow: true` for intentional continuation. Overflows produce
warnings while preserving visible content.

Configure helper options in the project's Settings file. There is no Python
display-default adapter or separate layout-settings file.

- `check-notice(notice, version: ..., language: ...)` checks the authored filename
  identity against prepared facts. The caller obtains the trusted identity from
  `notice-version` and `notice-language` compiler inputs.
- `notice-dates(notice)` returns localized delivery, as-of, and birth dates.
  `long-date(iso, language, required: false)` leaves unknown dates blank.
- `notice-header(title: ..., logo: ...)` centers the title beside the logo and
  warns when it exceeds three lines.
- `client-block(notice, window: envelope-preset)` places the address and labeled
  client ID, with details beside the address or below it (`details: "below"`).
  `id-label: "Record number"` changes the label. Each placed ID records its
  source row, value and measured area for checking against the PDF text.
  The source province is the default. Unknown age uses a neutral addressee;
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
  produce bullets or comma-separated lists. Dose numbering describes the
  overdue requirement.
- `immunization-history(notice, diseases: (...), include-other: true,
  ignore-agents: (), show-validity: false, omit-invalid: false)` derives the
  displayed table from complete administrations. Valid, invalid, and unknown
  validity have distinct marks and a matching legend. Unparsed entries appear
  below the table. Optional age display uses an em dash for unknown ages.
- `qr-code(notice, url: ...)` requires an explicit URL string or function of the
  notice. Disabled QR components do no work. Colours and square, dotted, or
  rounded modules are configurable. The resolved destination is shared by the
  drawn code, PDF link, and report.

`notice-link(destination)[label]` records an external link's destination and
starting page for PDF checks. The label is optional, as with Typst's `link`.
Use `notice-link(destination, keep-together: true)[label]` to prevent automatic
line breaks inside the link text. It moves to the next line when needed. If it
is wider than a whole line in its enclosing paragraph, column or box, it wraps
normally and reports `layout.link_width` as a warning. Text is not shrunk or
clipped by the helper. Explicit line breaks in an authored label remain.

For client-specific links, encode raw query values once:

```typst
#let record-url(notice) = immuknow.query-url("https://example.test/record", (
  client: notice.client_id,
  name: notice.client_data.name,
))
#let immunization-history() = immuknow.immunization-history(
  notice, diseases: ("Measles", "Mumps", "Rubella"), show-validity: true,
)
```

Insert `#immunization-history()` only where the history should be displayed.
Unused content emits no component findings. `url-encode(string)` encodes UTF-8
query/path components with RFC 3986 unreserved characters; `query-url` applies
it to raw dictionary keys and values. A fixed URL string is used verbatim.

The report follows `report-v2.json`: `schema_version: 2`, `identity` (`row_key`,
`template`, `client_id`, `version_id`, `language`), actual `page_count`, `checks`,
`qr_urls`, `measurements`, and the `notice` data used for layout. Native and
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
refused; there is no conversion of older reports.

Compile and inspect the same immutable project with a frozen creation timestamp,
then read its report with Typst 0.15.1:

```sh
typst eval --in notice.typ 'query(<immuknow-report>).map(it => it.value)' \
  --format json --creation-timestamp 1780272000
```

Bundled QR drawing code is derived from Codetastic; its licence and upstream
provenance are in `vendor/codetastic/`. Local changes support styled drawing and
UTF-8 text with an explicit encoding declaration and matching size calculation.
