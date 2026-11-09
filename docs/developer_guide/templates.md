# Writing notice templates

This guide is for people editing Typst templates or connecting another application.
ImmuKnow supplies the client information and selected notice. Your template controls
the wording, appearance and QR links. The maintained
branding, names and contacts are examples; replace them with reviewed
PHU content.

Use [Studio](../user_guide/studio.md) for source editing, matching example previews and
project exports. This guide owns the native facts and Typst component contract.

## Select a complete project

Get a starter project from [ImmuKnow Template](https://github.com/WDGPH/ImmuKnow-Template)
or use an authored project whose resources match your Core executable. See
[Studio compatibility](../user_guide/studio.md) before using a browser export. Template owns the starter letters,
Settings, display translations and example images. Core supplies the shared
Typst library and native contracts; its package contains no starter project.
Keep `setup.typ`, `settings.typ`, `presentation.typ`, `assets/`, `translations/` and
`lib/immuknow/` together in the project's `templates/` directory.

```bash
immuknow run clients.csv --template ./my-project/templates/overdue_diseases.en.typ --config ./my-project/config --output ./runs
immuknow run clients.csv --notice-assignments ./assignments.json --templates ./my-project/templates --config ./my-project/config --output ./runs
```

Manifest runs use `--templates`, the `--project` templates folder, or local
`templates/` when neither is supplied. Single-template runs
use the selected file's directory. The directory name has no meaning to the CLI.
Every run stages its own copy and preserves the original authored files.

Export the library with `immuknow resources --output ./resources` and copy
`resources/typst/` intact to `templates/lib/immuknow/`. Obtain starter notices
and project-specific changes from Template separately.

Keep `lib/immuknow/` complete and unchanged, including its nested files. Native
runs and saved-run bundling check its bytes against the supplied library;
Studio integrations should use the same exported copy. Rewriting a project
manifest does not approve an edited copy. Linked library
paths are refused. Put your own helpers outside that directory, and edit notice
prose, Settings, assets and project translations there. Studio opens supplied
library files for reading only.

This check protects the supplied components. It does not establish that arbitrary
text or drawing added elsewhere in an authored template belongs to the right
client; review authored content as well as the reported checks.

Keep dependencies inside this tree and import them through relative paths.
Core refuses `@local` and `@preview` package imports, including paths built from
variables. Keep library dependencies inside the project; Core does not download
packages or read a package installed elsewhere. Check the same restriction in Studio
when updating its integration.

The filename `<version>.<language>.typ` supplies version and language. Rename
only when the authored prose matches the intended language. Selection never
changes language or chooses a different notice automatically. See
[configuration](../user_guide/configuration.md) for the explicit manifest schema and
warning/failure behavior.

## Entry points and Settings

The opening stays short:

```typst
// Essential setup: keep these opening lines.
// @immuknow-settings: settings.typ
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
as `date_of_delivery`, `date_as_of`, `date_due`, `date_of_suspension` and
`date_of_birth`. Unset optional dates format as an empty string. History remains a lazy
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

Shared setup supplies boolean `to_student` and `to_guardian` flags:

```typst
#if to_student [you have] else if to_guardian [your child has] else [the named client has]
```

Only one flag can be true. Core's `intended-reader(notice)` helper uses the source
`intended_reader` choice first, then the age default: student at 16 or older, guardian
under 16. Without a choice or known age, both flags are false and the neutral
branch applies. Address components use the same selection and source province.
Use a helper's explicit `addressee:` option when authored wording requires a
particular label. The suspension starter uses the same reader flags for its service wording,
reader heading and default addressee. Age facts remain available independently
of the intended reader.
See [intended reader](../user_guide/getting_started.md#intended-reader) for CSV overrides and
mailing destinations.

Link labels stay together by default:

```typst
#immuknow.link("https://example.org/records")[Update your record]
```

The label moves intact to the next line when needed. A label wider than a whole
line wraps normally and produces a `layout.link_width` warning for review.
Use `keep-together: false` to allow normal wrapping without this width warning.

## Facts contract

`resources/schemas/rendering.json` is the structural contract. The pipeline validates
it before compilation; strings remain literal data rather than executable source.

| Field | Meaning |
|---|---|
| `schema_version` | Integer `1` |
| `row_key`, `client_id` | Stable original CSV row key and string source identifier |
| `template`, `version_id`, `language` | Explicit selected filename and its resolved identity |
| `intended_reader` | Optional `student` or `guardian` override; null or absent uses the age default in Typst |
| `client_data` | Client names, initials, mailing address, school, birth date and age |
| `school`, `board` | Source name and identifier |
| `date_of_delivery`, `date_as_of` | ISO dates or blank |
| `date_due`, `date_of_suspension` | Optional ISO dates, null or blank; absent on older payloads |
| `overdue_diseases` | `{disease, dose}` facts; invalid numeric doses retain `dose_raw` |
| `overdue_agents` | Source vaccine agent names |
| `history` | Normalized administrations with ISO `date_given`, `agent`, `display_name`, configured `diseases`, `validity` and boolean `mapping_known` |
| `validity_coverage` | Whole-file `all_present`, `all_absent` or `mixed` |
| `has_immunization_records` | Whether the source contains any administrations before exclusions or deduplication |
| `history_validity_coverage` | Per-history source flag coverage, before exclusions and deduplication: `all_present`, `all_absent` or `mixed` |

The fields inside `client_data` are:

| Field | Meaning |
|---|---|
| `first_name`, `last_name`, `name` | First name, last name and full name |
| `first_initial`, `last_initial` | First character of the corresponding name, after removing surrounding spaces |
| `address`, `city`, `province`, `postal_code` | Mailing address |
| `school` | School name |
| `date_of_birth_iso` | Birth date as `YYYY-MM-DD`, or blank when unavailable |
| `age` | Age in years on the delivery date, or null when unknown |

For student or guardian wording, use `to_student` and `to_guardian` as described
in [Entry points and Settings](#entry-points-and-settings). The `age` field
supplies the age-based default; an explicit `intended_reader` choice takes priority and
does not change the age facts.

Each initial is the first character after removing spaces around the corresponding
name. It keeps the original case and accents: `Élodie` gives `É`. A missing name
produces an empty string. QR destination functions can use
`notice.client_data.first_initial` and `notice.client_data.last_initial`.

A missing birth date is blank, and unknown `age` is JSON null. Blank
source values and unusable fragments are retained in `run.json` with preparation
findings. Display options leave prepared administrations and disease mappings
unchanged.

Each history item's `mapping_known` records whether the selected vaccine reference
contains that exact agent name. Unknown names retain an empty `diseases` list and
`mapping_known: false`. An explicit reference entry with an empty disease list
has `mapping_known: true`; it remains distinct from an unknown name.

## Record and overdue flags

In `settings.typ`, `immuknow.notice-flags(notice)` returns four booleans for shared setup:

```typst
#let flags = immuknow.notice-flags(notice)
#let to_student = flags.to_student
#let to_guardian = flags.to_guardian
#let up_to_date = flags.up_to_date
#let no_records = flags.no_records
```

`to_student` and `to_guardian` follow the same intended-reader selection as the
address block. `up_to_date` is true when the supplied overdue-disease list is
empty; overdue immunizing agents do not affect it. This reflects the supplied
assessment, rather than assessing vaccination requirements in Core.
`no_records` is true when no administrations were supplied in the source history.
Invalid doses, unknown vaccine names and records excluded from the displayed
chart still count as records. A blank history or the source's empty-history
placeholder does not. The two record/overdue flags are independent and may both
be true.

Use the flags for individual phrases or to omit an entire section:

```typst
#if not no_records and not up_to_date [
  Our records show the following outstanding disease requirements:
  #immuknow.overdue-diseases()
]
```

To replace only a list, both `overdue-diseases` and `overdue-agents` accept
`no-records: auto`. When no records were supplied, the helper shows a request
for vaccination records instead of the list, using English or Canadian French
wording selected by its language. This does not change surrounding paragraphs.

```typst
#immuknow.overdue-diseases(no-records: auto)
#immuknow.overdue-agents(no-records: [Please send any vaccination records you have.])
```

`no-records: none` is the default and retains the regular list. A string or
Typst content overrides the no-records message; the override is used only when
there are no source records. This is separate from `empty`, which supplies
content when the overdue list itself is empty. Prepared overdue lists, facts,
notice assignments and bundle checks remain intact.

Repeated normalized diseases display once in their first-occurrence order when
dose numbers are hidden. With `include-dose: true`, entries with different
dose numbers remain distinct. Repeated exact agent names also display once.
The supplied facts are unchanged, and preparation warns about repeated
diseases or agents independently of display filters and no-records messages.

To omit particular vaccine names from an overdue-agent list, pass exact source
names, for example `overdue-agents(ignore-agents: ("Example vaccine",))`.
Matching is case-sensitive. The option affects this list only; the history
table's `ignore-agents` is configured separately. If every agent is omitted,
`empty` supplies optional replacement content. A `no-records` replacement takes
precedence when no source records exist. Facts and coverage checks are unchanged.

### ISPA disease display and assertions

`overdue-diseases(ispa-only: true)` shows the applicable ISPA subset of the
supplied overdue diseases. Mixed ISPA/non-ISPA input remains valid; the default
`ispa-only: false` shows the complete list. Dose numbers and selected translations
are preserved. `overdue-agents(ispa-only: true)` is unsupported and raises an
error, including when a no-records replacement would otherwise be shown.

ISPA selection uses canonical disease identifiers and the client's birth cohort:
Diphtheria, Tetanus, Polio, Measles, Mumps, Rubella and Pertussis are included;
Varicella is included for births on or after January 1, 2010. Meningococcal
disease applies to births on or after September 1, 2004, or births on or after
January 1, 1997 once the client is 12. The earlier meningococcal cohort uses
`date_as_of` for that age boundary. These scope rules come from
[Ontario's school requirements](https://www.ontario.ca/page/vaccines-children-school)
and [Regulation 645, Table 1](https://www.ontario.ca/laws/regulation/900645).
They select already-reported overdue diseases; they do not reassess doses,
exemptions or the other legal steps needed for a suspension order.

In a letter, when ISPA status is needed, request the additional boolean explicitly:

```typst
#let flags = immuknow.notice-flags(include-ispa: true)
#let ispa_up_to_date = flags.ispa_up_to_date
#assert(not ispa_up_to_date,
  message: "This suspension notice requires an applicable overdue ISPA disease.")
