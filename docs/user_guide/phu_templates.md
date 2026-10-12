# Authoring native Typst notices

Python prepares facts and explicit assignments. Authored Typst projects own
letter prose, display choices, QR destinations and layout. The maintained
branding, names and contacts are synthetic examples; replace them with reviewed
PHU content.

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

For an installed wheel, use `importlib.resources.files("immuknow")` to locate
and copy its `templates` directory. The selected tree supplies all authored
helpers and assets. It is staged once in the run; installed files remain read-only.

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

Use explicit `true`, `false` and unknown branches for `notice.client_data.over_16`.
Unknown birth/age never means under 16. The maintained examples use neutral
client wording in that case. Address components use the source province.

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
| `unparsed_history` | Original unusable fragments, visibly retained when history is inserted |

A missing birth date is blank, and unknown `age`/`over_16` are JSON null. Blank
source values and unusable fragments are retained in `run.json` with preparation
findings. Display choices never alter administrations or disease mappings.

## Component choices and findings

`immunization-history` accepts disease columns, ignored agents, validity markers,
Other-column inclusion, invalid-dose omission and chart styling. Settings is the
only owner of these options. Whole-cohort mixed validity produces a warning when
validity display is requested. The displayed history preserves unexpected raw
fragments so they remain reviewable. Omitted components produce no component checks.

The package provides page/header, address/client, signature, history, overdue
lists and QR helpers. Warnings retain visible content and useful PDFs. Long
content continues onto extra pages and reports unexpected continuation; authors
can explicitly allow intentional overflow. Structural misuse or compiler errors
can prevent a PDF. Report findings show which components were used, their checks,
resolved QR URLs and layout measurements.

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

The helper percent-encodes query values and uses the same resolved destination
for its code and link. Python supplies facts and creates no QR images or URLs.
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
