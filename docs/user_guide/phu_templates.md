# Authoring native Typst notices

A notice is an authored `.typ` entry point that reads one JSON payload.
Python supplies validated canonical facts and the resolved assignment. Typst
owns the document's prose, layout, dates, disease labels, dose wording, and
visible chart headings. The included branding and contacts are samples that a
PHU must review.

## Select a complete template tree

The package owns `immuknow/templates/`. Copy its entry points, `conf.typ`,
`presentation.typ`, and assets to a directory you control, then use
`--templates PATH`. From a checkout:

```bash
cp -r immuknow/templates /path/to/my-phu
uv run viper students.xlsx en --templates /path/to/my-phu
```

For an installed wheel:

```python
from importlib.resources import files
from pathlib import Path
from shutil import copytree

copytree(Path(str(files("immuknow").joinpath("templates"))), Path("/path/to/my-phu"))
```

The shorter `--template my_phu` selects `phu_templates/my_phu/` beneath the
caller's working directory. The selected tree is isolated; a missing entry,
helper, or asset does not fall back to built-ins. Writes stay in the run output,
not the installed package. Avoid placing the output directory inside selected
templates, or vice versa; overlap is rejected before copying or cleanup.

Maintained flat entry points are `legacy_overdue_v1.en.typ`,
`legacy_overdue_v1.fr.typ`, `overdue_standard_v1.en.typ`,
`overdue_standard_v1.fr.typ`, and `affirmative_schedule_v1.en.typ`.
The legacy overdue notice displays diseases; the standard overdue notice
displays vaccine agents. Eligibility for either is disease-based. No French
affirmative notice ships; add one only after its wording and layout are reviewed.

## Assert the notice identity

Each entry point names its own literal `version_id` and language, checks
the JSON, and sets the document text language and Canadian region:

```typst
#let notice = json(sys.inputs.at("data"))
#assert(notice.version_id == "overdue_standard_v1", message: "Wrong notice version")
#assert(notice.language == "en", message: "Wrong notice language")
#set text(lang: "en", region: "CA")
#import "/templates/conf.typ"
```

Keep assertions independent of the input values. An agent-based overdue entry
also asserts `notice.overdue_agents.len() > 0`. Disease-based and affirmative
entries do not require agents. Use ordinary Typst field access; input strings
must remain literal data, never executable source.

## Per-notice JSON

The renderer gives each entry point one small, derived JSON file:

| Field | Meaning |
|---|---|
| `version_id`, `language`, `client_id` | Resolved identity and client identifier |
| `client_data` | `name`, `address`, `city`, `postal_code`, `school`, `over_16`, and `date_of_birth_iso`; optional `qr_img` and `qr_url` |
| `date_data_cutoff_iso` | ISO extract date or blank when absent |
| `overdue_diseases` | Canonical `{disease, dose}` entries; invalid dose also has `dose_raw` |
| `overdue_agents` | Vaccine agents available to agent-based notices |
| `include_dose` | Whether Typst shows available numeric doses |
| `received` | History rows with `date_given`, `date_rowspan`, `vaccines`, and canonical `columns` validity statuses |
| `chart_diseases` | Canonical chart identifiers in configured order |
| `show_validity_markers` | Whether the history distinguishes validity |
| `logo_path`, `signature_path` | Assets beneath the bounded Typst root |

An absent dose has `dose: null`; an invalid source dose also retains
`dose_raw` for diagnostics. Python validates dates and passes ISO strings.
`presentation.typ` formats long dates, approved disease labels, dose suffixes,
and shared headings for English and French. A blank optional cutoff stays
blank; a required invalid date fails. The history retains its compact date
format. Translation dictionaries are staged once under `/translations/` and
looked up by canonical key. Uncatalogued source labels stay visible unchanged; a label present only in the
other language is an error. Chart membership is
never inferred from translated labels.

The selected templates can rearrange content, but keep their own version and
language checks. The [configuration contract](configuration.md) explains
assignments, translation data, and QR/password fields.

## Reproduce and review a notice

A run stages the selected tree at `output/artifacts/render/templates/`, the
language dictionaries at `render/translations/`, and one JSON file per client
at `render/data/`. `artifacts/render_jobs.json` records each exact template,
data file, expected PDF, and bounded workspace. Set
`pipeline.after_run.remove_artifacts: false` to retain these inputs.

With Typst 0.15.1, use the actual paths from that job:

```bash
typst compile \
  --root "/path/to/output/artifacts/render" \
  --input data=/data/en_notice_00001_123.json \
  "/path/to/output/artifacts/render/templates/legacy_overdue_v1.en.typ" \
  "/path/to/review.pdf"
```

The slash in a Typst import or data reference is relative to `--root`; the
root is the run workspace, never the filesystem root. A manual compile aids
review but does not certify whole-cohort validation or delivery.

Review English and French prose, client details, history grouping, validity
symbols, QR links, branding, page count, signature position, and envelope
window. Include long records and addresses. The
[testing guide](../developer_guide/testing.md) covers repeatable native checks.
