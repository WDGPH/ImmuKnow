# ImmuKnow template project

This project keeps authored notices, Settings, assets, translations, the shared
Typst components under `templates/`. Native source bytes are
preserved. `config/` contains source reference data and example run options;
`build.json` identifies the application, data format, shared resources and compiler.
The branding and contact details are demonstration material.

Use the native compiler version recorded in `build.json` and install the matching
ImmuKnow package. Native execution needs no Node or browser runtime. Keep the
complete project tree together when moving it; native runs use system fonts. The download can optionally include basic font
files and licences for manual installation. QR codes are drawn by Typst
from prepared client data, using the destination authored in Settings.

Choose exactly one notice selector:

```bash
immuknow examples/clients/short.en.csv --config config \
  --template templates/overdue_diseases_v1.en.typ --output runs
immuknow examples/clients/short.fr.csv --config config \
  --notice-assignments examples/assignments/short.overdue_agents_v1.fr.json \
  --templates templates --output runs
```

Each manifest row supplies a string `client_id` and one template basename. The
filename supplies version and language; selection never changes either
implicitly. Optional experiment labels describe the explicit assignment.
An applicability conflict produces a finding and retains the selected notice.
Review all source and rendering findings before using revised wording.

`examples/` holds invented, runnable CSV/assignment pairs. The prepared example
metadata maps each preview variant to those exact inputs. See
`examples/README.md` for the scenario meanings and warning example. The pipeline
writes one private run with `run.json`, an HTML report, unchanged originals and
separate delivery/review artifacts. Review copies retain warnings and originals
remain available for saved-run rebundling.

```bash
immuknow-rebundle runs/<run-id> --accept-warning <token-from-report> --reason "Reviewed original"
```

Review branding, contacts, signatures, clinical source assessment and authored
prose before production use. Display choices and project label overrides live in
`templates/settings.typ` and `templates/translations/`. Python prepares the full
client data independently of those choices. Keep companion files with the
notices that use them.
