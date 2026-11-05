--8<-- "immuknow/config/README.md"

## Portable native resources

The installed engine includes the reusable Typst library and its licensed QR
encoder under `typst/`. Complete starter projects belong to
[ImmuKnow Template](https://github.com/WDGPH/ImmuKnow-Template); Studio uses a
pinned copy of those authored files. Keep a project's templates, Settings,
translations, assets and configuration together when moving it. An entry file
alone is not a complete project.

Native compilation uses system fonts and Typst's built-in fallback fonts. No font
files are shipped in the native package or added by the engine. Set `body-font` in
`settings.typ` to an installed family name. A missing family produces a warning.
Studio previews use FreeSans and FreeSerif as web assets. Project downloads include
those fonts and their licences for manual installation. Small differences in
appearance are acceptable; check the final native PDF.

After changing `body-font`, inspect sample notices in each language, including
copying and searching their text. A font's text mapping can affect copying and
screen readers even when the printed page looks correct. The fonts in Studio
project downloads provide the shared presentation baseline.

Saved originals stay unchanged when creating new bundle sets. Rebundling needs
no fonts; it uses the completed PDFs.

The Python runtime needs the official Typst 0.15.1 executable. It does not require
Node, Rust, a browser, or a Python QR encoder. QR construction and drawing
use a bundled WebAssembly encoder and Typst drawing; Settings supplies QR options.
Optional image inspection tools belong to the
development environment.

Build native artifacts with the same Python versions supported at runtime:

```bash
uv run python scripts/build-native.py --out-dir dist
```

This command and ordinary `uv build` use the same build hooks. They write
`immuknow/build.json` inside each wheel or source archive, with the actual file
hashes, application and data-format versions, required native compiler version,
Python/build-tool versions, and available source revision. Source files are not
rewritten. A source archive retains its starting revision when rebuilt without
Git; changes to its recorded inputs set `source_modified` to true. When no source
revision is available, it is recorded as unknown rather than guessed.

Running from a checkout records current source details in the run itself and
creates no source `build.json`. Studio keeps its browser compiler pins in
`compiler-pins.json` in the separate Studio repository and generates separate project build details. Native
builds and installed execution do not read Studio files.
