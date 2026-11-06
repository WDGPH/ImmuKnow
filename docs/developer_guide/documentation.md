# Documentation

Keep each contract in its owning guide. [Getting started](../user_guide/getting_started.md) describes a run; [configuration](../user_guide/configuration.md) describes settings; [PDF review](../user_guide/pdf_validation.md) describes bundle decisions; and [template authoring](templates.md) describes the Typst project and facts. The [architecture](architecture.md) explains the native workflow and record. Link to the owning guide when another page needs context.

Use exact CLI options, paths, schema fields and statuses. Explain behavior for the person performing the task, including the distinction between warnings, failed checks and output failures. Keep user instructions separate from contributor implementation details. Use fictional examples and do not put client information in documentation.

Check source links, commands and key schema references locally:

```sh
cargo test --release --locked --test documentation
```

The documentation hub consumes this repository's Markdown and `mkdocs.yml`; the Core build and its documentation check require no documentation framework. The separate notification workflow informs the hub of changes. It does not publish the site or give the hub access to run data.

## Maintaining the visuals

The [user-facing performance guide](../user_guide/performance.md) owns the plain-language timing explanation. Its proportional time budget rounds the main workflow to 60 seconds; keep precise timings out of the headline and caption. The [library map](../assets/pipeline-libraries.svg) belongs to the architecture guide. Both SVGs render directly on GitHub and in the documentation site without a diagram service.

The [interactive visual](../assets/notice-timing.html) has two views: **Spend the minute**, with selectable proportional blocks, and **Follow a notice**, with six illustrated steps and a replay of batch completions. It is a standalone HTML file with no external dependencies. It supports keyboard controls and pauses replay when hidden or when views change. Its inline `measurements` JSON matches [notice-timings.json](../assets/notice-timings.json). Keep both copies together when updating measurements. The downloaded data retains the finer activity bins for analysis; the interface no longer shows a Gantt chart.

The block areas use the measured main-workflow categories. Largest-remainder rounding makes the eight displayed counts total exactly 60 seconds. Rows of smaller blocks follow those same weights. This is a work budget, not a sequence or a trace of concurrent stages. The protected-copy callout is separate because that worker overlaps the main workflow. QR work remains inside Typst composition; it is not invented as a separately measured block. The walkthrough explains order without inventing per-notice timings. Replay counters use recorded completions, with original completion recorded when its encryption job starts, after saving the original.

The measurements came from production commit `a5bfe974178731629810162f6b99f48f353cf5f8` and profiling commit `81ac287` on `experiment/workflow-profiling`. The uninstrumented command took 57.76 seconds; the profiled command took 58.74 seconds, including 58.22 seconds inside the workflow. Instrumentation is not part of the production application. Main-workflow slices exclude the concurrent encryption worker and must not be added to worker totals.

After editing, check all eight blocks, both views, all six walkthrough steps, and replay play/pause, restart, speed and scrubbing. Final replay counts are 1,000 originals, 1,000 protected copies and 10 groups. Check keyboard use, a narrow screen, Automatic/Light/Dark themes, embedded theme changes, reduced-motion settings, the no-JavaScript static fallback, SVG clipping, and a strict documentation build. Keep examples fictional.

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
