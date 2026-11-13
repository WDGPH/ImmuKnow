# Documentation

Keep each contract in its owning guide. [Getting started](../user_guide/getting_started.md) describes a run; [configuration](../user_guide/configuration.md) describes settings; [PDF review](../user_guide/pdf_validation.md) describes bundle decisions; and [template authoring](templates.md) describes the Typst project and facts. The [architecture](architecture.md) explains the native workflow and record. Link to the owning guide when another page needs context.

Use relative links within this repository. For another project's living guides,
link to its default branch; when compatibility requires a reviewed revision, use
an immutable commit URL and identify that revision. Avoid feature-branch URLs
that break when branches are deleted after merge.

Use exact CLI options, paths, schema fields and statuses. Explain behavior for the person performing the task, including the distinction between warnings, failed checks and output failures. Keep user instructions separate from contributor implementation details. Keep performance experiments, measurements and completed work plans outside the repository; summarize relevant results and limitations in pull requests. Use fictional examples and do not put client information in documentation.

Check source links, commands and key schema references locally:

```sh
cargo test --release --locked --test documentation
```

The documentation hub consumes this repository's Markdown and `mkdocs.yml`; the Core build and its documentation check require no documentation framework. The separate notification workflow informs the hub of changes. It does not publish the site or give the hub access to run data.

## Maintaining the visuals

The two workflow diagrams have editable D2 sources in `docs/diagrams/` and generated SVGs in `docs/assets/`: `operator-journey` and `processing`. Their shared palette, card dimensions, typography and edge styles live in `docs/diagrams/style.d2`. Commit updated sources and rendered SVGs together. The SVGs render on GitHub and in the documentation site without a diagram service.

Render with [D2 0.9.0](https://github.com/d2lang/d2/releases/tag/v0.9.0), using
its bundled open-source ELK layout engine. The imported style supplies the renderer
configuration, including both theme palettes. D2 is an authoring tool only; neither
Cargo checks nor MkDocs publishing needs it. From the repository root:

```sh
for name in operator-journey processing; do
  d2 "docs/diagrams/$name.d2" "docs/assets/$name.svg"
done
```

The visual vocabulary follows the [PHIZ Git article](https://github.com/WDGPH/phiz/blob/main/content/posts/2026-10-git-and-github.md): neutral cards, thin borders, slim accent bars and clear text hierarchy. Green identifies workflow and coordinator actions, blue identifies PDF workers, and grey identifies data and saved outputs. The operator journey uses amber for review and red for unrenderable notices; every outcome is also named in text.

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

## Recording the CLI demo

The [CLI recording](../assets/notice-demo.gif) and its [static completion summary](../assets/notice-demo.png) show a fictional sample run.

The demo is a real [VHS](https://github.com/charmbracelet/vhs) recording, generated from [notices.tape](../demo/notices.tape). It runs the normal command for six fictional clients at normal playback speed. VHS, `ttyd`, `ffmpeg` and a browser are recording tools only, not application dependencies. Use the VHS installation instructions for your platform.

Install `immuknow`, DejaVu Sans Mono for the recording, and the fonts required by a compatible ImmuKnow Template checkout. From the Core repository root, prepare a scratch directory (replace the Template path):

```sh
CORE_DIR="$PWD"
TEMPLATE_DIR=../ImmuKnow-Template
DEMO_DIR=$(mktemp -d)
cp -R "$TEMPLATE_DIR/templates" "$TEMPLATE_DIR/config" "$DEMO_DIR/"
python3 - "$TEMPLATE_DIR" "$DEMO_DIR" <<'PY'
import csv
import json
import sys
from pathlib import Path

template, demo = map(Path, sys.argv[1:])
sample = template / "input/sample"
with (sample / "sample_students.csv").open(newline="", encoding="utf-8") as source:
    reader = csv.DictReader(source)
    fields = reader.fieldnames
    clients = list(reader)[:6]
assert len(clients) == 6, "The demo needs six fictional sample clients"
with (demo / "clients.csv").open("w", newline="", encoding="utf-8") as target:
    writer = csv.DictWriter(target, fieldnames=fields)
    writer.writeheader()
    writer.writerows(clients)
ids = {client["client_id"] for client in clients}
assignments = json.loads((sample / "sample_assignments.json").read_text(encoding="utf-8"))
selected = [assignment for assignment in assignments if assignment["client_id"] in ids]
(demo / "notices.json").write_text(json.dumps(selected, indent=2) + "\n", encoding="utf-8")
PY
immuknow project sync --project "$DEMO_DIR" --replace
```

In the scratch copy of `config/parameters.yaml`, set `encryption.enabled` to `true`. The recording selects the first six clients and their matching notice assignments from the compatible Template sample; copying the entire sample would run ten clients. The sync command installs the currently installed Core library into the scratch project. Then record:

```sh
cd "$DEMO_DIR"
vhs "$CORE_DIR/docs/demo/notices.tape"
```

Watch `notice-demo.gif` and check the generated run's CSV pair and all six notice outcomes before copying `notice-demo.gif` to `docs/assets/`. Start in a fresh scratch folder for each recording so the demo creates only one run. Keep outputs and local recording tools outside the repository. The short demo shows the actual default progress display and completion summary. It opens no PDF and uses only fictional information. The summary points the operator to the CSV pair; the linked getting-started guide supplies the accessible text walkthrough.

After recording, extract its final frame as `notice-demo.png`, for example with
`ffmpeg -i notice-demo.gif -update 1 notice-demo.png`. Commit the GIF and still
together after inspecting both. Link to the static summary alongside the recording so readers can view the
result without animation. The getting-started guide remains the text explanation.
