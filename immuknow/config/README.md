# Configuration and notice contract

Python run options and source references live in `immuknow/config/`. Use
`--config DIRECTORY` for your own directory. The input field contract lives
in `immuknow/schemas/input_schema.json`; it is maintained with preparation code.

## Files and responsibilities

| File | Purpose |
|---|---|
| `parameters.yaml` | Delivery/as-of dates, compiler, validation, encryption and bundling |
| `vaccine_reference.json` | Agent names mapped to complete normalized disease lists |
| `disease_normalization.json` | Source disease variants mapped to normalized names |
| `school_reference.json` | Optional school matching reference |
| `notice_versions.yaml` | Named applicability checks for explicitly selected notices |

Authored project configuration and starter letters are maintained in ImmuKnow
Template. Core ships reference configuration and accepts `--config DIRECTORY`.
Authored display choices belong in the project’s `templates/settings.typ`. This includes
history columns, hidden agents, validity markers, overdue dose wording, QR
options, page geometry, theme and assets. Contact details belong directly in the letter source. Approved display
labels live in `templates/translations/`. Python preserves all normalized
administrations and mappings independently of those choices. Retired Python
settings (`qr`, `preprocess`, `ignore_agents`, `chart_diseases_header` and
`notice_versioning`) are rejected with a direction to Settings.

## Run options

Unknown settings, repeated JSON/YAML fields and wrong value types stop the run
before notices are generated. This also applies to settings for disabled
features. Use YAML booleans (`true` or `false`) and numeric values directly;
quote dates, for example `date_as_of: "2026-01-02"`. Supplied dates must be real
`YYYY-MM-DD` dates; an empty string leaves an optional run date unset.
YAML aliases may reuse values, but merged fields cannot overwrite other fields.

| Key | Meaning |
|---|---|
| `date_of_delivery` | ISO date used to calculate age; absent/unusable birth dates leave age unknown |
| `date_as_of` | ISO as-of date displayed in the letter; does not filter administrations |
| `typst.bin` | Native compiler executable |
| `typst.timeouts_seconds` | Per-operation native compiler deadlines; see below |
| `encryption.enabled`, `encryption.password.template` | Optional individual PDF encryption |
| `bundling.bundle_size`, `bundling.group_by` | Number of notices per bundle and optional grouping fields; see below |
| `validation.notice_length` | Optional fixed PDF page count per notice; requires `enabled: true`, a positive `count`, and `unit: pages` |
| `school_validation.enabled` | Compare source school names with the selected reference (packaged `school_reference.json` when `reference_file` is unset) |

