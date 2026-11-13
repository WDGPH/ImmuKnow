# Release builds

Core ships one executable for each operating system and processor below. A
Cargo build normally targets the build machine; one executable does not run
across all four platforms.

## Platforms

| Download suffix | Rust target | Build and smoke-check runner |
| --- | --- | --- |
| `linux-x86_64.tar.gz` | `x86_64-unknown-linux-gnu` | Ubuntu 22.04 x64 |
| `windows-x86_64.zip` | `x86_64-pc-windows-msvc` | Windows Server 2022 x64 |
| `macos-aarch64.tar.gz` | `aarch64-apple-darwin` | macOS 15 Apple silicon |
| `macos-x86_64.tar.gz` | `x86_64-apple-darwin` | macOS 15 Intel |

Names include the package version, for example
`immuknow-2.0.0-windows-x86_64.zip`. Each archive contains the executable and
license. Shared resources and Typst are embedded. Install the fonts required by
your notice project separately; Python, uv and a Typst command are unnecessary.

Linux builds use the Ubuntu 22.04 GNU runtime baseline, rather than musl or a
fully static Linux executable. Windows builds link the C runtime statically.
Mac archives contain separate native executables. The workflow checks each
executable on its listed runner; older operating systems and other architectures
need separate compatibility checks. These downloads are unsigned; signing and
macOS notarization are not part of this workflow.

## Builds and publishing

Pull requests, pushes to `main` and manual runs of **Test Rust** build all four
archives. Linux runs the full release test suite, formatting and Clippy; each
platform checks the version and resource export from its extracted archive.
The archives are downloadable workflow artifacts. See [testing](testing.md)
for the scope of these checks.

To publish a release:

1. Update `package.version` in `Cargo.toml` and the root package entry in
   `Cargo.lock`, and merge the reviewed changes.
2. Tag the intended commit with `v` followed by that version, such as `v2.0.0`.
3. Publish a GitHub Release for that tag. Publishing a prerelease also starts
   binary builds; its tag must match the package version, such as
   `v2.0.0-rc.1` for package version `2.0.0-rc.1`.
4. Wait for **Test Rust** to finish. After all four builds and their checks pass,
   the workflow attaches the four archives and `SHA256SUMS` to that release.

A tag push alone does not publish binary assets. The release workflow checks out
the release tag and rejects a mismatch with `Cargo.toml`. Only the final upload
job has repository write permission. Failed builds leave the release without
new assets; rerunning the workflow replaces matching asset names. Archives
appear after the published release event, so publication and asset availability
are separate steps.

Download `SHA256SUMS` alongside your chosen archive and check its entry before
extracting. On Linux use `sha256sum --check --ignore-missing SHA256SUMS`; on
macOS compare `shasum -a 256 <archive>` with its entry. In Windows PowerShell use
`Get-FileHash <archive> -Algorithm SHA256` and compare the hash.

## Documentation

Merge [the coordinated documentation hub change](https://github.com/WDGPH/docs/pull/8)
before merging the native Core change. The hub supplies the shared schema-table
utility and its own MkDocs environment; Core does not need a Python lockfile.

The **Notify documentation hub** workflow requires repository variable
`DOCS_HUB_NOTIFY_ENABLED=true` and secret `DOCS_HUB_TRIGGER_TOKEN` with Actions
write access to `WDGPH/docs`. A push to `main` requests a hub build and deployment
of the latest documentation. Stable `vX.Y.Z` tag creation, deletion and release
publication request release reconciliation, including publication from an
existing tag. Prerelease tags do not enter the stable documentation catalog.
The hub owns release selection and publishing; a successful Core build alone
does not deploy the site. Tags created by another workflow using `GITHUB_TOKEN`
need an explicit hub dispatch because they do not trigger a tag-push workflow.
