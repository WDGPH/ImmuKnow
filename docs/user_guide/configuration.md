# Configuration and reference files

Your notice project contains a `config` folder with settings and reference files. Give its path to ImmuKnow with `--config`. [ImmuKnow Template](https://github.com/WDGPH/ImmuKnow-Template) provides a starting project to adapt to your data and notices. Review its settings and notice content before use.

The project supplies these files alongside its templates:

- `parameters.yaml` contains run settings.
- `notice_versions.yaml` lists notice versions and when each is applicable.
- `disease_normalization.json` maps disease names from your source to standard names.
- `vaccine_reference.json` maps each vaccine agent (the vaccine name or code in your source) to one disease name or a list of disease names.
- A school reference lists schools and facility IDs if school validation is enabled.

Maintain these files for your source system. `immuknow resources --output DIR` exports shared Typst components and schemas, but does not create these project files, configuration defaults, vaccine mappings, or regional school lists. Keep the filenames shown above. JSON and YAML files cannot contain repeated fields, unknown settings, or values of the wrong type. YAML merge keys are unsupported; write each setting explicitly.

## Run settings

Edit `parameters.yaml` to set the following options:

| Setting | Purpose |
| --- | --- |
| `date_as_of`, `date_of_delivery` | Dates in `YYYY-MM-DD` format used in the prepared information. |
| `bundling.bundle_size` | Maximum notices in each combined PDF. Set to zero to turn off grouping. |
| `bundling.group_by` | Optionally group by `school`, `board`, `language`, or `page_count`, using one value or a list. `size` or null groups by size only. |
| `encryption.enabled` | Create password-protected copies for sending while keeping the original PDFs. |
| `encryption.password.template` | A nonempty password template, required when encryption is enabled. |
| `school_validation.enabled` | Compare school names and facility IDs in the CSV with your health unit's school list. |
| `school_validation.reference_file` | Path to the school list, absolute or relative to the config folder. If omitted, null, or blank, uses `school_reference.json` in that folder. |
| `school_validation.target_phu` | Exact health unit name in the school list; required when school validation is enabled. |
| `validation.rules` | Settings for adjustable checks across the run. |
| `validation.clients` | Optional settings for checks on one selected input row. |
| `validation.notice_length` | Optional required page count for notices to be sent. |

For example, these settings put at most 100 notices in each combined PDF, grouped by school, and set the dates used in the notices:

```yaml
bundling:
  bundle_size: 100
  group_by: school
date_as_of: '2025-08-31'
date_of_delivery: '2025-09-01'
```

To require notices to have exactly two pages when sending them, enable grouping and add:

```yaml
validation:
  notice_length:
    enabled: true
    count: 2
    unit: pages
```

ImmuKnow does not add blank pages to meet the count. See [PDF checks and review](pdf_validation.md) for the results of failed checks and warnings.

`validation.rules` and `validation.clients` can change only adjustable checks made when creating notices. Each change specifies `enabled` and/or `severity` (`warn` or `fail`), and a nonempty `reason`. To select one row for `validation.clients`, use either `{scheme: panorama, value: "0123456789"}` or `{input_sha256: "<source SHA-256>", row_key: "row-000001"}`. The latter uses the input file's SHA-256 fingerprint and the row key from the run report. Each selector must match exactly one row, and at most one selector may target that row. Row-specific rules take precedence over run-wide rules. The report retains the original observations separately from the results after applying the rules and their reasons.

The settings `typst.bin` and `typst.timeouts_seconds` are retired because the executable includes Typst. Apply any time limit to the whole command using your command runner. `pipeline.after_run.remove_artifacts: true` is unsupported; delete a run folder you own when you no longer need it. Warning acceptance settings are unsupported because notices with warnings are eligible for sending by default. Remove these retired settings when updating an older project.

## School validation

Supply a current school list in JSON. It has a `phus` section containing one section per public health unit. Each school name is paired with its facility ID. For example:

```json
{
  "phus": {
    "Example Health Unit": {
      "EXAMPLE ACADEMY": "EX-001"
    }
  }
}
```

Save this example as `school_reference.json` in the config folder, then add the following to `parameters.yaml`, using the exact health unit name from your file:

```yaml
school_validation:
  enabled: true
  target_phu: Example Health Unit
```

You can select another file with `school_validation.reference_file`. If the file is missing or does not contain the selected health unit, preparation fails. Each saved run keeps a copy of the selected list and its source path.

In the CSV, `school_name` can end in ` - FACILITY ID`; ImmuKnow uses the last such separator. It compares names without regard to case or repeated spaces. A matching name and ID passes; a matching name without an ID produces a warning. A conflicting or unknown name or ID fails that row's check, and a readable notice goes into a separate review PDF. School matching does not replace the original name or the separate `school_id` and `board_id` fields. The findings include match details and a fingerprint of the reference file.

The former `school_validation.column_prefix` option is retired; school findings use fixed measurement names. Remove it from older project configuration.

## Password templates

To create password-protected copies, enable encryption and choose a template. For example, this combines the person's initials and birth date, such as `AB-20100131`:

```yaml
encryption:
  enabled: true
  password:
    template: '{first_initial}{last_initial}-{date_of_birth_iso_compact}'
```

You can use `client_id`, `first_name`, `last_name`, `first_initial`, `last_initial`, `name`, `date_of_birth_iso`, `date_of_birth_iso_compact`, `school`, `board`, `street_address`, `city`, `province`, `postal_code`, and `language_code` between braces as placeholders. Initials use the first Unicode character after surrounding spaces are removed from the name. ISO birth dates have the form `YYYY-MM-DD`; compact dates have the form `YYYYMMDD`. Each value used in the template must be present for that notice. Passwords remain in memory and are removed from saved configuration.

## Notice selection

Choose one `<version_id>.<language>.typ` file for everyone in the client list, or provide a JSON selection file with one choice per person. For example, save this as `assignments.json`:

```json
[
  {"client_id": "0123456789", "template": "overdue_diseases_v1.en.typ"},
  {"client_id": "1234567890", "template": "affirmative_schedule_v1.fr.typ", "experiment_id": "example", "experiment_arm": "A"}
]
```

Use `--notice-assignments assignments.json --templates ./project/templates` with the run command. Each `template` value is a filename in the `--templates` folder, without a path. Surrounding spaces are removed from IDs and filenames; leading zeros are kept. Missing or ambiguous choices and duplicate nonblank client IDs in the CSV reject the input. Extra rows in the selection file produce warnings. A conflict with the source version, an unavailable catalog check, or a choice that conflicts with the catalog produces a warning and keeps the selected template. Only `en` and `fr` are supported.

The notice catalog, `notice_versions.yaml`, has `schema_version: 1` and `versions` entries with `kind` (`overdue`, `affirmative`, or `informational`) and optional `requires` (`has_overdue`, `has_overdue_agents`, `no_overdue`, or `any`). It checks whether the chosen notice applies; it does not choose a notice or assess immunization status.

## Disease and history references

The vaccine reference maps each forecasted agent to one or more diseases. After the disease names are standardized, those agents must cover every overdue disease in the input. Missing coverage rejects the input; extra coverage or unmapped agents produce warnings. An invalid dose number produces a warning and keeps the disease without the number. Original source text is retained.

History entries use exact agent names from `vaccine_reference.json`. Every entry is checked before any are excluded from display. A history table included in a notice reports an error for an unknown agent unless its `ignore-agents` option excludes it. If the notice has no history table, no mapping check is needed. Formulation markers affect display names only. See [CSV input](input_schema.md) and [template authoring](../developer_guide/templates.md).

## Fonts

The standalone executable includes Typst 0.15.1 and its shared components. It uses fonts installed on the workstation. Install the fonts specified by your project and inspect example English and French notices. A separate Typst executable and Python runtime are not required.