The [PDF validation guide](https://docs.phiz.ca/immuknow/latest/user_guide/pdf_validation/)
describes output measurements. Run findings and output accounting are recorded
in the authoritative `run.json`.

### Group delivery bundles

Bundles support review and help organize printed notices for handling. Group by
board, language or page count to suit your process, including separating longer
notices that need hand folding. Review bundles include review sheets; delivery
bundles contain original notice pages. Encrypted PDFs remain separate individual
outputs. See [PDF checks and review](https://docs.phiz.ca/immuknow/latest/user_guide/pdf_validation/#bundle-contents).

Set `bundle_size` to the maximum number of notices in a bundle, or `0` to
leave bundling off. Use `group_by` to keep notices with the same school ID, board ID,
notice language, or PDF page count together:

```yaml
bundling:
  bundle_size: 100
  group_by: [board, language, page_count]
```

This example makes separate bundles for each combination. `language` comes from
the assigned notice, and `page_count` is the number of pages in the original
PDF. `school` and `board` use the source IDs, not the names. Use any combination
of `school`, `board`, `language`, and `page_count`, with each field appearing
once; a single field can also be written without brackets. Use `null`, `size`,
or an empty list to group all delivery notices together. Each group is split into
bundles of at most `bundle_size` notices. A missing selected school or board ID
produces a warning; when eligible for delivery, it is grouped under Unknown. Notices
needing review stay in review bundles. Grouping by page count does not add pages
or set a fixed notice length.

### Native compiler deadlines

Each native Typst operation has a wall-clock deadline. Defaults allow longer
notice layout than compiler discovery and small review sheets:

```yaml
typst:
  timeouts_seconds:
    version: 10
    compile: 120
    evidence: 120
    review: 60
```

Each value must be a number of seconds above zero and at most 86400 (one day).
Fractional seconds are accepted. Unknown operation names, strings, booleans,
null and nonfinite values are rejected. Omitted operations use the defaults
defined by `CompilerTimeouts` in `immuknow/compile_notices.py`. Resolved values
are saved in `run.json`; saved-run review uses those values as well.

A version-probe timeout stops setup and preserves the source/run record. A
notice compilation timeout fails that row, removes incomplete PDF output and
allows independent rows to continue. An evidence timeout retains the readable
original with failed checking, which prevents delivery. A review timeout fails
the delivery attempt and leaves the previous committed bundle set intact.
Inspect the recorded operation and template before increasing its limit.

### School validation

School validation requires `target_phu` and reads `reference_file` from the
selected configuration directory. When `reference_file` is omitted, null or
blank, the packaged `school_reference.json` is used. A named file that does not
exist stops the run; it is never replaced by the packaged file.

Exact, inexact and unmatched results are saved as run artifacts. Each row's
check in `run.json` records the reference file hash, PHU, matched name/ID and
mismatch reason. An unknown school or conflicting name/ID rejects the whole
cohort before any PDFs are generated. A matching name with no facility ID
warns; an exact name/ID match passes.

The lookup reads `school_name`, which may include ` - FACILITY ID`. It does not
replace the source name or the separate `school_id` and `board_id` fields.
Missing source IDs stay blank. See [delivery grouping](#group-delivery-bundles)
for how missing IDs are handled. When school validation is disabled, no lookup
result is claimed.
Relative reference paths are resolved from the selected configuration directory.
Absolute paths are also accepted. Each run uses a saved copy and records the
original path; later changes to the source reference do not affect that run.

## Password placeholders

PDF password templates support `client_id`, `first_name`, `last_name`, `first_initial`, `last_initial`, `name`,
`date_of_birth_iso`, `date_of_birth_iso_compact`, `school`, `board`,
`street_address`, `city`, `province`, `postal_code` and `language_code`.
Each initial is the first character after removing spaces around the name.
It keeps the original case and accents: `Élodie` gives `É`.
A missing name makes its initial unavailable for encryption.
Encryption is disabled in the reference configuration; its password template
uses the compact birth date. Initials only affect passwords when explicitly
included in the configured template, for example:

```yaml
encryption:
  enabled: true
  password:
    template: '{first_initial}{last_initial}-{date_of_birth_iso_compact}'
```

The two birth date forms are `YYYY-MM-DD` and `YYYYMMDD`. The ambiguous
`{date_of_birth}` placeholder is rejected.

For QR destinations, see the [template authoring guide](https://docs.phiz.ca/immuknow/latest/user_guide/phu_templates/#component-choices-and-findings).

## Explicit assignments

Every run takes one CSV and exactly one selector:

```bash
immuknow clients.csv --template ./templates/overdue_diseases_v1.en.typ --output ./runs
immuknow clients.csv --notice-assignments ./assignments.json --templates ./templates --output ./runs
```

The single file applies unchanged to every row. Manifest selection uses a
UTF-8 JSON array with string identifiers (leading zeros are preserved):

```json
[
  {"client_id": "0000000001", "template": "overdue_diseases_v1.en.typ"},
  {"client_id": "0000000002", "template": "overdue_agents_v1.fr.typ",
   "experiment_id": "wording-comparison", "experiment_arm": "B"}
]
```

A template is a basename inside the selected complete template tree.
`<version>.<language>.typ` supplies both identity values; supported languages
are `en` and `fr`. The compiler passes that trusted identity to Settings.
The optional experiment strings are report labels. There is no automatic
selection, translation, randomization or clinical assessment.

Surrounding whitespace is trimmed from manifest client IDs and template names,
as it is from source cells. Leading zeros remain intact. IDs that become equal
after trimming are ambiguous. Manifest rows accept only `client_id`, `template`,
`experiment_id` and `experiment_arm`; repeated or unknown fields are rejected.
The notice catalog accepts `schema_version` and `versions`, with `kind` and
optional `requires` per version. An omitted `requires` uses the kind's default;
an explicit null or unknown rule is refused.

Missing, ambiguous or unusable assignments and duplicate source client IDs
reject the complete input file before rendering. Extra manifest rows warn. An existing custom version
without a catalog check warns with `assignment.check_unavailable`. A known
applicability conflict or conflicting source version warns and preserves the
explicit selection. Malformed shared JSON or configuration stops setup.
A missing client ID warns and can still render in single-file mode. Blank
addresses and other incomplete facts remain in the cohort for review.

`notice_versions.yaml` has integer `schema_version: 1` and a version mapping:

```yaml
schema_version: 1
versions:
  overdue_diseases_v1:
    kind: overdue
    requires: has_overdue
  overdue_agents_v1:
    kind: overdue
    requires: has_overdue_agents
  affirmative_schedule_v1:
    kind: affirmative
    requires: no_overdue
  suspension_order_v1:
    kind: overdue
    requires: has_overdue
```

Rules check supplied facts: `has_overdue`, `has_overdue_agents`, `no_overdue`
or `any`. The catalog supplies no language or default notice. Suspension
wording uses the upstream assessment; authors configure its dates and service
information. Python does not assess exemptions or calculate school calendars.

### Validity and next-dose display

Python always reads validity and next-dose information from the input and
keeps it in the notice data. The Template and Settings decide whether notices show it.
Dose validity is shown by default when flags are available. Dose numbering is
shown only when requested.

- `show-validity` in `immunization-history(...)`: mark each dose in the
  history chart as valid (⬤) or invalid (○), and add a legend for marks shown.
  The default is `true`. A history with no flags uses ordinary ⬤ recorded-dose
  marks without a validity legend. When `false`, every recorded dose shows ⬤
  and validity is ignored.
- `omit-invalid` in `immunization-history(...)`: leave doses marked
  ` - Invalid` out of the history chart. This applies even when
  `show-validity` is `false`.
- `include-dose` on `immuknow.overdue-diseases(...)` in the Template: add the
  dose number, for example "Measles (2nd dose)" or "Rougeole (2e dose)".
  Set `include-dose: true` on the component call to show it. The default is
  `false`. Overdue agent lists never show dose numbers.

Validity comes from ` - Valid` or ` - Invalid` after each `imms_given` entry.
Dose numbers come from ` - N` after each `overdue_disease` entry. See the
[input schema](https://docs.phiz.ca/immuknow/latest/user_guide/input_schema/).
Rows that do not name `omit-invalid` use its default, `false`.

| Input | Setting | Notice shows |
|---|---|---|
| Has validity | `show-validity: false` | Plain ⬤ marks; looks the same as input without validity |
| Has validity | `show-validity: true` | ⬤ / ○ marks with matching legend |
| No validity | `show-validity: false` | Plain ⬤ marks |
| No validity | `show-validity: true` | Plain ⬤ recorded-dose marks; no validity legend |
| Some rows with validity | `show-validity: true` | Fully flagged and fully unflagged histories render with a cohort warning; partially flagged histories fail rendering |
| Has validity | `show-validity: false`, `omit-invalid: true` | Plain ⬤ marks; invalid doses are left out |
| Has validity | `show-validity: true`, `omit-invalid: true` | ⬤ marks; invalid doses are left out, and the legend has no ○ line |
| No validity | `omit-invalid: true` | No effect; doses without validity are never treated as invalid |
| Has dose numbers | `include-dose: false` | Disease names only |
| Has dose numbers | `include-dose: true` | Disease names with dose numbers |
| No dose numbers | `include-dose: true` | Disease names only; no warning |
| Dose suffix is not a positive whole number | either | Disease name only; `source.overdue_unusable` warning |

`show-validity` defaults to `true`. Fully unflagged histories remain supported
and use ordinary recorded-dose marks without a validity legend. Once a history
contains a Valid/Invalid flag, every dose in that history must have one,
including doses hidden by display options. Partially flagged histories fail
rendering unless validity display is explicitly disabled. Missing flags are
never shown as a third validity category. Empty histories need no validity legend.
Fully flagged and fully unflagged notices can render independently. They retain
a `content.history_validity` warning when validity coverage varies across the
cohort; a fully unflagged cohort does not warn about missing validity.
English and Canadian French legend defaults explain whether a dose counts toward
vaccination requirements. See [template authoring](https://docs.phiz.ca/immuknow/latest/user_guide/phu_templates/#component-choices-and-findings)
for `legend-labels` overrides.

## Reference and label updates

History agents must have exact entries in the project's `vaccine_reference.json`,
including agents hidden by Settings. An unknown agent rejects the input cohort;
correct the source name or supply a verified mapping rather than relying on the
"Other" display column. See [history input](https://docs.phiz.ca/immuknow/latest/user_guide/getting_started/#history-format)
for findings and recognized Panorama placeholders.

Keep normalization output names consistent with vaccine mappings and authored
history columns. Mappings retain diseases even when the current chart omits
them. Same-agent administrations on one date collapse with
`unknown > valid > invalid` precedence; a valid/invalid pair keeps the valid
dose. Validity coverage is classified over the whole cohort before
presentation and deduplication.

Edit both language/domain files in `templates/translations/` when adding
approved labels. Unknown labels remain visible. Missing selected-language
labels produce findings when the matching component is used. See
[template authoring](https://docs.phiz.ca/immuknow/latest/user_guide/phu_templates/)
for Settings, components and the structural JSON contract.

## Validation rules

The optional `validation` section controls enabled state and warning/failure
severity for designated layout and translation checks. See
[rule settings](https://docs.phiz.ca/immuknow/latest/user_guide/pdf_validation/#rule-settings) for the rule list,
row selectors and saved-run changes. Identity and required evidence stay mandatory.
