# Contributing

Trace a change through the Rust workflow in `src/pipeline.rs`: preserve source rows, prepare facts and assignments, compile independent notices, record findings, create requested encrypted copies, assemble bundles, and write the report. Change tests and user guidance at the boundary affected by the behavior.

Core owns input preparation, PDF creation and grouping. The upstream system assesses immunization status. Typst projects control wording and appearance; Core's unbranded fixtures are for tests. See the [template guide](templates.md) for the rendering contract and the [architecture](architecture.md) for saved-run behavior.

Install the pinned Rust toolchain and run the [relevant checks](testing.md). For presentation or compiler changes, inspect representative English and French output, including long names, addresses and histories. Explain the resulting behavior, verification and material limits in the pull request. Do not commit real client data, derived passwords, run artifacts or private PHU assets.

## Build the executable

The native crate uses Rust 1.100 or later and edition 2024. The toolchain file
pins the compiler, Rustfmt and Clippy for reproducible checks. Cargo rejects
unused direct dependencies through `[lints.cargo]`; keep `Cargo.lock` unchanged
when updating only the compiler. The [QR plugin](qr.md) has its own toolchain
pin and reproducible WebAssembly build.

Install Rust 1.100 or later, then run from the repository root:

```sh
cargo install --path . --locked
```

For development, `cargo build --release --locked` writes the executable to
`target/release/immuknow`. The application includes Typst; it needs neither a
separate Typst command nor Python. Install the fonts required by your notice
project. See [testing](testing.md) before submitting a change.
