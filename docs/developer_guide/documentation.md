# Documentation

Keep each contract in its owning guide. [Getting started](../user_guide/getting_started.md) describes a run; [configuration](../user_guide/configuration.md) describes settings; [PDF review](../user_guide/pdf_validation.md) describes bundle decisions; and [template authoring](templates.md) describes the Typst project and facts. The [architecture](architecture.md) explains the native workflow and record. Link to the owning guide when another page needs context.

Use exact CLI options, paths, schema fields and statuses. Explain behavior for the person performing the task, including the distinction between warnings, failed checks and output failures. Keep user instructions separate from contributor implementation details. Use fictional examples and do not put client information in documentation.

Check source links, commands and key schema references locally:

```sh
cargo test --release --locked --test documentation
```

The documentation hub consumes this repository's Markdown and `mkdocs.yml`; the Core build and its documentation check require no documentation framework. The separate notification workflow informs the hub of changes. It does not publish the site or give the hub access to run data.

## Maintaining the visuals

The [user-facing performance guide](../user_guide/performance.md) owns the plain-language timing explanation. Its Gantt chart uses an approximate 60-second scale; keep precise timings out of the headline and caption. The [library map](../assets/pipeline-libraries.svg) belongs to the architecture guide. Both SVGs render directly on GitHub and in the documentation site without a diagram service.

The [interactive chart](../assets/notice-timing.html) is a standalone HTML file with no external dependencies or network requests. It starts paused, supports keyboard controls and pauses when its tab is hidden. Its inline `measurements` JSON matches [notice-timings.json](../assets/notice-timings.json), which records source commits, the input fingerprint, timing totals and half-second completion samples. Keep both copies together when updating measurements. The bars are approximate stage windows; the counters use recorded output completions, scaled to the displayed minute. Original completion is recorded when its encryption job starts, after the original has been saved; it is not an earlier PDF-export timestamp.

The measurements came from production commit `a5bfe974178731629810162f6b99f48f353cf5f8` and profiling commit `81ac287` on `experiment/workflow-profiling`. The profiling instrumentation is not part of the production application. That experiment measured a whole command without instrumentation at 57.76 seconds and a separate profiled command at 58.74 seconds, including 58.22 seconds inside the workflow. The detailed main-workflow slices exclude the concurrent encryption worker; they must not be added to worker totals. This is a recorded workload, not a general throughput guarantee.

After editing the chart, check play/pause, restart, speed selection, scrubbing, keyboard operation and the final counts (1,000 originals, 1,000 protected copies and 10 groups). Check a narrow screen, reduced-motion settings, JavaScript disabled, and a strict documentation build. Inspect SVG text for clipping. Keep the sample clients fictional.

## Recording the CLI demo

The README uses a real [VHS](https://github.com/charmbracelet/vhs) recording, generated from [notices.tape](../demo/notices.tape). It runs the normal command for six fictional clients at normal playback speed; it is not the 1,000-client benchmark. VHS, `ttyd`, `ffmpeg` and a browser are recording tools only, not application dependencies. Use the VHS installation instructions for your platform.

Install `immuknow` and the fonts required by a compatible ImmuKnow Template checkout. From the Core repository root, prepare a scratch directory (replace the Template path):

```sh
CORE_DIR="$PWD"
TEMPLATE_DIR=../ImmuKnow-Template
DEMO_DIR=$(mktemp -d)
mkdir "$DEMO_DIR/project"
cp -R "$TEMPLATE_DIR/templates" "$TEMPLATE_DIR/config" "$DEMO_DIR/project/"
cp "$TEMPLATE_DIR/input/sample/sample_students.csv" "$DEMO_DIR/clients.csv"
cp "$TEMPLATE_DIR/input/sample/sample_assignments.json" "$DEMO_DIR/notices.json"
immuknow resources --output "$DEMO_DIR/core-resources"
cp -R "$DEMO_DIR/core-resources/typst/." "$DEMO_DIR/project/templates/lib/immuknow/"
```

In the scratch copy of `project/config/parameters.yaml`, set `encryption.enabled` to `true`. The committed recording uses the six-client example from Template commit `782d8d4` with Core commit `a5bfe97`. Exporting the shared resources above lets a compatible project use the currently installed Core library. Then record:

```sh
cd "$DEMO_DIR"
vhs "$CORE_DIR/docs/demo/notices.tape"
```

Watch `notice-demo.gif` and check the generated run's report and all six notice outcomes before copying `notice-demo.gif` to `docs/assets/`. Start in a fresh scratch folder for each recording so `ls runs/*/` shows only that run. Keep outputs and local recording tools outside the repository. The short demo deliberately opens no PDF and exposes no personal data. Its final comment points the operator to `report.html`; the linked getting-started guide supplies the accessible text walkthrough.
