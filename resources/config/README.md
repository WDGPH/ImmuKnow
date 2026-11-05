# Configuration and reference files

Pass the directory containing these files with `--config`. Export the supplied starting files with `immuknow resources --output DIR`; the resulting `DIR/config/` is a starting point for your project. Keep configuration and authored template projects together under your control, and review all notice content before use.

`parameters.yaml` sets run options. `notice_versions.yaml` describes catalog applicability, `disease_normalization.json` maps source disease names to canonical names, and `vaccine_reference.json` maps agents to one disease string or a list of disease strings. School validation uses `school_reference.json` when configured. JSON and YAML reject repeated fields, unknown settings and wrong types. YAML merge keys are unsupported; write settings explicitly.

## Parameters

| Setting | Purpose |
| --- | --- |
| `date_as_of`, `date_of_delivery` | Dates in `YYYY-MM-DD` format used in the prepared facts. |
| `bundling.bundle_size` | Maximum number of notices per bundle; zero disables bundling. |
| `bundling.group_by` | Optional grouping fields: `school`, `board`, `language`, and `page_count`, as one string or a list. `size` or null uses size only. |
| `encryption.enabled` | Request encrypted delivery copies while retaining originals. |
| `encryption.password.template` | Required nonempty password template when encryption is enabled. |
| `school_validation.enabled` | Compare source school names and facility IDs with the selected PHU reference. |
| `school_validation.reference_file` | Reference path, absolute or relative to the selected config directory. An omitted, null or blank value selects the packaged reference. |
| `school_validation.target_phu` | Exact PHU key in the reference; required when school validation is enabled. |
| `school_validation.column_prefix` | Prefix for school matching fields. |
| `validation.rules` | Run-wide settings for adjustable validation rules. |
| `validation.clients` | Optional rules scoped to an explicitly selected source row. |
| `validation.notice_length` | Optional fixed delivery notice length, in pages. |

Settings `typst.bin` and `typst.timeouts_seconds` are retired: the executable embeds the Typst engine. Apply any deadline to the whole command using your process supervisor. `pipeline.after_run.remove_artifacts: true` is unsupported; delete an owned run directory when it is no longer needed. Warning acceptance settings are unsupported because warnings are eligible for delivery by default. Remove retired settings when migrating a project.

For fixed-length delivery, configure an explicit positive count and enable bundling:

```yaml
validation:
  notice_length:
    enabled: true
    count: 2
    unit: pages
```

Run-wide `validation.rules` and scoped `validation.clients` can change only adjustable render rules. Each change specifies `enabled` and/or `severity` (`warn` or `fail`), and a nonempty `reason`. A client selector is either `{scheme: panorama, value: "0123456789"}` or `{input_sha256: "<source SHA-256>", row_key: "row-000001"}`. Each selector must match exactly one row, and at most one selector may target that row. Scoped rules override run-wide settings. Observed checks stay intact; effective checks and policy reasons are recorded separately.

No blank pages are added. See [PDF review](https://docs.phiz.ca/immuknow/latest/user_guide/pdf_validation/) for checks and delivery.

## School validation

The source `school_name` may end in ` - FACILITY ID`; the rightmost separator is used. Names are compared after uppercasing and collapsing whitespace. A matching name and ID passes; a name match without an ID warns. A conflicting or unknown name or ID fails that row and sends its readable notice to a review bundle. School matching does not replace source names or the separate `school_id` and `board_id` fields. The reference hash and match details are retained in findings.

## Password templates

Allowed placeholders are `client_id`, `first_name`, `last_name`, `first_initial`, `last_initial`, `name`, `date_of_birth_iso`, `date_of_birth_iso_compact`, `school`, `board`, `street_address`, `city`, `province`, `postal_code`, and `language_code`. Initials use the first Unicode character of the trimmed name. ISO birth dates have form `YYYY-MM-DD`; compact dates have form `YYYYMMDD`. A referenced value must be present for that notice. Passwords remain in memory and are removed from saved configuration.

```yaml
encryption:
  enabled: true
  password:
    template: '{first_initial}{last_initial}-{date_of_birth_iso_compact}'
```

## Notice selection

Select one `<version_id>.<language>.typ` file for the cohort, or provide a JSON array with one explicit selection per source client:

```json
[
  {"client_id": "0123456789", "template": "overdue_diseases_v1.en.typ"},
  {"client_id": "1234567890", "template": "affirmative_schedule_v1.fr.typ", "experiment_id": "example", "experiment_arm": "A"}
]
```

Manifest template values are basenames in the `--templates` directory. IDs and template names are trimmed, while leading zeros are preserved. Missing or ambiguous assignments and duplicate nonblank source IDs reject the cohort. Additional manifest rows warn. Source version conflicts, unavailable catalog checks and applicability conflicts warn and preserve the selected template. Only `en` and `fr` are supported.

The catalog has `schema_version: 1` and `versions` entries with `kind` (`overdue`, `affirmative`, or `informational`) and optional `requires` (`has_overdue`, `has_overdue_agents`, `no_overdue`, or `any`). The catalog does not choose a template or assess immunization status.

## Disease and history references

Each forecasted agent maps to one or more diseases. After disease normalization, forecasted agents must cover every supplied overdue disease; missing coverage rejects the cohort, while extra coverage or unmapped agents warns. Invalid dose suffixes warn and retain the disease without a dose number. Original source strings are retained.

History entries use exact agent names from `vaccine_reference.json`. Every source fragment is parsed before any display exclusions. A placed history table fails for an unknown agent unless its own `ignore-agents` option excludes it; no mapping check is needed for an omitted table. Formulation markers affect display names only. See [CSV input](https://docs.phiz.ca/immuknow/latest/user_guide/input_schema/) and [template authoring](https://docs.phiz.ca/immuknow/latest/user_guide/phu_templates/).
