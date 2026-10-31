# Authoring native Typst notices

Python prepares facts and explicit assignments. Authored Typst projects own
letter prose, display choices, QR destinations and layout. The maintained
branding, names and contacts are examples; replace them with reviewed
PHU content.

Use [Studio](studio.md) for source editing, matching example previews and
project exports. This guide owns the native facts and Typst component contract.

## Select a complete project

Copy `immuknow/templates/`, including `settings.typ`, `presentation.typ`,
`assets/`, `translations/` and `lib/immuknow/`, to a directory you control.
The six maintained entry points are English/French overdue disease and agent
notices, an English affirmative notice and an English suspension order.

```bash
cp -r immuknow/templates ./my-phu
immuknow clients.csv --template ./my-phu/overdue_diseases_v1.en.typ --output ./runs
immuknow clients.csv --notice-assignments ./assignments.json --templates ./my-phu --output ./runs
```

Keep PHU templates outside the ImmuKnow checkout, or beneath its
`phu_templates/` directory, which Git ignores. The directory name has no
meaning to the CLI; always pass the path explicitly.

For an installed wheel, use `importlib.resources.files("immuknow")` to locate
and copy its `templates` directory. The selected tree supplies all authored
helpers and assets. It is staged once in the run; installed files remain read-only.

Keep `lib/immuknow/` complete and unchanged, including its nested files. Native
runs, saved-run delivery and Studio check its bytes against the supplied library;
rewriting a project manifest does not approve an edited copy. Linked library
paths are refused. Put your own helpers outside that directory, and edit notice
prose, Settings, assets and project translations there. Studio opens supplied
library files for reading only.

This check protects the supplied components. It does not establish that arbitrary
text or drawing added elsewhere in an authored template belongs to the right
client; review authored content as well as the reported checks.

Keep dependencies inside this tree and import them through relative paths.
Native runs and Studio refuse `@local` and `@preview` package imports, including
paths built from variables. Native compilation uses private package directories
and blocks downloads before connecting; it cannot use a package installed elsewhere.

The filename `<version>.<language>.typ` supplies version and language. Rename
only when the authored prose matches the intended language. Selection never
changes language or chooses a different notice automatically. See
[configuration](configuration.md) for the explicit manifest schema and
warning/failure behavior.

## Entry points and Settings

The opening stays short:

```typst
#import "settings.typ": *
#show: notice-style

#notice-page("Request for Immunization Record")[
  #immuknow.client-block(notice, window: envelope-window)
  As of *#date_as_of*, our files show these overdue immunizations:
  #immuknow.overdue-diseases(notice, include-dose: include-dose)
]
#notice-page("Immunization Record")[
  #immunization-history()
  #align(center)[End of immunization record]
]
```

Settings imports `lib/immuknow/lib.typ` as `immuknow`, reads the JSON supplied
through `sys.inputs.at("data")`, and checks trusted compiler inputs
`notice-template`, `notice-version` and `notice-language`. Entry points do not
repeat literal identity declarations. `notice-style` receives `notice:` and
wraps the whole document, collecting native component findings and page count.

Settings follows page/envelope, theme and letter-feature order. Its configured
`notice-page` helper supplies the header and section styling. Dates are bound
as `date_of_delivery`, `date_as_of` and `date_of_birth`. History remains a lazy
function so a suspension order can omit it without evaluating history display
requirements. The suspension example has one order page and no history or
privacy appendix.

Privacy wording lives directly at the end of each applicable template in an
`#immuknow.privacy-notice[Your privacy wording here.]` block. Edit its wording
and contact details in the Template editor. The helper places it at the bottom
of the page and reports unexpected continuation. Templates without a privacy
notice simply omit the block; Settings does not insert one automatically.

Use explicit `true`, `false` and unknown branches for `notice.client_data.over_16`.
Unknown birth/age never means under 16. The maintained examples use neutral
client wording in that case. Address components use the source province.

Link labels stay together by default:

```typst
#immuknow.notice-link("https://example.org/records")[Update your record]
```

The label moves intact to the next line when needed. A label wider than a whole
line wraps normally and produces a `layout.link_width` warning for review.
Use `keep-together: false` to allow normal wrapping without this width warning.

## Facts contract

`immuknow/schemas/rendering-v1.json` is the structural contract. Python validates
it before compilation; strings remain literal data rather than executable source.

