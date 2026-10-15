# Documentation

Keep one current guide for each contract: [getting started](../user_guide/getting_started.md)
for inputs and the complete workflow, [configuration](../user_guide/configuration.md)
for user options and reference data, [template authoring](../user_guide/phu_templates.md)
for native JSON and assertions, and [testing](testing.md) for checks.
The [architecture](../reference/architecture.md) explains output evidence.
Link to these guides instead of copying them into new step descriptions.

Module docstrings should state purpose and important inputs, outputs, and
failures. Use types and examples when they clarify behavior. Test names and
docstrings should identify the user-visible behavior protected, especially
for compilation, mixed cohorts, and missing outputs.

Use plain words that tell readers what a field or step actually does.
Prefer "prepared client records", "disease names", or "selected version"
over abstract labels when those are the facts meant.

Keep point-in-time results and implementation rationale in the pull request
and Git history. Repository guides describe current behavior and repeatable
checks.

## Publish through the documentation hub

Documentation stays here. The public [WDGPH documentation hub](https://wdgph.github.io/docs/)
fetches this repository and builds `main` at `/docs/immuknow/latest/` and recorded
stable `vX.Y.Z` tags at `/docs/immuknow/vX.Y.Z/`. Its reviewed release lock chooses
the current release. A tag notification proposes a release-lock correction;
it does not approve or publish that correction.

The **Check documentation** workflow runs strict documentation builds on main
pushes, pull requests, and manual requests, using this repository's locked dependencies. The separate **Notify documentation
hub** workflow does not check out or execute project code. Once enabled, a push
to `main` requests a hub build, and a semantic-version tag push or deletion
requests a complete release reconciliation. The notification sends no source
content. There is no scheduled polling.

### Notification contract

The notifier is active when `DOCS_HUB_NOTIFY_ENABLED` is true. Its dispatch step
uses `DOCS_HUB_TRIGGER_TOKEN`, targets main in `WDGPH/docs`, and identifies
`WDGPH/ImmuKnow`. Documentation builds and redirects never receive that token.
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

### Legacy redirects

The separate **Publish legacy documentation redirects** workflow is manual-only,
requires main and `DOCS_HUB_REDIRECT_ENABLED=true`, and publishes only a redirect
artifact through a protected Pages/OIDC job. The retired `gh-pages` branch is not
modified. No source documentation workflow publishes a full manual.

The redirect tool retains known old paths, including the generated schema page,
and a fallback for other legacy paths. JavaScript preserves queries and fragments;
known pages also have links without JavaScript. These are browser redirects.
Generate a local artifact in a new or empty directory with:

```bash
python tools/build_docs_redirects.py docs-redirects
```

For a local source check or Material preview:

```bash
uv sync --locked --group docs
uv run --locked --group docs python docs/generate_schema_docs.py
uv run --locked --group docs python -m mkdocs build --strict
uv run --locked --group docs python -m mkdocs serve
```

The hub supplies published branding. Keep local Material configuration plain;
retain Markdown extensions and navigation needed by the source content.
