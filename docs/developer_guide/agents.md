# Agent Development Guidelines


## Read first

* **Standards**:
    * `docs/developer_guide/documentation.md`
    * `docs/developer_guide/testing.md`
    * `docs/developer_guide/code_analysis.md`

---

## Workflow

1. **Understand:** read code, trace flows, grep usages, read docs.
2. **Plan:** design around findings.
3. **Implement:** imports at top, types, meaningful docstrings.
4. **Test:** `uv run pytest` with markers.
5. **Configure:** add parameters under the correct step in YAML with comments.
6. **Document:** update standards or docstrings when feature‑complete. **Avoid standalone reports; strongly focus on integrating findings into existing docs and keeping them up to date.**

---

## Collaboration

* Present findings in the conversation as Markdown. Do not emit temporary files or heredoc tricks.
* Integrate durable learnings into standards, module comments, or docstrings.
* End each task by archiving insights where future contributors will look.

---

## Package layout

* **Orchestrator:** `pipeline/orchestrator.py` is the `viper` CLI entry point and coordinates 9 steps.
* **Steps:** Modules are organized by steps 1–9, not by functional themes.
* **Templates:** `templates/` contains authored `.typ` entry points, shared `conf.typ`, and assets. Python prepares JSON and render jobs; Typst owns document source and asserts each notice identity. `--templates PATH` selects an external PHU directory; `--template NAME` selects `phu_templates/NAME/` beneath the working directory. Private PHU materials remain ignored. See the template authoring guide for the JSON contract and migration.

---

## Dependencies

Single source of truth: `uv.lock`.

* Code to locked versions. No runtime fallbacks for alternate APIs.
* Upgrades:

  ```bash
  uv lock --upgrade
  uv sync
  uv run pytest
  git add uv.lock && git commit -m "deps: upgrade"
  ```
* If a version bump is required, update `pyproject.toml`, run `uv sync`, test, and commit the new lockfile.

---

## Configuration (`config/parameters.yaml`)

* Organize by pipeline step with headers, e.g., `# Step 3: Generating QR Codes`.
* Use dot notation and `snake_case` keys, e.g., `qr.enabled`, `qr.payload_template`.
* Document inline in YAML.
* Validate quickly:

  ```bash
  uv run python -c "import yaml,sys; yaml.safe_load(open('config/parameters.yaml')) or sys.exit(0)"
  ```

---

## Code style

* Imports at top: future → stdlib → third‑party → local.
  ```python
  from __future__ import annotations
  import json
  import yaml
  from .config_loader import load_config
  ```
* Use type hints, f‑strings, docstrings, dataclasses.
* No wildcard imports.
* Depth and significance guidance lives in `docs/developer_guide/code_analysis.md`.

---

## Quality gates (pre‑commit)

One‑time setup:

```bash
uv sync --group dev
uv run pre-commit install
```

Manual run:

```bash
uv run pre-commit run --all-files
```

Hooks (block commits on failure): `ruff check --fix` then `ruff format`.

---

## Type checking (`ty`)

Check before tests:

```bash
uv run ty check
```

Resolve all type errors or justify with `# type: ignore` and a short comment.

---

## Command execution discipline

Run each shell command once. Investigate before re‑running.

* If you need stderr, include it from the start: `2>&1`.
* On hangs or failures, inspect state (`git status`, file contents) before retrying.
* After interruptions, verify outcomes before re‑execution.

---

## Engineering principles

Applies at all times. Compatibility posture is noted where behaviour differs before and after 1.0.

1. **Simplicity first.** Prefer straightforward code over abstraction. Use native structures freely. Extract helpers only when they reduce duplication or improve clarity.
    * *Compatibility note:* pre‑1.0 favors rapid simplification with no backward‑compat guarantees. Post‑1.0 preserve public contracts when changing code.
2. **Clear boundaries and reuse.** Colocate helpers with the step that uses them. Extract to `utils.py` only when reused by ≥2 modules and clarity improves. Prefer pure, side‑effect‑free helpers with action‑oriented names.
3. **Deterministic, step‑isolated pipeline.** Steps read inputs from disk and write outputs to disk. Do not pass in‑memory state via the orchestrator. Same input → same output, including ordering and filenames.
4. **Contracts over defensiveness.** Centralize input validation in preprocessing and output checks in dedicated validation steps. Fail fast with precise exceptions. Do not add silent fallbacks.
5. **Naming and public surface.** Functions use `snake_case` with verbs (e.g., `prepare_render_jobs`). Do not rely on leading underscores for privacy; document intent. Only the orchestrator exposes a CLI; no per‑module parsers.
6. **Dependencies are locked.** Write to the APIs in `uv.lock`. If an API changes, upgrade and re‑lock. Do not branch at runtime to support multiple versions.
7. **Errors and logging.** Catch only exceptions you can handle meaningfully. Raise actionable messages. Log at step boundaries and major operations. Informative, not noisy.
8. **Parallel development without drift.** Keep core steps stable (preprocess, notices, compile, validate). Optional steps (encryption, batching, cleanup) may evolve independently if contracts hold. Update tests and docs with any schema or layout change.
9. **Tests are the spec.** Update tests with behavior changes. Use integration tests for quick feedback and E2E tests for coverage. Test native rendering outside the checkout with a bounded run-local file root.
10. **Documentation placement.** Enduring standards live here and in `docs/`. Point‑in‑time analyses and refactor plans live in `docs/`.
    - **Single canonical working document per initiative.** During a feature or refactor effort, maintain one authoritative document (e.g., `docs/DEFENSIVE_CODE_AND_HELPERS_PLAN.md`). Append progress (phases, decisions, status) to that file instead of creating new phase‑specific Markdown files.
    - Prefer sections like "Status", "Decision Log", and dated "Updates" within the canonical doc over new files such as `PHASE_X_START.md` or `PHASE_X_COMPLETION.md`.
    - If interim files were created, integrate their content back into the canonical doc and avoid introducing new ones. Link to historical PRs/commits for provenance rather than duplicating documents.

---

## Tests: quick reference

Setup once:

```bash
uv sync --group dev
```

Run pipeline:

```bash
uv run viper <input.xlsx> <en|fr>
```

Run tests:

```bash
uv run pytest                           # all
uv run pytest -m unit                   # unit only (~2s)
uv run pytest -m "not e2e"              # skip e2e
uv run pytest tests/e2e/ -v             # only e2e
uv run pytest tests/test_file.py::TestClass::test_name -v
```

Coverage:

```bash
uv run pytest --cov=pipeline --cov-report=html  # opens htmlcov/index.html
```
