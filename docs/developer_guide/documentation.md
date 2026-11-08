# Documentation

Keep each contract in its owning guide. [Getting started](../user_guide/getting_started.md) describes a run; [configuration](../user_guide/configuration.md) describes settings; [PDF review](../user_guide/pdf_validation.md) describes bundle decisions; and [template authoring](templates.md) describes the Typst project and facts. The [architecture](architecture.md) explains the native workflow and record. Link to the owning guide when another page needs context.

Use relative links within this repository. For another project's living guides,
link to its default branch; when compatibility requires a reviewed revision, use
an immutable commit URL and identify that revision. Avoid feature-branch URLs
that break when branches are deleted after merge.

Use exact CLI options, paths, schema fields and statuses. Explain behavior for the person performing the task, including the distinction between warnings, failed checks and output failures. Keep user instructions separate from contributor implementation details. Use fictional examples and do not put client information in documentation.

Check source links, commands and key schema references locally:

```sh
cargo test --release --locked --test documentation
```

The documentation hub consumes this repository's Markdown and `mkdocs.yml`; the Core build and its documentation check require no documentation framework. The separate notification workflow informs the hub of changes. It does not publish the site or give the hub access to run data.

## Maintaining the visuals

The three diagrams have editable D2 sources in `docs/diagrams/` and generated SVGs in `docs/assets/`: `ecosystem`, `operator-journey`, and `processing`. Their shared palette, card dimensions, typography and edge styles live in `docs/diagrams/style.d2`. Commit updated sources and rendered SVGs together. The SVGs render on GitHub and in the documentation site without a diagram service.

Render with [D2 0.9.0](https://github.com/d2lang/d2/releases/tag/v0.9.0), using
its bundled open-source ELK layout engine. The imported style supplies the renderer
configuration, including both theme palettes. D2 is an authoring tool only; neither
Cargo checks nor MkDocs publishing needs it. From the repository root:

```sh
for name in ecosystem operator-journey processing; do
  d2 "docs/diagrams/$name.d2" "docs/assets/$name.svg"
done
```

The visual vocabulary follows the [PHIZ Git article](https://github.com/WDGPH/phiz/blob/main/content/posts/2026-10-git-and-github.md): neutral cards, thin borders, slim accent bars and clear text hierarchy. Green identifies applications and coordinator actions, blue identifies project files or PDF workers, and grey identifies data and saved outputs. The operator journey uses amber for review and red for unrenderable notices; every outcome is also named in text.

Use explicit grid cells to keep card edges and phase rows aligned. Declare
`accent; inset;` before spreading the shared card so local colour overrides do
not reorder its children. Use Markdown hard breaks (`\` at the end of a line)
inside labels; ordinary newlines fold into long text. Dashed worker edges carry
jobs and returned results in the processing diagram.

The `architecture-diagram` region and `assets/diagrams.css` keep a readable
minimum image width on narrow screens. Verify keyboard and touch scrolling
without page overflow; retain the full-size link for GitHub and other readers.

Keep explanatory text next to each image and useful alternative text. Inspect
SVGs in a browser, both directly and embedded at documentation width, in light
and dark system themes and on a narrow screen. SVG dark mode follows the system
preference; it may differ from a manually selected site theme. Keep diagrams
static and make their text explanations sufficient without images or JavaScript.

For a local publishing check, provision MkDocs and Material separately and run
`mkdocs build --strict`. This builds the repository configuration; the hub owns
its deployment and any surrounding navigation. Inspect the built pages after
changing navigation or diagrams. Do not commit local build tools or site output.

The [performance guide](../user_guide/performance.md) owns the timing explanation. Its table groups the measured main-workflow categories and uses largest-remainder rounding to total 60 seconds. Keep the [measurement data](../assets/notice-timings.json), benchmark provenance and overlapping encryption distinction when updating it.

## Recording the CLI demo

The README uses a real [VHS](https://github.com/charmbracelet/vhs) recording, generated from [notices.tape](../demo/notices.tape). It runs the normal command for six fictional clients at normal playback speed; it is not the 1,000-client benchmark. VHS, `ttyd`, `ffmpeg` and a browser are recording tools only, not application dependencies. Use the VHS installation instructions for your platform.

Install `immuknow`, DejaVu Sans Mono for the recording, and the fonts required by a compatible ImmuKnow Template checkout. From the Core repository root, prepare a scratch directory (replace the Template path):

```sh
CORE_DIR="$PWD"
TEMPLATE_DIR=../ImmuKnow-Template
DEMO_DIR=$(mktemp -d)
cp -R "$TEMPLATE_DIR/templates" "$TEMPLATE_DIR/config" "$DEMO_DIR/"
cp "$TEMPLATE_DIR/input/sample/sample_students.csv" "$DEMO_DIR/clients.csv"
cp "$TEMPLATE_DIR/input/sample/sample_assignments.json" "$DEMO_DIR/notices.json"
immuknow resources --output "$DEMO_DIR/core-resources"
cp -R "$DEMO_DIR/core-resources/typst/." "$DEMO_DIR/templates/lib/immuknow/"
```

In the scratch copy of `config/parameters.yaml`, set `encryption.enabled` to `true`. The recording uses the six-client example from Template commit `782d8d4` with the current standalone Core. Exporting the shared resources above lets a compatible project use the currently installed Core library. Then record:

```sh
cd "$DEMO_DIR"
vhs "$CORE_DIR/docs/demo/notices.tape"
```

Watch `notice-demo.gif` and check the generated run's report and all six notice outcomes before copying `notice-demo.gif` to `docs/assets/`. Start in a fresh scratch folder for each recording so the demo creates only one run. Keep outputs and local recording tools outside the repository. The short demo shows the actual default progress display and completion summary with a larger font and narrower terminal. It opens no PDF and uses only fictional information. The summary points the operator to `report.html`; the linked getting-started guide supplies the accessible text walkthrough.

After recording, extract its final frame as `notice-demo.png`, for example with
`ffmpeg -i notice-demo.gif -update 1 notice-demo.png`. Commit the GIF and still
together after inspecting both. The README's `picture` selects the still for
`prefers-reduced-motion: reduce`, with an explicit static link for other readers.
Verify both media preferences in a browser; the getting-started guide remains
the text explanation.
