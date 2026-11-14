# Configuration and reference files

Your notice project contains a `config` folder with settings and reference files. Give its path to ImmuKnow with `--config`. [ImmuKnow Template](https://github.com/WDGPH/ImmuKnow-Template) provides a starting project to adapt to your data and notices. Review its settings and notice content before use.

The project supplies these files alongside its templates:

- `parameters.yaml` contains run settings.
- `disease_normalization.json` maps disease names from your source to standard names.
- `vaccine_reference.json` maps each vaccine agent (the vaccine name or code in your source) to one disease name or a list of disease names.
- A school reference lists schools and facility IDs if school validation is enabled.

Maintain these files for your source system. `immuknow resources --output DIR` exports shared Typst components and schemas, but does not create these project files, configuration defaults, vaccine mappings, or regional school lists. Keep the filenames shown above. JSON and YAML files cannot contain repeated fields, unknown settings, or values of the wrong type. YAML merge keys are unsupported; write each setting explicitly.

## Run settings

Edit `parameters.yaml` to set the following options:

| Setting | Purpose |
| --- | --- |
| `date_as_of`, `date_of_delivery` | Assessment and delivery dates in `YYYY-MM-DD` format. |
| `date_due`, `date_of_suspension` | Optional update deadline and suspension start, in `YYYY-MM-DD` format; omitted, null or blank means unset. |
| `allowed_duplicate_client_ids` | Optional list of explicitly accepted repeated client IDs, quoted as strings. |
| `bundling.bundle_size` | Maximum notices in each combined PDF. Set to zero to turn off grouping. |
| `bundling.group_by` | Optionally group by `school`, `board`, `language`, `page_count`, or `notice_variant`, using one value or a list. `size` or null groups by size only. |
| `bundling.sort_by` | `source` (default) preserves input order within each group. `last_name_dob` orders by last name, birth date and row key before splitting bundles. |
| `filenames.individual.template` | Filename stem for original and protected copies; omitted keeps row-key names. |
| `filenames.bundle.template` | Filename stem for normal bundle PDFs. |
| `filenames.review_bundle.template` | Optional review stem; defaults to the bundle template with `review_` prefixed. |
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

To separate selected notice versions and languages, use
`group_by: [notice_variant, language]`. `notice_variant` uses the version ID
from the selected template; group by `language` separately when needed.

When grouping by school or board, a missing ID with a usable name produces a
warning and groups by normalized name. School-name fallback also uses board
identity when available. A missing ID and name fails the grouping check and
keeps that notice in its own review group. Conflicting names for the same ID
fail affected notices and keep the different names apart. Different nonblank
IDs remain separate even when names match. Name comparison ignores case and
repeated whitespace and uses Unicode NFC; it preserves accents. These checks
apply only to dimensions selected for grouping. They are recalculated when
bundles are rebuilt; they do not change the original input or PDF.

Set `sort_by: last_name_dob` under `bundling` to order notices within each
route and group before splitting by bundle size. Last names use the same case,
space and Unicode normalization; accents remain distinct. Dates sort ascending,
with row key as the final tie-break. Missing names and missing or invalid dates
sort last for their respective field. Source order remains the default and the
saved source rows retain their original order. Rebuilding bundles uses the
sorting setting saved with the run.

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

The embedded compiler has no per-notice timeout. Apply time limits to the whole
command through your command runner; interrupted work remains incomplete.
Run folders are retained until you remove them under your organization's retention
policy. Warnings are eligible for delivery by default.

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

## Filename templates

Set filename stems in `parameters.yaml` using `{field}` placeholders, as with
password templates. Core appends `.pdf`; do not include extensions or
directory paths. For example:

```yaml
bundling:
  bundle_size: 100
  group_by: [school, notice_variant, language]
filenames:
  individual:
    template: '{last_name}_{first_name}_{client_id}_{notice_variant}'
  bundle:
    template: '{school}_{notice_variant}_{bundle_number}'
  # Optional: otherwise Core prefixes the bundle pattern with review_.
  review_bundle:
    template: 'review_{school}_{notice_variant}_{bundle_number}'
```

This can produce `example_school_overdue_agents_01.pdf`. The run-wide records CSV identifies its members and page ranges. Individual originals and protected copies share a stem in separate
`originals/` and `encrypted/` directories. Encryption still uses its own password
template. Filename settings are saved in the run; derived passwords are not.

| Scope | Supported fields |
| --- | --- |
| Individual | `client_id`, `first_name`, `last_name`, `first_initial`, `last_initial`, `name`, `date_of_birth_iso`, `date_of_birth_iso_compact`, `school`, `board`, `street_address`, `city`, `province`, `postal_code`, `language_code`, `row_key`, `school_id`, `board_id`, `notice_variant` |
| Bundle and review bundle | `school`, `school_id`, `board`, `board_id`, `language_code`, `notice_variant`, `bundle_number`, `route` |

Fields shared with password templates have the same source values. `school` is
the supplied school name, including any facility-ID suffix; `school_id` is the
separate source ID. `notice_variant` is the assigned version, such as
`overdue_agents`. `route` is `deliverable` or `review`. `bundle_number` starts at
`01` within each group and route, and grows past two digits when needed.

A bundle fact field must be present and identical across its actual members.
Choose grouping that makes the fields you use consistent. A pattern containing
only `{route}_{bundle_number}` works with size-only grouping. Naming does not
change groups, notice order, source identities or delivery decisions.

Names are lowercase and Unicode-normalized. Letters, digits, hyphens and
underscores remain; other character runs become underscores. Core trims edge
separators, protects reserved device names, limits stems to 160 UTF-8 bytes and
adds deterministic row/bundle suffixes for collisions, including patterns that
omit a chunk number. No artifact is overwritten because two expanded names
match. `{{` and `}}` escape braces; escaped literals still undergo filename
normalization. Expressions, format specifiers and arbitrary CSV fields are not
supported.

Malformed placeholders, unsupported fields, paths, control characters and file
extensions reject configuration before PDFs are created. A missing/mixed field
or a stem with no usable characters instead uses a deterministic fallback and
records `output.filename_fallback`; usable PDFs remain available. Read recorded
paths in the report rather than inferring names. Names and selected personal
fields are visible in the filesystem; choose the fields appropriate to your
workflow.

When filename settings are omitted, existing `row-*.pdf`, `bundle-*.pdf` and
`review-*.pdf` naming remains. Filename fields do not change grouping identity. If one bundle
contains several different school names, a `{school}` pattern uses a fallback
rather than naming the bundle after one arbitrary member.

To change bundle names in an existing run, see [rebundling](pdf_validation.md#rebuild-bundles).
Individual originals retain their recorded names.

## Password templates

To create password-protected copies, enable encryption and choose a template. For example, this combines the person's initials and birth date, such as `AB-20100131`:

```yaml
encryption:
  enabled: true
  password:
    template: '{first_initial}{last_initial}-{date_of_birth_iso_compact}'
```

You can use `client_id`, `first_name`, `last_name`, `first_initial`, `last_initial`, `name`, `date_of_birth_iso`, `date_of_birth_iso_compact`, `school`, `board`, `street_address`, `city`, `province`, `postal_code`, and `language_code` between braces as placeholders. Initials use the first Unicode character after surrounding spaces are removed from the name. ISO birth dates have the form `YYYY-MM-DD`; compact dates have the form `YYYYMMDD`. Each value used in the template must be present for that notice. Derived passwords remain in memory; the password template is redacted from saved configuration. Source facts and original PDFs remain sensitive.

## Notice selection

Choose one `<version_id>.<language>.typ` file for everyone in the client list, or provide a JSON selection file with one choice per person. For example, save this as `assignments.json`:

```json
[
  {"client_id": "0123456789", "template": "overdue_diseases.en.typ"},
  {"client_id": "1234567890", "template": "affirmative_schedule.fr.typ", "experiment_id": "example", "experiment_arm": "A"}
]
```

Use `--notice-assignments assignments.json --templates ./project/templates` with the run command. Each `template` value is a filename in the `--templates` folder, without a path. Surrounding spaces are removed from IDs and filenames; leading zeros are kept. Missing or ambiguous choices and unlisted duplicate nonblank client IDs in the CSV reject the input. Extra rows in the selection file produce warnings. The selected filename determines the notice version and language. The selected notice declares its own eligibility and coverage requirements; a failed requirement keeps a readable original for review. Only `en` and `fr` are supported.

To accept a known repeated client ID, add it explicitly to `parameters.yaml`:

```yaml
allowed_duplicate_client_ids:
  - '0123456789'
```

Entries must be unique, nonblank strings without surrounding whitespace. Quote
each ID to preserve leading zeros. The setting applies to every run using this
configuration. Each occurrence of a repeated ID is retained and receives a warning; all
rows sharing the ID use the same selected template and experiment assignment.
Review each row before sending. Unlisted duplicates still reject the input.
For row-specific validation rules on a repeated ID, use the input SHA-256 and
row key selector; a Panorama ID selector is ambiguous and rejected.

Each v2 notice places one requirements declaration beside its wording. The shared Typst helper checks eligibility, forecast coverage and agent display when the notice compiles. Preparation reports these checks as deferred rather than claiming they passed. See [notice requirements](../developer_guide/templates.md#notice-requirements). There is no separate notice catalog; an obsolete `notice_versions.yaml` has no effect.

## Disease and history references

The vaccine reference maps each forecasted agent to one or more diseases. Core standardizes disease names and records missing diseases, extra diseases and unmapped agents before display exclusions. Missing coverage fails an agent-based notice and warns on a disease-based notice; explicit neutral coverage is not applicable. Extra coverage or unmapped agents also warn when coverage applies. These findings belong to each compiled notice and do not stop later clients. An invalid dose number produces a warning and keeps the disease without the number. Original source text is retained.

History entries use exact agent names from `vaccine_reference.json`. Every entry is checked before any are excluded from display. A history table included in a notice reports an error for an unknown agent unless its `ignore-agents` option excludes it. If the notice has no history table, no mapping check is needed. Formulation markers affect display names only. See [CSV input](input_schema.md) and [template authoring](../developer_guide/templates.md).

## Fonts

The standalone executable includes Typst 0.15.1 and its shared components. It uses fonts installed on the workstation. Install the fonts specified by your project and inspect example English and French notices. A separate Typst executable and Python runtime are not required.

## Notice dates

Use the existing `date_as_of` and `date_of_delivery` names for assessment and
planned delivery. `date_due` and `date_of_suspension` are optional project dates.
Core validates each supplied date and compares the dates that are present, in
this order:

```text
date_as_of <= date_of_delivery < date_due < date_of_suspension
```

Assessment and delivery may share a day. Other supplied dates must be later;
if the due date is omitted, suspension must still be later than delivery.
Omit an optional date or set it to `null` or `''` when it does not apply. Invalid
calendar dates or inconsistent ordering stop preparation with the field names
in the error. Core does not infer a deadline, a suspension date or school days.
Templates decide where these dates appear. See
[ImmuKnow Template's documentation](https://github.com/WDGPH/ImmuKnow-Template/blob/main/README.md)
for starter-notice wording and date display.
