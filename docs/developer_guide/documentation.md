# Documentation

Keep one current guide for each contract: [getting started](../user_guide/getting_started.md)
for inputs and the complete workflow, [configuration](../user_guide/configuration.md)
for user options and reference data, [template authoring](../user_guide/phu_templates.md)
for native JSON and assertions, [Studio overview](../user_guide/studio.md) for the separate editor,
and [testing](testing.md) for native checks.
The [architecture](../reference/architecture.md) explains output evidence.
Link to these guides instead of copying them into new step descriptions.

Module docstrings should state purpose and important inputs, outputs, and
failures. Use types and examples when they clarify behavior. Test names and
docstrings should identify the user-visible behavior protected, especially
for compilation, mixed cohorts, and missing outputs.

## Shared language and project responsibilities

Use this standard in Core, Studio and Template, including documentation,
application messages, code, comments and docstrings.

Write for the person completing the task. Start with what they can do and what
happens next. Use concrete words, short sentences and the exact labels shown in
the application. Explain a technical term when readers first need it. Prefer
"prepared client records" or "disease names" when those are the facts meant.

Give each shared contract one maintained owner:

| Project | Owns the explanation of |
| --- | --- |
| ImmuKnow Core | Native inputs, notice selection, rendering resources, validation, saved runs and delivery |
| ImmuKnow Studio | Browser editing, previews, fictional examples, and project import and download |
| ImmuKnow Template | Local project setup, helper commands, readiness checks and project tests |

Link to the owning guide for details. Include enough context and commands for a
reader to complete the current task without reconstructing it across
repositories. A short handoff summary is useful; competing specifications of
validation or delivery are not.

Keep names readers must recognize exact: commands, flags, paths, API names,
schema fields, check codes and status values. Explain what they mean rather
than replacing them with approximate synonyms. A template is a source file; a
notice is the document it produces. Studio's fictional examples supply the
sample inputs in a downloaded project. Distinguish warnings, failed checks,
failed output steps and runs that stop before producing notices.

An error should explain what failed and, when known, what the person can do
next. Retain filenames, offending values, error codes and other details needed
to investigate. Do not promise that a suggested action will fix a problem
unless the program can establish that.

Keep user guidance focused on the task. Put implementation and maintenance
details in contributor documentation. Comments should explain constraints or
decisions that the code does not make clear. Docstrings should describe purpose
and significant inputs, results and failures. Prefer clear internal names;
rename existing ones only to resolve a concrete misunderstanding. Wording
changes must preserve validation, state changes and delivery decisions.

Update the owning explanation when behavior changes. Keep review history,
completed test runs and temporary migration notes in pull requests and Git
history. Repository guides describe current behavior and repeatable checks.

Keep pull request titles and descriptions short and plain. Explain the problem,
why the change helps and what readers will experience. A before/after example
can help a review; repository guides do not need that development history.
Omit agent attribution and detailed verification logs. Include validation details
only when they help a reviewer understand a material risk or limitation.

## Publish through the documentation hub

Documentation stays here. The public [WDGPH documentation hub](https://docs.phiz.ca/)
fetches this repository and builds `main` at `/immuknow/latest/` and recorded
stable `vX.Y.Z` tags at `/immuknow/vX.Y.Z/`. Its reviewed release lock chooses
the current release. A tag notification proposes a release-lock correction;
it does not approve or publish that correction.
This repository checks documentation and sends notifications; it does not
publish a separate Pages site or legacy redirects. The old manual is retired
without redirect compatibility. Disabling its former workflow does not remove
an already published GitHub Pages artifact: a repository administrator must
unpublish the old site in **Settings → Pages → Unpublish site**. Do this only for
`WDGPH/ImmuKnow`; the hub remains published at `docs.phiz.ca`.

The **Check documentation** workflow runs strict documentation builds on main
pushes, pull requests, and manual requests, using this repository's locked dependencies. The separate **Notify documentation
hub** workflow does not check out or execute project code. Once enabled, a push
to `main` requests a hub build, and a semantic-version tag push or deletion
requests a complete release reconciliation. The notification sends no source
content. There is no scheduled polling.

### Notification contract

The notifier is active when `DOCS_HUB_NOTIFY_ENABLED` is true. Its dispatch step
uses `DOCS_HUB_TRIGGER_TOKEN`, targets main in `WDGPH/docs`, and identifies
`WDGPH/ImmuKnow`. Documentation builds never receive that token.
The hub controls release-lock review and deployment.

### Correct tags and recover missed notifications

Use exact stable tags such as `v1.2.3`; prerelease tags and leading-zero versions
are not imported. The hub compares the full current tag set with its release
lock, so a delayed notification does not apply a stale event payload. It proposes
withdrawal for deleted tags and a changed commit for reused or moved tags.

[GitHub's tag events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
have two limits: a tag push executes the workflow recorded at the tagged commit,
so historical commits may lack this notifier, and creating/deleting more than
three tags at once can suppress events. Events created by a workflow's ordinary
`GITHUB_TOKEN` may also not trigger another workflow. After retagging a historical
commit, any bulk tag operation, or an operation performed with that token, run:

```bash
gh workflow run docs-hub-notify.yml --repo WDGPH/ImmuKnow --ref main
```

The Actions UI offers the same manual recovery. A deleted tag normally triggers
the notifier from the default branch, but run manual reconciliation after recreating
an old tag to ensure the final state is observed. Guaranteed automatic notification
for arbitrary historical tag commits requires a separately hosted GitHub webhook
or App relay; the Actions-only setup has this explicit maintenance step.

### Local documentation checks

For a local source check or Material preview:

```bash
uv sync --locked --no-default-groups --group docs
uv run --locked --no-default-groups --group docs python -m unittest discover -s docs -p 'test_*.py'
uv run --locked --no-default-groups --group docs python docs/generate_schema_docs.py
uv run --locked --no-default-groups --group docs python -m mkdocs build --strict
uv run --locked --no-default-groups --group docs python -m mkdocs serve
```

The hub supplies published branding. Keep local Material configuration plain;
retain Markdown extensions and navigation needed by the source content.

A documentation-only change does not require rebuilding native or browser
artifacts. Studio maintains its own build and browser checks in its separate
repository; a Core documentation build does not establish native/browser parity.
