# Example notices

These five invented scenarios exercise short and long histories, English/French
notices, incomplete facts, explicit assignment conflicts, affirmative wording
and an order that omits history. They contain no real client information.

`scenarios.json` owns raw CSV values, explicit entry filenames, sample identity
translations, and frozen dates/timestamp. Localization changes names, addresses
and schools; clinical facts and identifiers stay the same across variants.
`prepared.json` is generated through native source preparation, assignment
reconciliation and factual render-job preparation. Warnings remain beside each
selected payload. An affirmative notice deliberately assigned to overdue facts
retains those facts and its applicability warning.

```bash
uv run python -m studio.scripts.examples
uv run python -m studio.scripts.examples --check
```

`--check` rejects stale committed facts and still assembles ignored browser
assets under `studio/public/generated/`. The project JSON contains unchanged
native Typst/project files and verified SHA-256 hashes. All supported native
fonts are verified and copied separately to `generated/fonts/`; the JSON embeds
only their catalogs and license metadata. The generated `build.json` identifies
the shared native resources and Studio compiler; native package build details
remain separate.

Each example's `inputs` maps an entry basename to the exact source CSV and
assignment file included in the project. These source files reproduce a single
preview variant through either native selector. With ImmuKnow installed, run
from the generated/exported project root:

```bash
immuknow examples/clients/short.en.csv --config config \
  --template templates/overdue_diseases_v1.en.typ --output runs
immuknow examples/clients/short.fr.csv --config config \
  --notice-assignments examples/assignments/short.overdue_agents_v1.fr.json \
  --templates templates --output runs
immuknow examples/clients/source-warnings.en.csv --config config \
  --notice-assignments examples/assignments/source-warnings.affirmative_schedule_v1.en.json \
  --templates templates --output runs
```

Keep the warning source alone when reproducing its preview: validity coverage
is measured over the complete input cohort, so combining scenarios creates a
different cohort. The long-history example intentionally permits reviewers to
see content continuation and findings. The suspension example has valid source
history but places no history component or display checks.

Browser fixtures are fixed prepared facts. Edit `scenarios.json` and regenerate
to change them; edit the native Settings file to change presentation. Production
source preparation, assessment responsibilities and delivery behavior are
explained in the package guides.