#immuknow.overdue-diseases(ispa-only: true)
```

`ispa_up_to_date` uses the same selection as the list and is independent of
`up_to_date`, which always considers the complete overdue-disease list.
Requesting ISPA selection fails if a birth date needed for Varicella or
Meningococcal applicability is missing or invalid, or if `date_as_of` is missing
when needed for the meningococcal age boundary. The default four flags and
ordinary lists remain available without those ISPA-specific facts.

An affirmative template can guard its wording explicitly:

```typst
#assert(up_to_date, message: "This notice requires no overdue diseases.")
```

The catalog's `no_overdue` rule checks the same disease-based condition before
rendering; it is the default for `kind: affirmative`. Applicability conflicts
warn while preserving explicit assignments. A template assertion makes this a
mandatory rendering error, close to the wording it protects. A dynamic notice that handles several
cases internally can use `requires: any` and branch on the flags. Its selected
version and language stay fixed. Explicit filename assignments remain available
for distinct wording, customization and A/B testing; Core does not choose a
notice from these flags.

## Component choices and findings

Use `client-block` for the mailing address and client details. Its independent
`show-client-id: true` and `show-oiid: false` options allow either identifier,
both, or neither. Client ID remains the assignment and run identifier even when
hidden. The optional input CSV column `oiid` supplies the Ontario Immunization
ID as text, preserving leading zeros. The prepared notice exposes `oiid` and
`oiid_coverage` (`all_present`, `mixed`, or `all_absent`) for custom content.

Enabling `show-oiid` requires at least one nonblank OIID in the input file;
an input file with no OIIDs fails rendering until the input or display
choice is corrected. In a mixed input file, `missing-oiid` controls clients without
an OIID: `none` (the default) omits the line, `""` leaves the value blank after
the label, `auto` shows “Not available” / “Non disponible”, and a plain-text
string supplies custom wording. This option applies only with `show-oiid: true`;
it does not replace an available OIID or bypass the error when every row lacks OIID.
An omitted or blank OIID column remains supported with OIID display disabled.
Set `id-label: "Record number"`, `oiid-label: "Record key"`, or `school-label`
to customize plain-text labels. Default labels are provided in English and
Canadian French. `show-birth-date` and `show-school` independently control the
other details. If every detail is hidden or absent, only the mailing address
is placed.

The helper records the displayed client-details and mailing-address areas.
Hidden identifiers are not required in the PDF. Repeated blocks are allowed
when each belongs to the same source row.

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
plain text.
Change presentation through helper options; correct factual errors in the input.
The report retains the notice data used for layout and checks that each placed
helper used the same data. Native and browser checks compare it with the prepared input.

`immunization-history` accepts disease columns, ignored agents, validity markers,
Other-column inclusion, invalid-dose omission and chart styling. Settings
supplies the shared defaults; named options on a call change that table only.
The formulation footnote appears only when a displayed vaccine name contains
`*`, as in `HB*` for `HB-unspecified`. The full source name is used for lookup;
the marker means its formulation is unspecified. Ignored agents and omitted
invalid doses do not trigger it.
Valid and invalid legend entries appear only when their marks occur in the
visible disease columns. Each footnote and legend item has an English and
Canadian French default, selected by the chart's language. The validity wording
explains whether a dose counts toward vaccination requirements.

Customize individual items with `legend-labels`; omitted items keep their
localized defaults. Values accept plain text or Typst content. Use `valid`,
`invalid` and `unspecified` as keys. The first two label dose-validity marks;
`unspecified` explains the formulation asterisk. For example:

```typst
#immuknow.immunization-history(
  show-validity: true,
  legend-labels: if notice.language == "fr" {
    (valid: "Dose prise en compte dans les exigences de vaccination",
     invalid: "Dose non prise en compte dans les exigences de vaccination")
  } else {
    (valid: "Dose counts toward vaccination requirements",
     invalid: "Dose does not count toward vaccination requirements")
  },
)
```

Include the `*` in an override for the `unspecified` footnote.
Validity display is enabled by default (`show-validity: true`). A history with
no validity flags remains supported: it uses ordinary recorded-dose marks and
has no validity legend. A history containing both flagged and unflagged doses
fails rendering even if deduplication or display exclusions would hide the
missing flags; correct the source or explicitly
set `show-validity: false`. There is no separate marker or legend for missing
validity flags. Notices still warn when validity coverage varies across their
cohort. Invalid source history rejects input before rendering; its fragments
remain in the run report. Omitted components produce
no component checks, but do not bypass source validation.

Each placed history table checks the prepared agents against its own evaluated
`ignore-agents` list. Any remaining agent with `mapping_known: false` produces a
`content.history_mapping` error. This check runs before `omit-invalid` and does
not depend on whether the Other column is shown. An explicit exclusion in one
table applies only to that table.

A mapping error alone leaves a successfully rendered PDF in review and prevents
sending. It cannot be disabled, downgraded or accepted as a warning. Correct the
source name or reference entry, or add an explicit agent exclusion and generate
a new run. A notice without a history table has no history-mapping check. Other
errors, such as mixed validity flags, can prevent compilation entirely.

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
The client block defaults to `font-size: 10pt` and `details: "right"`. Omit those
options unless changing them on that call. Omit QR calls in letters without a
QR code. Keep shared page setup and Theme colours in Settings. Write contact details
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

The supplied report builder creates invisible document metadata described by
`report.json` inside the library (`schema_version: 2`). It does not add report pages
or attach a JSON file to the PDF. It includes the source row and selected filename as well as
client, version and language. Missing fields, unknown checks/components,
contradictory presence findings and invalid page ranges are refused by native
runs and Studio. Keep the supplied builder; do not write a replacement report
in an authored template.

Use `immuknow.link("https://example.org/record")[Read the record]` for
external links. It also accepts `mailto:` and `tel:` destinations. Omitting the
bracketed text keeps Typst's default label.

In the starter's `settings.typ`, use a fixed QR destination or a function of
the notice's client facts:

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

QR presentation options are optional. The defaults keep connected, borderless
squares, one foreground colour and a four-module white quiet zone.

| Option | Values and meaning |
| --- | --- |
| `foreground`, `background` | Dark module colour and quiet-zone/background colour; default black and white. |
| `corner-foreground` | Colour of the three large finder targets; `auto` inherits `foreground`. |
| `alignment-foreground` | Colour of smaller internal alignment targets, where present; `auto` inherits `foreground`. Timing and other structural cells retain `foreground`. |
| `module-shape` | `"square"` connects touching squares; `"separated"` leaves a gap equal to 20% of a cell between data squares; `"dots"` uses circles; `"rounded"` rounds individual data squares. Structural markers retain their shapes. |
| `corner-style` | `"square"` or `"rounded"` for the three finder targets. |
| `logo` | Typst image content, or an image/mask dictionary supplied by Studio; default `none`. |
| `logo-size`, `logo-padding` | Centre image width as 5–30% of the encoded grid, and its clearing border (0–1mm). |
| `error-correction` | `auto` uses `"l"` without an image and `"h"` with one; explicit `"l"`, `"m"`, `"q"`, `"h"` are also accepted. Images require `"h"`. |

For example, set `module-shape: "separated"` and
`corner-foreground: rgb("176b78")` in the QR settings dictionary. An authored
centre graphic can use `logo: image("assets/mark.svg", width: 100%)`.
An image clearing area that overlaps a structural marker is rejected; reduce its
size or padding. This check does not guarantee scanning after image occlusion.
Keep both foreground colours dark against a light background and test actual
printed output. The library does not automatically assess colour contrast.

Custom styles add drawing work; unstyled RGB/grayscale square codes use a
compact SVG path generated in Rust. Other foreground colour spaces retain
native Typst curves. See [QR implementation](qr.md) for the encoder and verification.

The helper percent-encodes query values, adds them before any `#section`, and
uses the same destination for its code and link. Existing query values are kept.
The pipeline supplies facts; the authored template defines QR destinations.

