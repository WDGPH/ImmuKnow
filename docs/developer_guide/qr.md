# Working on QR codes

The shared Typst library uses a small Rust encoder to avoid doing QR calculations
in Typst. The encoder is built as WebAssembly, which Typst can load in both Core
and Studio. The compiled file is included in the project library; normal users
do not need a compiler or a separate QR installation.

The source lives in `typst-plugins/qr/`. That directory is separate from `src/`
because it builds a Typst plugin, rather than part of the native executable.
URL construction, links and drawing styles remain in the shared Typst library.

## Rebuild after a source change

Install rustup, then run these commands from the repository root:

```sh
rustup toolchain install 1.92.0 --profile minimal --component rustfmt,rust-src --target wasm32-unknown-unknown
typst-plugins/qr/build.sh
typst-plugins/qr/build.sh --check
cargo test --release --locked --test qr
```

The first build command replaces `resources/typst/vendor/qr/qr.wasm`. The second
rebuilds it and checks that the result matches the committed file. The build
script removes machine-specific paths so another machine can reproduce it.
Keep `rust-src` installed: its presence affects the paths in Rust's error code.
CI runs this same comparison when the plugin changes.

The plugin uses the unmodified MIT-licensed `qrcodegen` 1.8.0 encoder and
`wasm-minimal-protocol` 0.1.0 interface. Its own `Cargo.lock` and
`rust-toolchain.toml` pin the dependencies and compiler. Keep the licence notices
beside the compiled file when updating either dependency.

## How it connects to Typst

All exported functions take the destination as UTF-8 bytes and an error
correction level: `l`, `m`, `q` or `h`. Higher correction allows more damage to a
printed code, but can require a larger code. The encoder chooses the smallest
size that fits and the pattern with the best readability score. It keeps the
requested correction level. Non-ASCII text includes a UTF-8 declaration (ECI 26).
Errors never include the destination, which may contain personal information.

| Function | Returned bytes | Used for |
| --- | --- | --- |
| `encode` | Width, then one byte per square in row order (`0` light, `1` dark) | Styled codes and centre images |
| `encode_runs` | Width, then groups of three bytes: row, first dark column, end column (exclusive) | Plain square codes with non-RGB print colours |
| `encode_svg` | Width, then UTF-8 SVG bytes with a four-module quiet zone | Plain square codes in RGB or grayscale |

`encode_svg` also takes a foreground colour as `#rrggbb` or `#rrggbbaa`.
The plugin validates this value before including it in SVG. It emits one filled
path, with no URL, scripts or external references. The first byte supplies the
width so Typst can preserve the component’s existing size and baseline.
Backgrounds remain native Typst fills; non-RGB foreground colours retain the
native curve renderer to preserve their print colour space.

All widths and coordinates fit in one byte, including the largest QR size.
The compact row format lets Typst draw a plain code as one filled shape instead
of handling every square separately. The SVG path also avoids constructing
those curve commands in interpreted Typst. All three forms describe the same
code; the encoder, requested correction and best-of-eight mask selection are
unchanged.

The styled renderer consumes the matrix as row arrays of integer `0`/`1` values,
using `1` for a dark square. Typst converts the returned bytes in bulk; it does
not build a second boolean grid. The three 7×7 finder regions use direct bounds
checks across standard QR sizes. These changes leave the plugin protocol,
drawing order, quiet zone, colours and structural-marker protection unchanged.
Refresh the complete exported library when adopting them.

The QR test calls the shipped file through Typst, compares all three forms and
decodes the result independently. It covers all correction levels, size changes,
Unicode destinations and the maximum QR version (40). When changing how codes are drawn, also inspect and scan representative PDFs and Studio previews, including styled codes.

The [authoring guide](templates.md) describes module shapes, independent finder
and alignment colours, centre graphics and error correction. Styled modules and
centre graphics use the matrix renderer; the plain single-colour RGB/grayscale
code uses SVG. A different marker colour selects the styled renderer.
