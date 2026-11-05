# CSV input fields

This reference describes the supplied input schema. Required indicates that the column must be present; incomplete row values may produce findings. See [getting started](getting_started.md) for cohort rejection rules.

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
| `overdue_disease` | No | Semicolon-separated overdue diseases. Each disease may be followed by ' - N', where N is the next dose number as a positive whole number, for example 'Measles - 2; Polio;'. A dose suffix that is not a positive whole number produces a warning, and the disease is shown without a number. Whether dose numbers appear on notices is set by include-dose in Settings. |
| `overdue_agent` | No | Semicolon-separated list of overdue agents for client |
| `imms_given` | Yes | Semicolon-separated entries in the exact form 'YYYY-MM-DD - Agent', optionally followed by ' - Valid' or ' - Invalid', for example '2020-05-01 - MMR - Valid;'. Agent names are matched exactly against the selected vaccine_reference.json. A placed history table reports an error for an unknown agent unless its ignore-agents option explicitly excludes it. Month and day always have two digits. Dates must exist. Every entry ends with ';', including the last. Spaces, tabs and line breaks may surround entries; field separators are exactly space-hyphen-space. Blank history and the placeholders '-;' and '-  -;' (when validity is exported) mean no history. A missing final ';', a leading ';', ';;' and other empty entries, extra fields and wrongly cased status tokens reject the whole input file. |
| `board_name` | No | School board name |
| `board_id` | No | School board identifier |
| `school_id` | No | School identifier |
| `version_id` | No | Version identifier |
| `intended_reader` | No | Intended reader: student or guardian. Leave blank to use the age default (student at 16 or older, guardian under 16). Unknown age without a reader uses neutral wording. Invalid values reject the whole input file. Supply the intended mailing destination in the address columns. |
