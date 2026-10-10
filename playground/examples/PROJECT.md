# ImmuKnow template project

This archive contains the exact authored sources under `templates/`, the
vendored ImmuKnow Typst package 0.1.0, and selected configuration under `config/`.
`immuknow-project.json` records the selected entry point, compiler/package
versions, and SHA-256 hashes at export. Editing this project creates a draft;
it does not approve revised wording.

Install ImmuKnow separately in your Python environment and use Typst 0.15.1.
Production does not require Node, npm, or the playground. Use the pinned
FreeFont TTF archive `20120503-10build1` (archive SHA-256
`d1424c9d47b2a6bd0d5149ca66f2bab9b4365237bfbb6063659d961bab2f8ccb`)
for matching layout. Keep the complete `templates/` tree together when moving
this project. A single `.typ` download needs the same package and assets.

From this project directory, choose exactly one selector:

```bash
immuknow /path/to/cohort.csv --config config \
  --template templates/overdue_diseases_v1.en.typ --output /path/to/output
immuknow /path/to/cohort.csv --config config \
  --notice-assignments /path/to/assignments.json --templates templates \
  --output /path/to/output
```

Replace the single filename with the selected language/version as appropriate.
Each manifest row supplies `client_id` and a template filename, without a path.
Both selectors retain source validation, catalog eligibility, assertions,
PDF checks, encryption, and delivery settings. Review `config/parameters.yaml`
and locally approved branding, contacts, signatures, wording, and translations
before production use. The supplied branding is demonstration material.

Browser examples are fixed prepared facts: changing preprocessing/reference
configuration does not reprepare them. Edit explicit Typst parameters to test
presentation; run the real CLI to test preparation/configuration changes.
Label overrides under `config/translations/` do affect browser rendering.

For an intentional new version, rename the entry point using
`<version_id>.<en|fr>.typ`, update its literal version assertion, and add explicit
eligibility under `versions` in `config/notice_versions.yaml`, for example:

```yaml
versions:
  locally_approved_v2:
    kind: overdue
    requires: has_overdue
```

Retain the existing catalog entries needed by other notices. Do not infer
eligibility from a filename. Browser examples cover maintained identities;
custom identities require appropriate prepared inputs in the native workflow.

`examples/` contains optional invented CSV inputs and a demonstration assignment
manifest, separate from production inputs. `qr_codes/` contains only example
QR assets; production regenerates its own QR assets. See `examples/README.md`
for repeatable demo commands. Do not replace these with real cohort data for
public distribution.

To restore sources in the browser, ZIP this project's contents with
`immuknow-project.json` at the archive root and choose Import project. The
browser accepts at most 400 entries, 8 MiB per file and 24 MiB in total, rejects
unsafe paths and links, and does not fetch runtime packages. Vendor additional
Typst dependencies using relative imports. The PDF envelope guide is a viewer
overlay; it never enters exported PDFs. Check actual-size printing and folds.

Template defaults live in `templates/settings/<template>.typ`; paper and window
choices live in `templates/layout-settings.json`. The playground’s individual
`.typ` download inlines these settings. Complete project exports preserve the
editable companion files. Both forms still need the package, helpers and assets.
