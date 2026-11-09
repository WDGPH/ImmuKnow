# ImmuKnow

ImmuKnow turns a CSV of immunization information into personalized PDF notices.
You choose the notices; the source system assesses immunization status.

| Project | Description |
| --- | --- |
| ImmuKnow Core | Native processing engine: prepares data, creates PDFs, encrypts copies, assembles bundles and writes reports. |
| [ImmuKnow Template](https://github.com/WDGPH/ImmuKnow-Template) | Starter notices, translations, branding, settings and reference files to adapt for your organization. |
| [ImmuKnow Studio](docs/user_guide/studio.md) | Browser editor and preview environment. Native adoption is in [Studio #33](https://github.com/WDGPH/ImmuKnow-Studio/pull/33). |

See [projects and contracts](docs/ecosystem.md) for compatibility and resource ownership.

## Create notices

You need the `immuknow` executable, a CSV and a compatible configured notice project.
The [getting started guide](docs/user_guide/getting_started.md) explains setup and notice selection.

```sh
immuknow run clients.csv --project project --template overdue_diseases.en.typ
```

Open `report.html` in the new run folder and review the findings and PDFs before
sending notices. Warnings are eligible for delivery by default. See
[PDF review](docs/user_guide/pdf_validation.md) for checks, holds and rebundling.

## Build and develop

Install Rust 1.92 or later, then build the executable:

```sh
cargo install --path . --locked
```

Project setup and sample checks also run without Python:

```sh
immuknow project sync --project project
immuknow project check --project project --sample
immuknow run --sample --project project
```

`immuknow resources` exports shared components and schemas; `immuknow prepare`
produces prepared data without PDFs; `immuknow rebundle` uses a saved run's originals.

See [template authoring](docs/developer_guide/templates.md), the
[command reference](docs/developer_guide/cli.md) and
[contributing guide](docs/developer_guide/contributing.md).
