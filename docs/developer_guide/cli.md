# Command and facts reference

The standalone `immuknow` executable is the integration boundary. It embeds Typst 0.15.1 and its shared resources; no Python runtime or separate Typst command is needed.

```text
immuknow run CSV --project DIR (--notices JSON | --template FILENAME)
immuknow run CSV (--notice-assignments JSON --templates DIR | --template FILE)
  --config DIR --output DIR [--input-encoding utf-8-sig|cp1252|latin-1]
  [--compile-workers 1|2] [--encryption-workers N] [--bundle-workers N] [--timestamp UNIX]
immuknow prepare CSV (--notice-assignments JSON --templates DIR | --template FILE)
  --config DIR [--input-encoding utf-8-sig|cp1252|latin-1]
immuknow resources --output DIR
immuknow rebundle RUN_DIR [--policy policy.json] [--withhold ROW_KEY --reason TEXT]
  [--release ROW_KEY] [--bundle-workers N] [--filenames filenames.json]
immuknow warnings RUN_DIR [--refresh]
immuknow acknowledge RUN_DIR ISSUE_ID --reason TEXT [--revoke]
```

With `--notices` and no explicit project or templates path, Core uses `templates/` and `config/` in the working directory. Without `--project`, relative `--template` paths are resolved from the working directory.

`--project DIR` supplies `DIR/templates` and `DIR/config`. Explicit `--templates` or `--config` paths override those defaults. With a project, relative single-template names are resolved inside its `templates` folder; absolute template paths retain their existing meaning. CSV and assignment-file paths are always relative to the working directory. Selection stays explicit. `--notices` is a visible alias for `--notice-assignments`. The same project shortcut works with `prepare`.

Global display options are `--progress auto|plain|off` and `--emoji`. Progress and summaries use stderr; redirected stdout remains a single saved-record path for `run` and `rebundle`, or JSON for `prepare` and `resources`. The terminal summary prints the selected CSV paths, while stdout retains the saved-record path. Auto mode redraws a throttled progress line only on a capable terminal; elsewhere it writes plain stage announcements and occasional counts. Plain mode avoids redraws and styling; off hides all progress and summary output. `NO_COLOR` disables styling. Progress receipts contain only counts, not client information. No extra terminal-rendering thread or runtime dependency is introduced.

`warnings` lists distinct effective URL warnings from a completed saved run. `acknowledge` records or revokes review of an exact issue ID with a nonblank reason; it does not change findings or delivery. `warnings --refresh` regenerates the paired CSVs from the last checkpoint without adding a review event or compiling notices; readable failed and running `.incomplete` runs are accepted. See [PDF review](../user_guide/pdf_validation.md) for review scope and recovery.

`run` processes a client list and saves a run directory with source data, resource snapshots, originals, canonical facts and evidence in `run.json`, paired CSVs and grouped PDFs. Facts are not written as separate per-row files. `prepare` writes JSON to standard output without rendering PDFs. The envelope has `schema_version: 2`, engine and resource identity, `input.sha256`, top-level `checks`, and `entries`. Every entry contains source identity, exact source values, its validated explicit `assignment`, observed `checks` and a separate `deferred_checks` list. Ready entries also contain `notice` and `blocked_checks`; failed source preparation has no invented notice. Invalid history or intended-reader values fail only their source rows. A successfully written preparation envelope exits 0 even when it contains failed rows; `run` and project checks retain failure exits. Requirements and coverage checks are deferred until compilation; validated reports resolve them or explicitly block dependent checks. `resources` exports `schemas`, `typst`, and a manifest from the executable. `rebundle` creates another set of grouped PDFs using the saved run. Warnings are eligible for sending by default. A failed notice or requested encryption produces a nonzero run exit; readable originals with failed checks are included in review bundles. Compilation and encryption each default to two workers when at least four CPUs are available to the process, otherwise one. `--compile-workers` accepts one or two; `--encryption-workers` accepts zero through 16, with zero running protection inline. Explicit values override these defaults. Bundling defaults to four workers. Compilation may finish out of order, but facts, findings, originals and progress are committed in source-row order.

## Resources for authoring tools

The exported `schemas/input_schema.json` describes CSV fields and `schemas/rendering.json` describes notice facts. The exported `typst/` directory is the shared library used by authored projects; copy it intact to the project's `templates/lib/immuknow/` directory. The shared report contract and Typst components remain part of that library. Projects provide their own configuration, reference data, notices, Settings, translations and assets.

The [template guide](templates.md) describes fields and component behavior. Studio and Template are separate projects with their own integration requirements.

## Resource compatibility

Export resources into a new folder when updating Core, then replace the project's
complete `templates/lib/immuknow/` copy. Do not mix files from different releases.
See [projects and contracts](../ecosystem.md#native-handoff) for resource identity,
schema versions and the preparation envelope. Project configuration and reference
lists are described in [configuration](../user_guide/configuration.md).

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

These commands need no Python, uv or project environment. Template owns the
sample records, authored notices, settings and reference lists; Core supplies
only the generic setup and sample-selection behavior.
