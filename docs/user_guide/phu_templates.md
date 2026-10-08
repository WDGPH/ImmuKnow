# Authoring native Typst notices

A notice consists of an authored `.typ` entry point and one JSON payload.
Python validates the source records, resolves the assignment, and prepares
display values. Typst owns the prose, layout, images, and presentation conditions.

## Choose a template directory

The wheel includes the built-in templates, shared helper, and branding assets.
The built-ins contain sample branding and contact details; customize them before
using them for a PHU.

To start from a checkout:

```bash
cp -r templates /path/to/my-phu
viper students.xlsx en --templates /path/to/my-phu --output /path/to/notices
```

For an installed package, copy its resources to a directory you own:

```python
from importlib.resources import files
from pathlib import Path
from shutil import copytree

copytree(Path(str(files("templates"))), Path("/path/to/my-phu"))
```

Use `--templates PATH` for an external directory. The shorter
`--template my_phu` selects `phu_templates/my_phu/` beneath the caller's
working directory. Choose one option. Neither requires writing into site-packages.

A selected PHU directory is isolated: its missing templates or assets are never
filled from the built-ins. Private files beneath `phu_templates/` remain ignored
by Git. Maintain them in your own controlled location.

## Maintained entry points

```text
templates/
  legacy_overdue_v1.en.typ
  legacy_overdue_v1.fr.typ
  overdue_standard_v1.en.typ
  overdue_standard_v1.fr.typ
  affirmative_schedule_v1.en.typ
  conf.typ
  assets/
    logo.png
    signature.png
```

The `legacy_overdue_v1` entry points retain the legacy notice wording and overdue **disease**
list. They declare the internal identity `legacy_overdue_v1` and work in fixed mode
without a catalog or manifest. The versioned overdue templates display **vaccine
agents**. These are distinct notices; renaming an entry point does not
make its wording equivalent.

There is no French affirmative template. A request for it fails with its expected
path. Add a translation only when an author has supplied and reviewed it.

Entry points use `<version_id>.<language>.typ`. The filename names the notice
and its revision as well as its language; no version subdirectory is needed.
Shared helpers and assets may still use subdirectories.

## Load data and check identity

Every entry point declares literal version and language values and checks both
before rendering. For example:

```typst
#let notice = json(sys.inputs.at("data"))
#let template-version = "overdue_standard_v1"
#let template-language = "en"

#assert(
  notice.version_id == template-version,
  message: "Notice version does not match this template",
)
#assert(
  notice.language == template-language,
  message: "Notice language does not match this template",
)

#import "/templates/conf.typ"
```

Keep these checks unconditional. The expected identity belongs to the template;
it must not be copied from the JSON input. Direct compilation of mismatched data
must fail even when Python is bypassed.

Use ordinary Typst field access and interpolation, such as
`#notice.client_data.name`. Strings remain text. Never use `eval` on input values
or introduce a Python/Jinja renderer.

## JSON contract

The per-notice payload is derived from the canonical preprocessed client record.
It is a render input, not another editable assignment source.

| Field | Meaning |
|---|---|
| `version_id`, `language` | Resolved identity, checked by the entry point |
| `client_row` | One-element array containing the client ID |
| `client_data` | Name, address, city, postal code, school, `over_16`, display birth date and cutoff date |
| `client_data.date_of_birth_iso` | Canonical birth date, retained separately from display text |
| `date_data_cutoff_iso` | Canonical cutoff date |
| `vaccines_due_array`, `vaccines_due_str` | Localized disease list and its joined text |
| `vaccines_due_agents_array`, `vaccines_due_agents_str` | Source agent list and its joined text; may be empty |
| `received` | History rows with `date_given`, `date_rowspan`, `vaccines`, and localized `columns` |
| `num_rows` | Number of history rows |
| `chart_diseases_translated` | Ordered chart headings |
| `show_validity_markers` | Whether to distinguish valid and invalid doses |
| `logo_path`, `signature_path` | Paths beneath the bounded Typst file root |
| `client_data.qr_img`, `client_data.qr_url` | Optional QR image reference and link |

All fields use ordinary JSON strings, arrays, dictionaries, numbers, booleans, or
nulls. Arrays and dictionaries are never pre-serialized as Typst source.
Birth dates, cutoff dates, disease labels, headings, and dose wording are prepared
after the notice language is resolved. History dates remain in their established
ISO display form.

Eligibility always follows the overdue **disease** list. A template independently
chooses its displayed list. An agent-based overdue template must enforce:

```typst
#assert(
  notice.vaccines_due_agents_array.len() > 0,
  message: "This overdue template requires vaccine agent data",
)
```

Do not impose that requirement on an affirmative or disease-based notice.

## Files and reproduction

Step 4 copies the selected template tree once, without changing its source:

```text
output/artifacts/
  render_jobs.json
  render/
    templates/                   # entry points, helpers, and assets
    data/en_notice_00001_123.json
    qr_codes/                    # present when QR generation is enabled
```

Each render job records the client ID, sequence, resolved identity, template,
data path, bounded workspace, and expected PDF. The pipeline passes only the
data-file reference through `sys.inputs`.

To reproduce a retained job with Typst 0.15.1:

```bash
typst compile \
  --root "/path/to/output/artifacts/render" \
  --input data=/data/en_notice_00001_123.json \
  "/path/to/output/artifacts/render/templates/legacy_overdue_v1.en.typ" \
  "/path/to/review.pdf"
```

Use the actual entry point and data filename from `render_jobs.json`.
A leading slash in Typst is relative to `--root`, not the operating system root.
Use forward slashes for imports and asset references. Relative imports within
the selected template tree retain their directory structure.

Keep `pipeline.after_run.remove_artifacts: false` to retain these inputs.
A manual compilation produces a review PDF; it does not certify the pipeline's
whole-cohort compilation or validation stage.

The same preparation and compilation functions are available to library callers:

```python
from pathlib import Path
from pipeline.generate_notices import prepare_render_jobs
from pipeline.compile_notices import compile_with_config

artifacts = Path("/path/to/output/artifacts")
pdfs = Path("/path/to/output/pdf_individual")
parameters = Path("/path/to/config/parameters.yaml")

prepare_render_jobs(
    artifacts / "preprocessed_clients_RUN_ID.json",
    artifacts,
    template_dir=Path("/path/to/my-phu"),
    config_path=parameters,
    pdf_dir=pdfs,
)
compile_with_config(artifacts, pdfs, parameters)
```

## Migrate a private Python template

Move the authored prose and layout into the corresponding `.typ` entry point.
Replace source placeholders with fields from `notice`; move presentation
conditions into Typst. Keep source normalization and localization in Python.
Retain the helper imports, assets, validation markers, and literal identity checks.

Remove the old Python module after testing the native entry point. Python-only
custom templates now produce an error naming the expected `.typ` path and the
module to migrate. There is no parallel Python renderer.

Before adopting the migrated template, compare representative PDFs for prose,
client details, history, validity symbols, QR links, branding, page numbering,
signature position, and envelope-window measurements. Include long records and
addresses. See the [testing guide](../developer_guide/testing.md) for the captured
synthetic baselines and real-compiler acceptance tests.
