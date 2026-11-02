# Authoring native Typst notices

Python prepares facts and explicit assignments. Authored Typst projects own
letter prose, display choices, QR destinations and layout. The maintained
branding, names and contacts are examples; replace them with reviewed
PHU content.

Use [Studio](studio.md) for source editing, matching example previews and
project exports. This guide owns the native facts and Typst component contract.

## Select a complete project

Get a starter project from [ImmuKnow Template](https://github.com/WDGPH/ImmuKnow-Template)
or download your authored project from Studio. Template owns the starter letters,
Settings, display translations and example images. Core supplies the shared
Typst library and native contracts; its package contains no starter project.
Keep `setup.typ`, `settings.typ`, `presentation.typ`, `assets/`, `translations/` and
`lib/immuknow/` together in the project's `templates/` directory.

```bash
immuknow clients.csv --template ./my-project/templates/overdue_diseases_v1.en.typ --config ./my-project/config --output ./runs
immuknow clients.csv --notice-assignments ./assignments.json --templates ./my-project/templates --config ./my-project/config --output ./runs
```

Manifest runs require an explicit `--templates` directory. Single-template runs
use the selected file's directory. The directory name has no meaning to the CLI.
Every run stages its own copy and preserves the original authored files.

For your own project, `immuknow.resources.typst_library_root()` locates the
engine's library. Copy that directory to `templates/lib/immuknow/`. Template's
`sync_lib.py` helper does this after an engine upgrade. Obtain starter changes
from Template separately from Core upgrades.

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
#import "setup.typ": *
#show: immuknow.letter // Apply the letter layout

#immuknow.notice-page("Request for Immunization Record")[
  #immuknow.client-block(window: envelope-window)
  As of *#date_as_of*, our files show these overdue immunizations:
  #immuknow.overdue-diseases(include-dose: false)
]
#immuknow.notice-page("Immunization Record")[
  #immuknow.immunization-history()
  #align(center)[End of immunization record]
]
```

`setup.typ` exposes the configured helpers as `immuknow`. Settings reads the
JSON supplied through `sys.inputs.at("data")` and checks trusted compiler inputs
`notice-template`, `notice-version` and `notice-language`. It connects the client
data to the helpers once. Entry points do not repeat data arguments or literal
identity declarations. `#show: immuknow.letter` applies the letter layout and
collects component findings and page count for the whole document.

Core's underlying functions still take explicit data arguments and never read
compiler inputs when imported. Template owns the project setup that makes those
functions ready to use.

Settings holds shared page, envelope, theme, QR and history choices.
Write organization names, mailing addresses, links and phone numbers directly
in the Template where they appear. Keep notice-specific choices there too,
including suspension dates and whether that notice shows a QR code.
Omit helper options when their defaults already express what you want. Its configured
`immuknow.notice-page` helper supplies the header and section styling. Dates are bound
as `date_of_delivery`, `date_as_of` and `date_of_birth`. History remains a lazy
function so a suspension order can omit it without evaluating history display
requirements. The configured `immuknow.immunization-history` and `immuknow.notice-page` helpers accept
named options for one call, after the shared defaults. See
[Template customization](https://github.com/WDGPH/ImmuKnow-Template#customizing)
for examples. The suspension example has one order page and no history or
privacy appendix.

Privacy wording lives directly at the end of each applicable template in an
`#immuknow.privacy-notice[Your privacy wording here.]` block. Edit its wording
and contact details in the Template editor. The helper places the privacy block
at the bottom of the page and reports unexpected continuation. Templates without
a privacy notice simply omit the block; Settings does not insert one automatically.

Use `immuknow.link` for clickable
contacts, for example:

```typst
#immuknow.link("tel:+18005550100;ext=1234")[1-800-555-0100 ext. 1234]
#immuknow.link("mailto:privacy@example.org")
```

Link destinations are checked for HTTPS, email or telephone address format;
the checks do not establish that a destination exists or responds.

Use explicit `true`, `false` and unknown branches for `notice.client_data.over_16`.
Unknown birth/age never means under 16. The maintained examples use neutral
client wording in that case. Address components use the source province.

Link labels stay together by default:

```typst
#immuknow.link("https://example.org/records")[Update your record]
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

Shared setup connects the complete, unchanged `notice` to address, history,
overdue-list and QR helpers. Their placed content records the source row and
client ID. Mixing helpers from
different rows fails the report check, even when the external ID is blank.
Use `immuknow.address-block()` when only the mailing address is needed.
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
Other-column inclusion, invalid-dose omission and chart styling. Settings
supplies the shared defaults; named options on a call change that table only.
Whole-cohort mixed validity produces a warning when
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

Put options used by one component directly in its Template call. For example,
set `style: "bullets"`, `columns: 1` and `include-dose: false` on
`overdue-diseases`. Bullet lists use `indent: 0.8cm` without a surrounding
`#set list` rule; pass `indent: 1cm` to override just that component.
Keep shared page setup and Theme colours in Settings. Write contact details
directly where they appear in the Template.

Use an explicit image path and width inside the signature block:

```typst
#immuknow.signature-block(
  signature: image("assets/signature.png", width: 4.5cm),
  name: "Dr. Annie Body",
  title: "Medical Officer of Health",
)
```

For a smaller signature, change `width: 4.5cm` to `width: 3cm`. Leave height
unspecified to preserve the image's aspect ratio. The helper assumes no default
image filename. Use `signature: none` to omit the image.

The supplied report builder writes version 2 evidence under `report-v2.json`
inside the library. It includes the source row and selected filename as well as
client, version and language. Missing fields, unknown checks/components,
contradictory presence findings and invalid page ranges are refused by native
runs and Studio. Keep the supplied builder; do not write a replacement report
in an authored template.

Use `immuknow.link("https://example.org/record")[Read the record]` for
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

Keep the printed name directly in the signature call. It may include credentials,
for example `name: "Dr. Annie Body, MD"`. The suspension order defines a separate
`order-signatory-name` in its Template for the legal wording, without requiring
the printed signature to use exactly the same text.
