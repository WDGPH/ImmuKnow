# Synthetic authoring examples

All people, identifiers, addresses, schools, and assessments here are invented.
They exercise presentation; they are not clinical forecasting examples. QR codes
encode only `https://example.invalid/immuknow-demo`.

`scenarios.json` is the authored source. `prepared.json` is generated through
`prepare_clients`, assignment eligibility, QR preparation, and
`prepare_render_jobs`, exactly as in production. It contains ten scenarios and
37 compatible notice/language variants. Unknown-validity examples are prepared
as their own cohort; mixing them with known-status source rows deliberately
triggers the production safeguard when validity markers are enabled.

From a checkout, regenerate or verify the committed facts and assemble the
static browser resources:

```bash
uv run python -m playground.scripts.examples
uv run python -m playground.scripts.examples --check
```

Assembly writes ignored `playground/public/generated/project.json`. The bundle
contains exact maintained template/package/asset bytes and SHA-256 hashes.
Browser example payloads are read-only; source CSV upload is not supported.
The long-history case intentionally extends across several pages. The several-
overdue case can extend the letter; authors can try a two-column list.

Complete project exports can include these separate synthetic CSV cohorts.
From the exported project root, use the real CLI with either selector:

```bash
uv run immuknow examples/known-overdue.csv --config config \
  --template templates/overdue_diseases_v1.en.typ --output demo-output
uv run immuknow examples/known-overdue.csv --config config \
  --notice-assignments examples/assignments.json --templates templates \
  --output demo-output
uv run immuknow examples/affirmative.csv --config config \
  --template templates/affirmative_schedule_v1.en.typ --output demo-output
```

Use `unknown-overdue.csv` alone to exercise all-unknown coverage. These commands
assume ImmuKnow is installed in the active environment. An exported draft does
not approve new wording or register a new notice version; use the production
catalog and local approval process for an intentional version change.
