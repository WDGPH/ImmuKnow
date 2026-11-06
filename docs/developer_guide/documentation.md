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

The [interactive visual](../assets/notice-timing.html) has two views: **Spend the minute**, a Chart.js stopwatch with selectable slices, and **Follow a notice**, with six illustrated steps and a replay of batch completions. The browser library is included locally under `docs/assets/vendor`; no CDN, framework, Node installation or network access is needed to view it. To use the interactive page offline, keep the assets folder together. Its inline `measurements` JSON matches [notice-timings.json](../assets/notice-timings.json). Keep both copies together when updating measurements. The downloaded data retains the finer activity bins for analysis.

The four slices group the measured main-workflow categories:

| Slice | Measured categories | Rounded seconds |
| --- | --- | ---: |
| Create the notices | Typst evaluation/layout, PDF export, cache cleanup | 41 |
| Prepare, check and save | Other preparation/writes, original PDF checks, file hashes | 10 |
| Group the notices | Combining PDFs | 6 |
| Write the report | Reports and checkpoints | 3 |

Largest-remainder rounding makes the slices total exactly 60 seconds. Selecting a slice shows its component tasks, rounded within that slice's allowance. Keep the static SVG and the canvas's text alternative consistent with those results. The clock represents aggregate work shares, not a chronological trace: notice work repeats per person, and files and reports are saved throughout. The protected-copy callout is separate because that worker overlaps the main workflow. QR work remains inside Typst layout; it is not invented as a separately measured slice. The walkthrough explains order without inventing per-notice timings. Replay counters use recorded completions, with original completion recorded when its encryption job starts, after saving the original.

Chart.js owns the doughnut geometry, resizing, tooltips and pointer selection. A small local drawing hook adds stopwatch ticks, the top button and the total. Native HTML buttons expose the same values and selection to keyboard and screen-reader users; descriptions and component tasks stay in HTML. The chart does not animate; the separate completion replay starts paused and pauses when hidden or when views change. Automatic appearance follows the surrounding documentation theme or the system preference, and repaints the canvas when that preference changes. A static SVG is available without JavaScript and when the library fails to load.

The pinned browser bundle is **Chart.js 4.6.1**, copied unchanged from `package/dist/chart.umd.min.js` in the [published npm package](https://registry.npmjs.org/chart.js/-/chart.js-4.6.1.tgz). Its SHA-256 is `87364cc2b2a76a6684929e7d6b80b18a897794db38400caff1fcf1791c6925d2`. The npm archive was checked against its published SHA-512 integrity value before copying. Preserve the Chart.js MIT license and the MIT license for its bundled **@kurkle/color 0.3.2** dependency. To update, verify the new package integrity, inspect its bundled dependency notices, replace the versioned browser file and licenses, update the HTML script path and these notes, then run the browser checks below. No application dependency changes are required.

The measurements came from production commit `a5bfe974178731629810162f6b99f48f353cf5f8` and profiling commit `81ac287` on `experiment/workflow-profiling`. The uninstrumented command took 57.76 seconds; the profiled command took 58.74 seconds, including 58.22 seconds inside the workflow. Instrumentation is not part of the production application. Main-workflow slices exclude the concurrent encryption worker and must not be added to worker totals.

After editing, check all four slices by clicking both the chart and the HTML buttons, confirm their total and component totals, both views, all six walkthrough steps, and replay play/pause, restart, speed and scrubbing. Final replay counts are 1,000 originals, 1,000 protected copies and 10 groups. Check keyboard use, a narrow screen, Automatic/Light/Dark themes, embedded theme changes, reduced-motion settings, the no-JavaScript and failed-library static fallbacks, offline use with no external requests, SVG clipping, and a strict documentation build. Keep examples fictional.

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
