# Private PHU templates

Keep PHU-specific native Typst files and assets in a directory you own.
Files beneath this directory are ignored by Git, apart from this README and
`.gitkeep`.

```bash
cp -r immuknow/templates phu_templates/my_phu
uv run viper students.xlsx en --template my_phu
```

For an installed package or an external location:

```bash
viper students.xlsx en --templates "/path/to/my PHU templates"
```

The selected directory supplies its own entry points, helpers, and assets.
Missing languages never fall back to English or to another PHU's templates.
Follow the [template authoring guide](../docs/user_guide/phu_templates.md) for
the supported layout, JSON contract, and identity assertions.