| Field | Meaning |
|---|---|
| `schema_version` | Integer `1` |
| `row_key`, `client_id` | Stable original CSV row key and string source identifier |
| `template`, `version_id`, `language` | Explicit selected filename and its resolved identity |
| `client_data` | Name parts, full name, address/city/province/postal code, school, ISO birth date, age and `over_16` |
| `school`, `board` | Source name and identifier |
| `date_of_delivery`, `date_as_of` | ISO dates or blank |
| `overdue_diseases` | `{disease, dose}` facts; invalid numeric doses retain `dose_raw` |
| `overdue_agents` | Source vaccine agent names |
| `history` | Normalized administrations with ISO `date_given`, `agent`, `display_name`, complete `diseases` and `validity` |
| `validity_coverage` | Whole-cohort `all_present`, `all_absent` or `mixed` |

A missing birth date is blank, and unknown `age`/`over_16` are JSON null. Blank
source values and unusable fragments are retained in `run.json` with preparation
findings. Display choices never alter administrations or disease mappings.

## Component choices and findings

Use `client-block` for the client ID. Set `id-label: "Record number"` to change
its label without changing the check. Labels for the ID and school accept plain
text. The helper records the client-details area; Python checks its ID, displayed
birth date and school against the PDF text, allowing spaces and line breaks to
change. Repeated blocks are allowed when each belongs to the same source row.

Pass the complete, unchanged `notice` to address, history, overdue-list and QR helpers too.
Their placed content records the source row and client ID. Mixing helpers from
different rows fails the report check, even when the external ID is blank.
Use `address-block(notice)` when only the mailing address is needed.
Use `window: none` on `client-block`, or set `envelope-window = none` in Settings,
when no envelope window is specified. The client block uses its default layout;
fit and overlap checks are not applicable. A notice with addresses but no
specified window warns. This also covers notices using only `address-block`.
Address blocks stay on one page. The `addressee` and `province` options accept
plain text. Python checks the mailing name and address in each block against
the PDF, allowing changes in spaces and line breaks.
Change presentation through helper options; correct factual errors in the input.
The report retains the notice data used for layout and checks that each placed
helper used the same data. Native and browser checks compare it with the prepared input.

`immunization-history` accepts disease columns, ignored agents, validity markers,
Other-column inclusion, invalid-dose omission and chart styling. Settings is the
only owner of these options. Whole-cohort mixed validity produces a warning when
validity display is requested. Invalid source history rejects input before
rendering; its fragments remain in the run report. Omitted components produce
no component checks, but do not bypass source validation.

History marks use the same `indicator-font` and `indicator-size` in the table
and its legend. The default FreeSans marks keep their size and centring when
the letter typeface changes. `indicator-offset` adjusts mark placement inside
table cells.

The package provides page/header, address/client, signature, history, overdue
lists, links and QR helpers. Warnings retain visible content and useful PDFs. Long
content continues onto extra pages and reports unexpected continuation; authors
can explicitly allow intentional overflow. Structural misuse or compiler errors
can prevent a PDF. Report findings show which components were used, their checks,
resolved QR URLs and layout measurements.

The supplied report builder writes version 2 evidence under `report-v2.json`
inside the library. It includes the source row and selected filename as well as
client, version and language. Missing fields, unknown checks/components,
contradictory presence findings and invalid page ranges are refused by native
runs and Studio. Keep the supplied builder; do not write a replacement report
in an authored template.

Use `immuknow.notice-link("https://example.org/record")[Read the record]` for
external links. It also accepts `mailto:` and `tel:` destinations. Omitting the
bracketed text keeps Typst's default label. Python compares its destination with
a clickable link on the recorded page, including during saved-run delivery.

QR Settings uses an explicit fixed string or a function of normalized facts:

```typst
#let qr = (
  url: notice => immuknow.query-url("https://example.org/update", (
    client_id: notice.client_id,
    dob: notice.client_data.date_of_birth_iso,
    lang: notice.language,
  )),
  width: 3cm,
)
```

The helper percent-encodes query values, adds them before any `#section`, and
uses the same destination for its code and link. Existing query values are kept.
Python supplies facts and creates no QR images or URLs.
Project display translations are editable in `translations/`; the library has
its own packaged localization resources.

## Reproduce and review a notice

The authoritative `runs/<run-id>/run.json` records source rows, facts,
assignments, checks and original PDF paths. The run stages the selected project
under `resources/templates/` and facts under `facts/<row_key>.json`. To review a
retained notice with Typst 0.15.1:

```bash
typst compile --root ./runs/<run-id> \
  --input data=/facts/row-000001.json \
  --input notice-template=overdue_diseases_v1.en.typ \
  --input notice-version=overdue_diseases_v1 --input notice-language=en \
  ./runs/<run-id>/resources/templates/overdue_diseases_v1.en.typ ./review.pdf
```

The root bounds file reads. A manual compile aids visual review; the complete
pipeline also records findings and delivery accounting. Inspect English/French,
unknown-age, long-address and long-history examples, including QR links,
window placement, signatures, symbols and page continuation. The
[testing guide](../developer_guide/testing.md) describes repeatable checks.
