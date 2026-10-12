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

Authored display choices belong in `templates/settings.typ`. This includes
history columns, hidden agents, validity markers, overdue dose wording, QR
options, page geometry, theme, assets and contact details. Approved display
labels live in `templates/translations/`. Python preserves all normalized
administrations and mappings independently of those choices. Retired Python
settings (`qr`, `preprocess`, `ignore_agents`, `chart_diseases_header` and
`notice_versioning`) are rejected with a direction to Settings.

## Run options

| Key | Meaning |
|---|---|
| `date_of_delivery` | ISO date used to calculate age; absent/unusable birth dates leave age unknown |
| `date_as_of` | ISO as-of date displayed in the letter; does not filter administrations |
| `typst.bin` | Native compiler executable |
| `encryption.enabled`, `encryption.password.template` | Optional individual PDF encryption |
| `bundling.bundle_size`, `bundling.group_by` | Bundle size and grouping: size/null, school or board |
| `school_validation.enabled` | Compare source school names with the selected reference |

The [PDF validation guide](https://WDGPH.github.io/ImmuKnow/user_guide/pdf_validation/)
describes output measurements. Run findings and output accounting are recorded
in the authoritative `run.json`.

School validation uses `target_phu` and `reference_file` in the selected
configuration directory. Exact, inexact and unmatched results are saved as
run artifacts. Unmatched schools warn and retain the source row; validation
never silently removes clients. Source school and board IDs stay blank when
absent. Delivery groups missing grouping information under Unknown.

## Password placeholders

PDF password templates support `client_id`, `first_name`, `last_name`, `name`,
`date_of_birth_iso`, `date_of_birth_iso_compact`, `school`, `board`,
`street_address`, `city`, `province`, `postal_code` and `language_code`.
The two birth date forms are `YYYY-MM-DD` and `YYYYMMDD`. The ambiguous
`{date_of_birth}` placeholder is rejected.

```yaml
encryption:
  enabled: true
  password:
    template: '{date_of_birth_iso_compact}'
```

QR destinations are authored in Typst Settings using normalized notice fields.
The helper resolves one destination for the encoded QR and its clickable link,
then records that URL in the native findings.

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

Missing, ambiguous or unusable assignments and duplicate source client IDs
fail their affected rows. Extra manifest rows warn. An existing custom version
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

## Reference and label updates

Keep normalization output names consistent with vaccine mappings and authored
history columns. Mappings retain diseases even when the current chart omits
them. Same-agent administrations on one date collapse with
`unknown > valid > invalid` precedence; a valid/invalid pair keeps the valid
dose. Validity coverage is classified over the whole cohort before
presentation and deduplication.

Edit both language/domain files in `templates/translations/` when adding
approved labels. Unknown labels remain visible. Missing selected-language
labels produce findings when the matching component is used. See
[template authoring](https://WDGPH.github.io/ImmuKnow/user_guide/phu_templates/)
for Settings, components and the structural JSON contract.
