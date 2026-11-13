# Documentation

Keep each contract in its owning guide. [Getting started](../user_guide/getting_started.md) describes a run; [configuration](../user_guide/configuration.md) describes settings; [PDF review](../user_guide/pdf_validation.md) describes bundle decisions; and [template authoring](templates.md) describes the Typst project and facts. The [architecture](architecture.md) explains the native workflow and record. Link to the owning guide when another page needs context.

Use relative links within this repository. For another project's living guides,
prefer its documentation website; use its repository's default branch when no
site is configured. Keep that project's setup, compatibility and
maintenance instructions in its own documentation. When a Core contract requires
a reviewed dependency revision, use an immutable commit URL and identify it. Avoid feature-branch URLs
that break when branches are deleted after merge.

Use exact CLI options, paths, schema fields and statuses. Explain behavior for the person performing the task, including the distinction between warnings, failed checks and output failures. Keep user instructions separate from contributor implementation details. Keep performance experiments, measurements and completed work plans outside the repository; summarize relevant results and limitations in pull requests. Use fictional examples and do not put client information in documentation.

Check source links, commands and key schema references locally:

```sh
cargo test --release --locked --test documentation
```

The documentation hub consumes this repository's Markdown and `mkdocs.yml`; the Core build and its documentation check require no documentation framework. The separate notification workflow informs the hub of main-branch updates, stable release tags and published stable releases. See [release builds](releases.md#documentation) for the required hub configuration. It does not publish the site or give the hub access to run data.

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
