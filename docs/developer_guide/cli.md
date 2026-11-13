# Command and facts reference

The standalone `immuknow` executable is the integration boundary. It embeds Typst 0.15.1 and its shared resources; no Python runtime or separate Typst command is needed.

```text
immuknow project sync [--project DIR] [--replace]
immuknow project check [--project DIR] [--sample]
immuknow run --sample [--project DIR] [--output DIR]
immuknow prepare --sample [--project DIR]
immuknow run CSV --project DIR (--notices JSON | --template FILENAME)
immuknow prepare CSV --project DIR (--notices JSON | --template FILENAME)
immuknow run CSV (--notice-assignments JSON [--templates DIR] | --template FILE)
  [--config DIR] [--output DIR] [--input-encoding utf-8-sig|cp1252|latin-1]
  [--compile-workers 1|2] [--encryption-workers N] [--bundle-workers N] [--timestamp UNIX]
immuknow prepare CSV (--notice-assignments JSON [--templates DIR] | --template FILE)
  [--config DIR] [--input-encoding utf-8-sig|cp1252|latin-1]
immuknow resources --output DIR
immuknow rebundle RUN_DIR [--policy policy.json] [--withhold ROW_KEY --reason TEXT]
  [--release ROW_KEY] [--bundle-workers N] [--filenames filenames.json]
immuknow warnings RUN_DIR [--refresh]
immuknow acknowledge RUN_DIR ISSUE_ID --reason TEXT [--revoke]
```

With `--notices` and no explicit project or templates path, Core uses `templates/` and `config/` in the working directory. Without `--project`, relative `--template` paths are resolved from the working directory.

`--project DIR` supplies `DIR/templates` and `DIR/config`. An explicit `--config` overrides the configuration folder. With an assignment file, `--templates` overrides the templates folder; it conflicts with `--template`. With a project, relative single-template names are resolved inside its `templates` folder; absolute template paths retain their existing meaning. CSV and assignment-file paths are always relative to the working directory. Selection stays explicit. `--notices` is a visible alias for `--notice-assignments`. The same project shortcut works with `prepare`.

Global display options are `--progress auto|plain|off` and `--emoji`. Progress and summaries use stderr; redirected stdout remains a single saved-record path for `run` and `rebundle`, or JSON for `prepare` and `resources`. The terminal summary prints the selected CSV paths, while stdout retains the saved-record path. Auto mode redraws a throttled progress line only on a capable terminal; elsewhere it writes plain stage announcements and occasional counts. Plain mode avoids redraws and styling; off hides all progress and summary output. `NO_COLOR` disables styling. Progress receipts contain only counts, not client information.

`warnings` lists distinct effective URL warnings from a completed saved run. `acknowledge` records or revokes review of an exact issue ID with a nonblank reason; it does not change findings or delivery. `warnings --refresh` regenerates the paired CSVs from the last checkpoint without adding a review event or compiling notices; readable failed and running `.incomplete` runs are accepted. See [PDF review](../user_guide/pdf_validation.md) for review scope and recovery.

## Run results

`run` saves source data, resource snapshots, originals, canonical facts and
validated evidence in a run directory. Facts remain in `run.json` rather than
separate per-row files. Final reporting publishes the paired CSVs and any
requested grouped PDFs. Warnings alone do not fail the command; a failed notice
or requested encryption produces a nonzero exit status. Readable originals with
failed checks go to review bundles. See [PDF review](../user_guide/pdf_validation.md)
for export fields, routing and saved-run changes.

## Prepared facts

`prepare` writes JSON to standard output without rendering PDFs. The envelope
has `schema_version: 2`, engine and resource identity, `input.sha256`, top-level
`checks` and `entries`. Every entry contains source identity, exact source
values, its validated explicit `assignment`, observed `checks` and a separate
`deferred_checks` list. Ready entries also contain `notice` and `blocked_checks`;
failed source preparation has no invented notice. Row keys preserve identity
even when client IDs are absent or repeated.

Invalid history or intended-reader values fail only their source rows. A
successfully written preparation envelope exits 0 even when it contains failed
rows; `run` and project checks retain failure exits. Requirements and coverage
checks stay deferred until compilation. Validated reports resolve them or
explicitly block dependent checks; corrupt evidence is rejected.

## Worker options

| Option | Values | Default |
| --- | --- | --- |
| `--compile-workers` | 1 or 2 | 2 on four or more available CPUs; otherwise 1 |
| `--encryption-workers` | 0 through 16; 0 runs inline | Same CPU-based default as compilation |
| `--bundle-workers` | 1 through 16 | 4 |

Compilation may finish out of order, but facts, findings, originals and progress
are committed in source-row order. `rebundle` also accepts `--bundle-workers`.

## Resources for authoring tools

The exported `schemas/input_schema.json` describes CSV fields and `schemas/rendering.json` describes notice facts (schema version 2). Compiled reports follow `typst/report.json` (schema version 4). The schema filenames are unversioned; each payload's `schema_version` identifies its format. The exported `typst/` directory is the shared library used by authored projects; copy it intact to the project's `templates/lib/immuknow/` directory. The shared report contract and Typst components remain part of that library. Projects provide their own configuration, reference data, notices, Settings, translations and assets.

The [template guide](templates.md) describes fields and component behavior. Studio and Template are separate projects with their own integration requirements.

## Resource compatibility

`immuknow resources --output DIR` exports `schemas/`, `typst/` and
`resource-manifest.json`. Export into a new folder when updating Core, then replace
the project's complete `templates/lib/immuknow/` copy. Existing identical files
are accepted; different files are not overwritten. Do not mix releases.
The manifest identifies resource contents, rather than a source commit; keep
the executable's source identity separately when pinning integrations.

Use `project sync` below to install the library directly. Project configuration
and reference lists are described in [configuration](../user_guide/configuration.md);
[projects and contracts](../ecosystem.md) defines resource ownership.

## Native project setup and samples

```sh
immuknow project sync --project project
immuknow project check --project project
immuknow project check --project project --sample
immuknow prepare --sample --project project
immuknow run --sample --project project
```

`project sync` installs the complete embedded Typst library into
`templates/lib/immuknow/`. It accepts identical files and refuses a different
library unless `--replace` is supplied. Replacement affects only that directory;
authored notices and configuration are preserved. Linked library paths are
rejected. `project check` compares the complete library and prepares the
project's fictional sample without modifying authored files. With `--sample`, it
also renders the sample in a temporary folder and removes the output afterwards.
Use `run --sample` to retain output and inspect its report. Warnings alone do
not fail a check; failures return a nonzero status. Check and sync print a short
text result; the existing run/prepare stdout formats are unchanged.

Project commands default to the current folder. `run` and `prepare` accept
`--sample` instead of a CSV and explicit notice selection. Sample paths come
from `sample.json` with exactly `csv` and `assignments` fields. If absent, the
conventional paths are `input/sample/sample_students.csv` and
`input/sample/sample_assignments.json`. Paths must name existing files inside
the project; absolute paths, parent traversal and links outside the project are
rejected. `--sample` cannot be combined with explicit input, selection, template
or configuration overrides. `--output` remains relative to the current working
folder, defaulting to `runs/`, just as for an explicit CSV run.

Template owns the sample records, authored notices, settings and reference lists;
Core supplies the generic setup and sample-selection behavior.
