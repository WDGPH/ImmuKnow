# Testing

Run checks from the repository root with the Rust toolchain in `rust-toolchain.toml`:

```sh
cargo fmt --all --check
cargo test --release --locked
cargo build --release --locked
cargo test --release --locked --test documentation
```

Use a focused test while developing, for example `cargo test --release --locked --test cli`. The CLI test uses fictional source rows and an unbranded project, exports embedded resources into a temporary directory, and runs the executable from outside the checkout. It exercises preparation, mixed notice outcomes, encryption, review bundles and saved-run changes. `tests/fixtures/render-contract.json` supplies native render-evidence cases; the schemas in `resources/schemas/` and `resources/typst/report-v2.json` define their contract. Unit tests cover the PDF, input and worker boundaries. The documentation test checks local links, commands and input schema references.

Native compilation uses workstation fonts and embedded Typst. Inspect representative English and French PDFs after presentation, font or compiler changes, including long names, addresses and histories. CI runs the Rust release build and tests; it does not require a separate Typst executable.

To verify the vendored QR plugin with its pinned toolchain and WebAssembly target, run:

```sh
plugins/qr/build.sh --check
```

`plugins/qr/build.sh` without `--check` rebuilds the vendored artifact. Build a release archive containing the executable and license with `scripts/build-native.sh`; an optional first argument selects its output directory. Each project should test its own behavior and handoffs rather than duplicate another project's complete test suite.
