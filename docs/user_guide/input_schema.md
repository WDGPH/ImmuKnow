# CSV input fields

Use these column names in your CSV. A required column must be present, even when some rows have missing values. Missing information may produce warnings or failed checks. A vaccine “agent” is the name or code used for a vaccine in your source system. See [getting started](getting_started.md) for cases that reject the whole input file.

Nonblank client IDs must be unique unless explicitly allowed in [configuration](configuration.md#notice-selection). Allowed repeated IDs retain all rows and produce a warning for each occurrence.

Rename the former `imms_given` column to `immunizations_given` before running.
Files containing `imms_given` are rejected, including files that also contain
the new column.

| Field | Required column | Description |
| --- | --- | --- |
| `school_name` | Yes | School name, optionally followed by a facility ID in the format 'SCHOOL NAME - FACILITY ID' |
| `client_id` | Yes | 10-digit Panorama client identifier |
| `oiid` | No | Optional Ontario Immunization ID; kept as text, including leading zeros. Some clients may not have an OIID. |
| `first_name` | Yes | Client first name |
| `last_name` | Yes | Client last name |
| `date_of_birth` | Yes | Client date of birth |
| `street_address_line_1` | No | Client street address (line 1) |
| `street_address_line_2` | No | Client street address (line 2) |
| `city` | Yes | City of client address |
| `province` | No | Province / territory of client address |
| `postal_code` | No | Postal code of client address |
| `overdue_disease` | No | Semicolon-separated overdue diseases. Each disease may be followed by ' - N', where N is the next dose number as a positive whole number, for example 'Measles - 2; Polio;'. A dose suffix that is not a positive whole number produces a warning, and the disease is shown without a number. The notice controls dose display with the overdue-diseases helper's include-dose option. |
| `overdue_agent` | No | Semicolon-separated list of overdue agents for the client |
| `immunizations_given` | Yes | Recorded vaccinations. Use the date, vaccine agent and optional validity result for each entry; see the example below. |
| `board_name` | No | School board name |
| `board_id` | No | School board identifier |
| `school_id` | No | School identifier |
| `version_id` | No | Version identifier |
| `intended_reader` | No | Intended reader: student or guardian. Leave blank to use the age default (student at 16 or older, guardian under 16). Unknown age without a reader uses neutral wording. Invalid values fail that source row without creating a PDF; other valid rows continue. Supply the intended mailing destination in the address columns. |

## Vaccination history example

In `immunizations_given`, separate entries with semicolons and include the final semicolon:

```text
2020-05-01 - MMR - Valid;2021-06-02 - Tdap;
```

Each entry has the form `YYYY-MM-DD - Agent`, optionally followed by ` - Valid`
or ` - Invalid`. Keep the spaces around each hyphen. Months and days need two
digits, and dates must exist. The status words are case-sensitive. Spaces,
tabs and line breaks may surround entries, but extra fields or empty entries
(such as `;;`) fail that source row. The report retains its original history without inventing facts or a PDF; other valid rows continue.

Use agent names exactly as they appear in your project's `vaccine_reference.json`.
When a notice shows a history table, an unknown agent fails its check unless the
template explicitly excludes that agent with `ignore-agents`. An omitted history
table needs no mapping check. A blank field, `-;`, or `-  -;` means no history.
