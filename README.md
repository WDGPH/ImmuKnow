# ImmuKnow

ImmuKnow turns Panorama/PEAR vaccination records into personalized immunization
notices and history charts. Python validates the records and prepares notice
data. Authored Typst templates produce the PDFs.

The maintained notices include legacy English/French notices, versioned
English/French overdue notices, and an English affirmative notice. Built-in
branding and contact details are samples; PHUs should supply their own templates.

## Install and run

Use Python 3.10 or later and **Typst 0.15.1**. The compiler can be selected through
`PATH`, `typst.bin` in the configuration, or `TYPST_BIN`.

From a checkout:

```bash
uv sync --group dev
uv run viper students.xlsx en --input ./input --output ./output
```

An installed package supplies the same `viper` command and all required default
templates, assets, and reference resources. It can run outside the repository:

```bash
viper /path/to/students.xlsx en --output "/path/to/notices"
```

Input files may be Excel or CSV and must satisfy the
[input schema](docs/user_guide/getting_started.md#preparing-input-data).
Fixed mode requires `en` or `fr` and works without an assignment catalog.

## Per-client assignments

Use a manifest and a configuration directory containing `notice_versions.yaml`
to assign different versions and languages within one cohort:

```bash
viper /path/to/students.xlsx \
  --notice-assignments /path/to/assignments.json \
  --config /path/to/config \
  --output /path/to/notices
```

The manifest keeps the existing `notice_version` spelling:

```json
[
  {"client_id": "1009876545", "notice_version": "overdue_standard_v1", "language": "en"},
  {"client_id": "2001234567", "notice_version": "overdue_standard_v1", "language": "fr"}
]
```

The resolved record uses `version_id`. If the source input also supplies
`version_id`, it must agree with the manifest. Defaults apply once during
assignment. Every later step uses the resolved client language.

Legacy fixed notices declare `legacy_overdue_v1` and display overdue diseases.
Versioned overdue notices display vaccine agents. Eligibility always follows
the overdue disease list. There is no built-in French affirmative notice; a
request for an unavailable template fails clearly.

## Customize templates

```bash
cp -r templates /path/to/my-phu
viper students.xlsx en --templates /path/to/my-phu --output /path/to/notices
```

Edit the `.typ` files, `conf.typ`, and assets together. The selected directory
is isolated from the built-ins. The convenience option `--template my_phu`
selects `phu_templates/my_phu/` under the caller's working directory.
Entry points are flat files such as `legacy_overdue_v1.en.typ` and
`overdue_standard_v1.fr.typ`.

Each entry point loads ordinary JSON through `sys.inputs` and asserts its
literal version and language before rendering. Python does not generate Typst
source. See the [template authoring guide](docs/user_guide/phu_templates.md)
for the full contract, installed-package examples, and single-notice reproduction.

## Pipeline and artifacts

| Step | Purpose |
|---|---|
| 1 | Prepare the selected output directory |
| 2 | Validate input, normalize records, resolve assignments and eligibility |
| 3 | Generate QR images when enabled |
| 4 | Prepare localized notice JSON and stage unchanged templates |
| 5 | Compile the explicit render jobs with Typst |
| 6 | Validate every expected PDF |
| 7 | Encrypt expected PDFs when enabled |
| 8 | Bundle by size, school, or board when enabled |
| 9 | Remove intermediates according to the cleanup settings |

The canonical artifact is `artifacts/preprocessed_clients_<run_id>.json`.
Each client retains its sequence, identity, canonical dates, vaccination history,
and resolved notice metadata. A mixed cohort has no single header language.

`artifacts/render_jobs.json` connects each client to its static template,
per-notice JSON, bounded workspace, and expected PDF.
`artifacts/compilation.json` records successful completion of all jobs.
Validation writes `metadata/validation_<run_id>.json`.
Assignment metadata is provenance, not evidence that a PDF succeeded.

PDFs remain in `pdf_individual/`; encrypted copies have an `_encrypted` suffix.
Bundles and their manifests account for every expected notice exactly once.
Mixed languages remain together under the configured grouping. Missing outputs
and compiler or validation errors fail the run. Stale files are not selected.

See the [architecture](docs/reference/architecture.md),
[step reference](docs/reference/pipeline_steps.md), and
[configuration guide](config/README.md), including QR, encryption, bundling,
PHIX validation, and assignment policies.

## Development checks

```bash
uv sync --all-groups
uv run ty check
uv run pytest
uv run pre-commit run --all-files
```

Real Typst compilation is required by the native acceptance tests and the CI
test job. The suite includes mixed-language processing, identity assertions,
failure propagation, custom templates, and a clean installed-wheel test.
The [testing guide](docs/developer_guide/testing.md) describes native compilation
checks and PDF review. Review release tags and Git history for past changes.
