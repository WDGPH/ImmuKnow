# Command and facts reference

The standalone `immuknow` executable is the integration boundary. It embeds Typst 0.15.1 and its shared resources; no Python runtime or separate Typst command is needed.

```text
immuknow run CSV --project DIR (--notices JSON | --template FILENAME)
immuknow run CSV (--notice-assignments JSON --templates DIR | --template FILE)
  --config DIR --output DIR [--input-encoding utf-8-sig|cp1252|latin-1]
  [--encryption-workers N] [--bundle-workers N] [--timestamp UNIX]
immuknow prepare CSV (--notice-assignments JSON --templates DIR | --template FILE)
  --config DIR [--input-encoding utf-8-sig|cp1252|latin-1]
immuknow resources --output DIR
immuknow rebundle RUN_DIR [--policy policy.json] [--withhold ROW_KEY --reason TEXT]
  [--release ROW_KEY] [--bundle-workers N]
```

With `--notices` and no explicit project or templates path, Core uses `templates/` and `config/` in the working directory. Legacy relative `--template` paths keep their existing meaning when no project is specified.

`--project DIR` supplies `DIR/templates` and `DIR/config`. Explicit `--templates` or `--config` paths override those defaults. With a project, relative single-template names are resolved inside its `templates` folder; absolute template paths retain their existing meaning. CSV and assignment-file paths are always relative to the working directory. Selection stays explicit. `--notices` is a visible alias for `--notice-assignments`. The same project shortcut works with `prepare`.

Global display options are `--progress auto|plain|off` and `--emoji`. Progress and summaries use stderr; redirected stdout remains a single saved-record path for `run` and `rebundle`, or JSON for `prepare` and `resources`. Interactive terminals show the readable report path instead of repeating the machine record path. Auto mode redraws a throttled progress line only on a capable terminal; elsewhere it writes plain stage announcements and occasional counts. Plain mode avoids redraws and styling; off hides all progress and summary output. `NO_COLOR` disables styling. Progress receipts contain only counts, not client information. No extra terminal-rendering thread or runtime dependency is introduced.

`run` processes a client list and saves a run directory with source data, resources, facts, originals, findings and grouped PDFs. `prepare` writes JSON to standard output without rendering PDFs. The envelope has `schema_version: 1`, engine and resource identity, `input.sha256`, and `entries`; each entry contains `row_key`, `client_id`, `source`, `assignment`, `notice`, and `checks`. `resources` exports `schemas`, `typst`, and a manifest from the executable. `rebundle` creates another set of grouped PDFs using the saved run. Warnings are eligible for sending by default. A failed notice or requested encryption produces a nonzero run exit; readable originals with failed checks are included in review bundles. The default is one encryption worker and four bundle workers.

## Resources for authoring tools

The exported `schemas/input_schema.json` describes CSV fields and `schemas/rendering.json` describes notice facts. The exported `typst/` directory is the shared library used by authored projects; copy it intact to the project's `templates/lib/immuknow/` directory. The shared report contract and Typst components remain part of that library. Projects provide their own configuration, reference data, notices, Settings, translations and assets.

The [template guide](templates.md) describes fields and component behavior. Studio and Template are separate projects with their own integration requirements.

## Updating an existing integration

Use the standalone commands instead of importing the former Python package.
`prepare` writes JSON to standard output, `run` prints the saved record path when stdout is redirected,
and `resources` exports the exact shared library and schemas from the executable.
A command exits with a nonzero status when its work fails. Review the saved
report to distinguish failed notices from successful ones.

Export resources into a new folder when updating Core, then replace the project's
complete `templates/lib/immuknow/` copy. Do not mix files from different releases.
The schema files are named `schemas/rendering.json` and `typst/report.json`;
Git tags identify their release, while JSON `schema_version` fields identify
the data format. The notice facts remain version 1 and the report remains
version 2. The report is saved separately from the PDF, without an attachment.

Resource export supplies no example configuration or regional reference lists.
Projects must provide their own files as described in [configuration](../user_guide/configuration.md).
When school checking is enabled and no path is set, Core looks for
`school_reference.json` in the selected configuration folder. It no longer falls
back to a regional list bundled with Core. Remove retired settings when updating
a project. Studio and Template integrations need their own corresponding updates;
this repository does not update those applications automatically.