To include initials, add `first_initial: notice.client_data.first_initial` and
`last_initial: notice.client_data.last_initial` alongside the other URL values.
Initials are used only when included in this function.

Project display translations are editable in `translations/`; the library has
its own packaged localization resources.

## Reproduce and review a notice

The authoritative `runs/<run-id>/run.json` records source rows, facts,
assignments, checks and original PDF paths. The run stages the selected project
under `resources/templates/` and facts under `facts/<row_key>.json`. Review the retained original PDFs and findings in `report.html` and `run.json`.
Inspect English/French,
unknown-age, long-address and long-history examples, including QR links,
window placement, signatures, symbols and page continuation. The
[testing guide](testing.md) describes repeatable checks.

Keep the printed name directly in the signature call. It may include credentials,
for example `name: "Dr. Annie Body, MD"`. The suspension order defines a separate
`order-signatory-name` in its Template for the legal wording, without requiring
the printed signature to use exactly the same text.

## Page title alignment

Set `title-align` to `left`, `center` or `right` in project Settings. The starter
`notice-page` wrapper passes this choice to the shared header. A named override
changes only one page:

```typst
#immuknow.notice-page("Immunization Record", title-align: left)[
  #immuknow.immunization-history()
]
```

Alignment applies within the title's existing column; it does not move the logo.
The logo-free header aligns within the full width. Header height and title-line
checks continue to use the rendered heading.
