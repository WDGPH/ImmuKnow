# Testing

Run checks from the repository root with the Rust toolchain in `rust-toolchain.toml`:

```sh
cargo fmt --all --check
cargo test --release --locked
cargo build --release --locked
cargo test --release --locked --test documentation
```

Use a focused test while developing, for example `cargo test --release --locked --test cli`. The CLI test uses fictional source rows and an unbranded project, exports embedded resources into a temporary directory, and runs the executable from outside the checkout. It exercises preparation, mixed notice outcomes, encryption, review bundles and saved-run changes. `tests/fixtures/render-contract.json` supplies native render-evidence cases; the schemas in `resources/schemas/` and `resources/typst/report.json` define their contract. Unit tests cover the PDF, input and worker boundaries. PDF round-trip tests reopen protected copies and bundles, checking AES-256 revision 6 settings, empty and wrong password refusal, correct password access, preserved pages/content and fresh encryption randomness. These release checks exercise the pinned library contract that production trusts after constructing and writing an artifact. The documentation test checks local links, commands and input schema references.

For a resource embedding or build-tracking change, use an isolated source copy
and verify ordinary cached release rebuilds after a resource-only edit, addition
and removal. Compare the exported bytes and resource identities at each step,
and confirm that restoring the original resources restores the original export.
Keep checkout resources unchanged and run without another Cargo job using the
same target directory.

Native compilation uses workstation fonts and embedded Typst. Inspect representative English and French PDFs after presentation, font or compiler changes, including long names, addresses and histories. CI runs the Rust release build and tests; it does not require a separate Typst executable.

To verify the vendored QR plugin with its pinned toolchain and WebAssembly target, run:

```sh
typst-plugins/qr/build.sh --check
```

`typst-plugins/qr/build.sh` without `--check` rebuilds the vendored artifact. CI packages the release executable and license after the build and tests pass. Each project should test its own behavior and handoffs rather than duplicate another project's complete test suite. The [ecosystem guide](../ecosystem.md) owns the cross-project contract.

## Test ownership and execution

| Behavior | Authoritative owner | Consumers | Test level | Verify on change |
| --- | --- | --- | --- | --- |
| Input, coordinator, PDF and saved-run behavior | Core | Operators, downstream systems | Small unit tests in `src/`; representative end-to-end cases in `tests/cli.rs` | Row identity, failures, artifacts and bundle decisions |
| Shared rendering schemas and evidence | Core | Template and Studio projects | Contract cases in `tests/fixtures/render-contract.json` and `src/validation.rs` | Schema and evidence handoff |
| Shared Typst library and QR component | Core | Templates and Studio | `tests/qr.rs` and QR artifact rebuild check | Rendering and shipped plugin |
| Settings, reference lists, notice wording and appearance | Template project | Core, operators and recipients | Project unit and representative rendering tests | Both languages and project-specific content |
| Assessment and assignments | Upstream system | Core and operators | Upstream unit and handoff integration tests | Exported rows and explicit selections |
| Browser editing and preview | Studio | Template authors | Studio unit and browser integration tests | Editing, preview and shared component behavior |
| Import and export between projects | Producing and consuming projects | Operators and other projects | Representative integration tests at each handoff | Compatibility and preservation of required fields |
| Release executable and documentation | Core | Installers and operators | CI release build, `tests/documentation.rs`, manual release review | Packaging, commands, links and representative PDFs |

The Rust workflow in CI runs on Linux with pinned notice fonts and tests the release build; the documentation test is included in the full test command. The QR artifact check runs in a separate path-filtered workflow when plugin or vendored QR files change. Representative PDF inspection is manual and depends on the project’s fonts and content. Run relevant checks on other supported deployment environments when changing platform-dependent behavior; Linux CI alone does not establish Windows compatibility. Check native fonts, paths, locks and extracted release execution on the intended platform.

Prefer focused unit tests for isolated normalization, policy, PDF and queue logic,
then representative integration cases for their combined behavior. Avoid repeating
the same malformed-input or encryption cases in every consuming project.

For a Core resource or schema update, run the contract cases, refresh Template's
complete shared library, then verify representative English/French notices,
long histories, addresses and branding. Template owns those authored layout
checks; Core fixtures establish the engine contract. A Studio pin update also
requires regenerated preview facts/assets, browser import/export and draft
checks, and a downloaded-project run against the intended native executable.
Studio's routine CI does not run the full browser/native suite; maintainers must
select its manual `full_tests` workflow for that handoff. See the
[Studio development guide](https://github.com/WDGPH/ImmuKnow-Studio/blob/main/docs/development.md).

Before release, extract the archive outside the checkout and exercise its
executable with a compatible fictional project and installed fonts. Verify
resources, reports, privacy-sensitive outputs and bundle membership. Operators
still review findings and actual deliverables for every production run; CI
cannot approve authored wording or local data handling.
