# Command and facts reference

The standalone `immuknow` executable is the integration boundary. It embeds Typst 0.15.1 and its shared resources; no Python runtime or separate Typst command is needed.

```text
immuknow run CSV (--notice-assignments JSON --templates DIR | --template FILE)
  --config DIR --output DIR [--input-encoding utf-8-sig|cp1252|latin-1]
  [--encryption-workers 1] [--bundle-workers 4] [--timestamp UNIX]
immuknow prepare CSV (--notice-assignments JSON --templates DIR | --template FILE)
  --config DIR [--input-encoding utf-8-sig|cp1252|latin-1]
immuknow resources --output DIR
immuknow rebundle RUN_DIR [--policy policy.json] [--withhold ROW_KEY --reason TEXT]
  [--release ROW_KEY] [--bundle-workers 4]
```

`run` processes a cohort and saves a run directory with source data, resources, facts, originals, findings and delivery bundles. `prepare` writes JSON to standard output without rendering PDFs. The envelope has `schema_version: 1`, engine and resource identity, `input.sha256`, and `entries`; each entry contains `row_key`, `client_id`, `source`, `assignment`, `notice`, and `checks`. `resources` exports `config`, `schemas`, `typst`, and a manifest from the executable. `rebundle` creates another delivery attempt using the saved run. Warnings are eligible for delivery; failures are reported and produce a nonzero run exit.

## Resources for authoring tools

The exported `schemas/input_schema.json` describes CSV fields and `schemas/rendering-v1.json` describes notice facts. The exported `typst/` directory is the shared library used by authored projects; copy it intact to the project's `templates/lib/immuknow/` directory. The shared report contract and Typst components remain part of that library. Template projects provide their own notices, Settings, translations and assets.

The [template guide](../user_guide/phu_templates.md) describes fields and component behavior. Integrations previously coupled to an earlier Core package must adopt the standalone commands and resource export. Studio and Template are separate projects and may require their own updates.
