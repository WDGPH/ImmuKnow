--8<-- "immuknow/config/README.md"

## Portable native resources

The installed package includes a complete authored project: Settings, maintained
notices, English/French labels, images, the reusable Typst library, its licensed
QR encoder. Copy the whole `immuknow/templates/` tree
when creating a PHU project. Keep its supporting paths together when moving it;
an entry file alone is not a complete project.

Native compilation uses system fonts and Typst's built-in fallback fonts. No font
files are shipped in the native package or added by the engine. Set `body-font` in
`settings.typ` to an installed family name. A missing family produces a warning.
Studio previews use FreeSans and FreeSerif as web assets; **Include fonts** adds
those files to a project download for manual installation. Small differences in
appearance are acceptable; check the final native PDF.

Saved originals stay unchanged when creating new delivery batches. Review pages
use the fonts available on the machine running ImmuKnow.

The Python runtime needs the official Typst 0.15.1 executable. It does not require
Node, Rust, a browser, Pillow, or a Python QR encoder. QR construction and drawing
are authored in Typst Settings. Optional image inspection tools belong to the
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
