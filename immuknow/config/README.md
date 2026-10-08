# Configuration and notice contract

The package ships `immuknow/config/` as its default configuration directory.
Pass `--config PATH` to select a PHU-owned directory. It must contain the
required reference files; installed resources remain read-only. The command and
callable workflow are described in [getting started](https://WDGPH.github.io/ImmuKnow/user_guide/getting_started/).

## Files and responsibilities

| File | Purpose |
|---|---|
| `parameters.yaml` | Run options, chart order, dates, QR, validation, encryption, and delivery |
| `input_schema.json` | Required source columns and types |
| `vaccine_reference.json` | Vaccine code to canonical disease identifiers |
| `disease_normalization.json` | Source disease variants to canonical identifiers |
| `phix_mapping.json` | PHU school and facility reference |
| `translations/{en,fr}_diseases_{chart,overdue}.json` | Approved display labels for Typst |
| `notice_versions.yaml` | Versions, eligibility, and defaults for manifest mode |

Python uses the reference mappings to normalize records and decide eligibility.
Typst loads the selected display dictionaries once from the staged render
workspace. Chart membership and order use canonical disease identifiers, never
translated labels; two identifiers with the same label remain distinct.
Uncatalogued source labels remain visible unchanged. If an approved label exists
in the other language but is absent from the selected language, rendering fails
instead of switching languages. Update both language/domain dictionaries when
adding a canonical disease.

## Run options

Set options in `parameters.yaml`. Common choices:

| Key | Meaning |
|---|---|
| `date_notice_delivery` | ISO reference date for age and delivery decisions |
| `date_data_cutoff` | ISO extract date shown in notices; may be blank when absent |
| `chart_diseases_header` | Canonical chart identifiers in display order; unlisted diseases group under `Other` |
| `preprocess.include_dose` | Show numeric overdue doses when available; facts retain doses either way |
| `preprocess.show_validity_markers` | Mark valid and invalid received doses in the history |
| `ignore_agents` | Agent codes excluded from assessment processing |
| `qr.enabled`, `qr.payload_template` | QR image and encoded link |
| `encryption.enabled`, `encryption.password.template` | Individual PDF encryption and password |
| `bundling.bundle_size`, `bundling.group_by` | Bundle size and grouping: none, school, or board |
| `pdf_validation.rules.*` | `disabled`, `warn`, or `error` per rule |
| `pipeline.before_run.clear_output_directory` | Clear previous output or prompt before replacement |
| `pipeline.after_run.remove_artifacts` | Remove retained render inputs after successful delivery |
| `pipeline.after_run.remove_unencrypted_pdfs` | Remove plain PDFs when encrypted or bundled copies are final |

`pdf_validation.rules` supports `client_id_presence`,
`exactly_two_pages`, `signature_overflow`, and
`envelope_window_1_125`. The first compares the extracted client ID to the
expected render job; the others use page count or native Typst markers.
An error-level finding stops the run. The validation report is written under
`metadata/`. [PDF validation](https://WDGPH.github.io/ImmuKnow/user_guide/pdf_validation/) explains
the measurements.

For school matching, set `phix_validation.enabled: true`,
`target_phu` to the exact key in `phix_mapping.json`, and
`mapping_file` to that selected-directory-relative or absolute path.
`unmatched_behavior` can be `warn`, `error`, or `skip`; `skip`
excludes unmatched records. Per-run match CSVs distinguish exact, inexact,
and no match results. Refresh the PHIX reference when its source changes.

## QR and password placeholders

QR payloads and passwords are outside document presentation. Their supported
fields are `client_id`, `first_name`, `last_name`, `name`,
`date_of_birth_iso`, `date_of_birth_iso_compact`, `school`,
`board`, `street_address`, `city`, `province`, `postal_code`,
and `language_code`. Dates are `YYYY-MM-DD` and `YYYYMMDD`,
respectively. The default password remains the compact birth date.

```yaml
qr:
  enabled: true
  payload_template: "https://example.ca/update?id={client_id}&dob={date_of_birth_iso}&lang={language_code}"
encryption:
  enabled: true
  password:
    template: "{date_of_birth_iso_compact}"
```

The former `{date_of_birth}` placeholder is ambiguous because it meant a
localized display value. Configuration validation rejects it early and names
the two explicit ISO alternatives. Review and edit existing QR or password
templates yourself; the pipeline does not silently reinterpret them.

## Versions and assignments

Fixed mode takes `en` or `fr` as a positional argument and selects
`legacy_overdue_v1`. Manifest mode uses `--notice-assignments PATH`
and a mapping-shaped `notice_versions.yaml` with integer
`schema_version: 1`:

```yaml
schema_version: 1
default_version: overdue_standard_v1
default_language: en
versions:
  overdue_standard_v1:
    kind: overdue
  affirmative_schedule_v1:
    kind: affirmative
```

Kinds `overdue`, `affirmative`, and `informational` imply
`has_overdue`, `no_overdue`, and `any` eligibility. A version can set
`requires` explicitly to one of those values. Eligibility always follows
canonical overdue diseases, even when a template displays vaccine agents.

The assignment manifest is a JSON array:

```json
[
  {"client_id": "1009876545", "version_id": "overdue_standard_v1", "language": "fr"},
  {"client_id": "2001234567", "version_id": "affirmative_schedule_v1", "language": "en"}
]
```

`client_id` and `version_id` are required. Omitted `language` uses the
catalog default. Optional `experiment_id` and `experiment_arm` are retained
as provenance. An explicit source `version_id` must agree with the manifest.
Unknown versions, conflicting assignments, unsupported languages, invalid
catalogs, and eligibility failures stop before rendering, with client-linked
findings in the run output.

`notice_versioning.allow_unassigned: false` requires one manifest row per
client. If true, missing rows use the source `version_id` when present or
the catalog default, with the default language. Set
`notice_versioning.extra_manifest_rows` to `error` or `warn`
for rows without a matching source client. A positional language in manifest
mode does not override resolved per-client languages.

The maintained files are `<version_id>.<language>.typ`. The package includes
legacy overdue (English/French), standard overdue (English/French), and an
English affirmative entry point. A missing version/language pair fails; no
other language or PHU directory is substituted. See
[template authoring](https://WDGPH.github.io/ImmuKnow/user_guide/phu_templates/) for the JSON contract.

## Updating reference data

Keep vaccine mappings and normalization keyed by canonical disease names.
Translation files map each canonical identifier to one approved display label;
chart and overdue contexts may use different wording. Update reference data
and the relevant real-render tests together. A new language also needs an
authored and reviewed entry point; adding dictionaries alone does not create
a notice.
