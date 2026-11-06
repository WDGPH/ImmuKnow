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

Both exported functions take the destination as UTF-8 bytes and an error
correction level: `l`, `m`, `q` or `h`. Higher correction allows more damage to a
printed code, but can require a larger code. The encoder chooses the smallest
size that fits and the pattern with the best readability score. It keeps the
requested correction level. Non-ASCII text includes a UTF-8 declaration (ECI 26).
Errors never include the destination, which may contain personal information.

| Function | Returned bytes | Used for |
| --- | --- | --- |
| `encode` | Width, then one byte per square in row order (`0` light, `1` dark) | Styled codes and centre images |
| `encode_runs` | Width, then groups of three bytes: row, first dark column, end column (exclusive) | Plain square codes |

All widths and coordinates fit in one byte, including the largest QR size.
The compact row format lets Typst draw a plain code as one filled shape instead
of handling every square separately. Both forms describe the same code.

The QR test calls the shipped file through Typst, compares the two forms and
decodes the result independently. It covers all correction levels, size changes
and Unicode destinations. When changing how codes are drawn, also inspect and
scan representative PDFs and Studio previews, including styled codes.
