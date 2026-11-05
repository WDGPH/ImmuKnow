# QR encoder

The shared Typst library bundles `immuknow/typst/vendor/qr/qr.wasm`.
It uses the unmodified MIT-licensed `qrcodegen` 1.8.0 encoder and Typst's
`wasm-minimal-protocol` 0.1.0 interface. Cargo.lock pins all build dependencies;
`rust-toolchain.toml` pins Rust 1.92.0 and the WebAssembly target.
Native installation, wheel/source-archive builds and Studio use the bundled
artifact and need no Rust installation.

To change the plugin, install rustup, edit this source, then run from Core:

```sh
python plugins/qr/build.py
python plugins/qr/build.py --check
```

The build removes machine-specific source paths. The focused CI workflow
rebuilds the artifact and requires identical bytes when plugin inputs change.
Install the pinned `rust-src` component too: Rust's embedded panic locations
depend on whether its source is installed.
Core's normal test matrix does not build Rust. Keep the upstream and Rust
licence notices beside the artifact when updating dependencies.

The plugin accepts UTF-8 destination bytes and one error-correction letter
(`l`, `m`, `q`, `h`). It emits the matrix width as one byte followed by one
byte per cell in row order (`0` light, `1` dark). Non-ASCII text includes
UTF-8 ECI 26. The encoder chooses the smallest fitting version and the best
mask; it never silently increases the requested error-correction level.
Errors return fixed descriptions without including the destination.

URL construction, links, findings and visual styling remain in Typst. Test
changes at that boundary: independently decode native and browser outputs,
including Unicode, correction levels and styled symbols. The shared testing
guide in `docs/developer_guide/testing.md` describes the cross-project checks.
