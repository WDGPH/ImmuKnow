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

The QR test calls the shipped file through Typst, compares all three forms and
decodes the result independently. It covers all correction levels, size changes,
Unicode destinations and the maximum QR version (40). When changing how codes are drawn, also inspect and scan representative PDFs and Studio previews, including styled codes.

The [authoring guide](templates.md) describes module shapes, independent finder
and alignment colours, centre graphics and error correction. Styled modules and
centre graphics use the matrix renderer; the plain single-colour RGB/grayscale
code uses SVG. A different marker colour selects the styled renderer.

## Measure encoder and drawing costs

Use the same Typst executable, fonts, unique destinations and output format for
both revisions. The fixture accepts `off`, `encode`, `square`, `dots` and
`rounded` modes; use a fresh process for each timing and compare repeated runs.
`encode` includes WebAssembly loading and invocation, not just native Rust work.

```sh
typst compile --root . --ignore-system-fonts --input mode=square --input count=100 \
  typst-plugins/qr/benchmark.typ /tmp/immuknow-qr-benchmark.pdf
```

Measure the [complete native command](testing.md#measure-the-complete-command)
as well. Use each executable’s exported library: Core rejects a project whose
shared library does not match its executable. Keep encryption, bundling, input
facts and assignment mix identical; inspect saved outcomes before comparing
runtime. A QR-only compile cannot establish the same gain for a complete run.

A local 100-unique-QR comparison measured roughly 1.02 seconds for Typst-built
curves and 0.59 seconds for the SVG path. Complete 100-notice runs with
encryption disabled measured about 5.98 seconds versus 5.73 seconds (roughly 4% faster) across two uncontended repetitions.
With encryption enabled, two paired repetitions measured about 5.94 seconds
versus 5.51 seconds (roughly 7% faster). Each encrypted run retained 100 originals,
100 encrypted copies, 100 deliverable entries and one bundle, with identical
facts, assignments and QR destinations. These small repeated samples are
observations, not a statistical performance guarantee.
Preparation, notice layout, validation and bundling still cost time. Small ten-notice runs were too noisy to establish an improvement.
These measurements do not establish a hardware-independent speed or maximum throughput.

A subsequent complete-command comparison used the ten newer fictional clients
repeated with unique IDs: 1,000 two-page notices, 700 containing QR codes, 1,000
encrypted copies and ten PDF/CSV bundles. Under a shared 4-CPU / 8-GiB quota,
three paired repetitions measured these process-start-to-final-report times:

| Core | Median | Observed range |
| --- | ---: | ---: |
| Before (`7e873ef`) | 54.3 seconds | 54.2–55.9 seconds |
| SVG path (`c5d8b5a`) | 52.3 seconds | 52.3–53.0 seconds |

The median improvement was 3.7%, or about two seconds. Facts, assignments, QR
destinations, findings, page counts and delivery decisions matched across all
six runs. Builds and benchmark verification were outside the timed command;
encryption, bundling and reporting were included. The fictional input mix and
shared runner limit how broadly these observations apply.

The current encoder remains `qrcodegen`. An experimental
[`fast_qr` 0.14](https://github.com/erwanvivien/fast_qr) ASCII path reduced the SVG benchmark to about 0.51 seconds, but required a second
encoder for explicit Unicode ECI and nearly doubled the WebAssembly artifact.
That tradeoff is not adopted. Future experiments should measure bit-packed mask
scoring, [reusable version/mask templates](https://github.com/nayuki/QR-Code-generator/tree/master/java-fast)
and smaller SVG paths before adding more dependencies. Retain all eight mask candidates and decode outputs
independently; choosing a fixed mask just to improve a benchmark changes the
readability guarantee.

The C [libqrencode error-correction implementation](https://github.com/fukuchi/libqrencode/blob/master/rsecc.c)
uses finite-field lookup tables and caches generator polynomials. These are
additional strategies to profile before considering a port; no comparative
WASM speed claim has been established here. An exact-mask early-exit scoring
prototype showed no convincing improvement and was not adopted. Moving styled
geometry into Rust and coalescing SVG runs are further candidates; both still
need rendering, scanning and complete-command measurements.
