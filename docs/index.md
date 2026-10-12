# ImmuKnow

ImmuKnow validates Panorama/PEAR vaccination records and creates personalized
immunization notices and history charts. Python owns the public-health rules,
client assignment, and complete output checks. Maintained Typst templates own
English and French document presentation.

The included wording, branding, and contact details are samples. Public Health
Units should review their selected templates and PDFs before use.

Start with [input preparation and the complete workflow](user_guide/getting_started.md).
Use the [configuration contract](user_guide/configuration.md) for assignments,
Typst display/QR settings, encryption, and validation. The
[template authoring guide](user_guide/phu_templates.md) defines the per-notice
JSON and native identity assertions. Contributors can follow the
[testing guide](developer_guide/testing.md).

The native package includes a portable Typst project, its licensed QR encoder,
and all nine supported font families. A run keeps original PDFs, frozen resources,
and one authoritative `run.json` with a readable `report.html`. Warnings retain
reviewable PDFs, and independent clients continue when another notice fails.
