# Private PHU templates

Keep PHU-specific native Typst files and assets in a directory you own.
Files beneath this directory are ignored by Git, apart from this README and
`.gitkeep`. The directory name has no special meaning to the CLI; pass its
path with `--templates`.

```bash
cp -r immuknow/templates phu_templates/my_phu
uv run immuknow students.csv --notice-assignments assignments.json \
  --templates ./phu_templates/my_phu
```

For an installed package or an external location:

```bash
immuknow students.csv --notice-assignments assignments.json \
  --templates "/path/to/my PHU templates"
```

For one entry point across the accepted cohort:

```bash
immuknow students.csv --template "/path/to/my PHU templates/overdue_diseases_v1.en.typ"
```

The selected file's version must be in the catalog, and its containing tree
supplies helpers and assets. Do not combine this option with a manifest or
template directory selector.

The selected directory supplies its own entry points, helpers, and assets.
Missing languages never fall back to English or to another PHU's templates.
Follow the [template authoring guide](../docs/user_guide/phu_templates.md) for
the supported layout, JSON contract, and identity assertions.
