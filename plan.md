# Cross-repository execution plan

Filename templates are implemented across Core, Template and Studio. Reference fixes are committed in Template and await Studio adoption. Grouping safeguards and optional sorting are implemented and verified in Core; downstream adoption remains. The remaining work follows the milestones below. Three Terra scouts inspected the repositories. The investigation evidence comes from source, not a replay of the private production run.

This tracked file is the shared source of truth for scope, status, execution order and cross-repo decisions. Core’s implementation checklist follows the shared plan below. Consumer work lists: [Template](../ImmuKnow-Template/plan.md), [Studio](../ImmuKnow-Studio/plan.md). Keep shared-contract changes consistent across those files.

## What the completed run tells us

The reported run finished in **384.5 seconds**, created **5,837 notices / 11,674 pages**, requested no protected copies, and produced **60 ready bundles / 1 review bundle**. Its terminal summary reported **5,836 rows with warnings, 1 failed and 0 held**. The terminal warning figure counts rows whose highest effective severity is warning, not distinct warnings; the HTML warning filter can also include warning-bearing failed rows. A review-bundle count is a count of PDFs, not clients.

This establishes that a large run completed. It does not identify the failed check or prove that the repeated warnings all concern URLs. First inspect a local aggregate of finding code, observed/effective status, affected-row count and compiler diagnostics. Keep client details and full personalized URLs out of the plan and any shared profiling output.

Initial investigation baselines (historical, before filename implementation):

| Repo | Revision | Role |
| --- | --- | --- |
| ImmuKnow | `7784d9ce0dff6fc14d8061fd1aefc45df76e799d` | Native preparation, shared Typst components, policies, PDFs, bundles and reports |
| ImmuKnow-Template | `9f098ab9ec3569d3fa5463b15ccd1842aa3fe16d` | Authored settings, references, notices, labels and fictional examples |
| ImmuKnow-Studio | `b2a3e8e132b43b204c38992916acaa8afb98baf8` | Editor, browser previews, project import/export and pinned resource consumption |

These SHAs explain the initial investigation; they are not checkout targets for execution. Filename work has since landed locally. The currently adopted runtime pins are Core `f2f3c3a11e20f12caff85e8531529180e8fdc797` and Template `dbe9ed2f0233395970f63cc357c36fe271525c28`. Template's reference fixes are committed at `b129c7a286483261332d3403e51d064b476f4711` and await consumer adoption. Start from current source and retain completed filename behavior.

## Execution status and order

| ID | Status | Owner / consumers | Deliverable |
| --- | --- | --- | --- |
| F0 | Complete | Core + Template → Studio | Configurable individual/protected and normal/review bundle filenames |
| R1 | Template complete; Studio adoption pending | Template → Studio | Meningococcal/TIg reference and display fixes |
| R2a | Contract draft under critical review | Core, with Template/Studio consumers | Freeze executable fixtures for notice-local requirements and deferred preparation |
| R2b | After R2a | Core + Template → Studio | Implement that contract, remove notice YAML, retain readable failed notices for review, detect empty agent displays |
| G1 | Core complete; consumer adoption pending | Core; upstream export owner | Safe grouping for missing/conflicting school identity |
| W1 | Ready; independent of R2/G1 | Core | Structured per-link evidence and run-level warning aggregation |
| W2 | Design task after W1 | Core; Studio consumes relevant evidence | Define and implement run-scoped warning acknowledgment without changing delivery |
| S1 | Core complete; consumer adoption pending | Core + Template; Studio handoff | Optional last-name/DOB ordering within bundles |
| D1 | Explore | Core + Template + Studio | Disease identity/alias/label catalog; unrelated to removing the notice catalog |
| H1 | Later | Core | Measured, lossless report-size improvement |
| PR1 | Low priority | Core operator/developer workflow | Profile the real native workload |

Complete R1's Studio adoption independently. R2a is a finite design-and-fixture task, not permission to let three implementations invent different contracts. R2b starts once its schema/examples and expected outcomes are written and reviewed. G1 and W1 may proceed independently. W2, D1, H1 and PR1 are explicitly not implementation-ready feature specifications yet.

## 1. Reference fixes: preserve what worked

The user's successful project edits are now committed in Template; Studio still needs to adopt that resource revision:

- Add `"Meningococcal disease": "Meningococcal"` to disease normalization. All 14 meningococcal-related agent entries already map to `Meningococcal`; leave those mappings alone.
- Add `"TIg": ["Tetanus"]` to the agent reference. Add `TIg` to both history `ignore-agents` and overdue-agent exclusions. Recognized in facts does not mean displayed as a vaccine.
- Remove redundant `"Varicella": "Varicella"` normalization if cleaning the file; unchanged names already pass through. No other alias cleanup is required for this fix.

Template owns these authored files. Core should test generic normalization/reference behavior with fictional fixtures; Studio should consume the updated Template package rather than maintain another copy.

## 2. Coverage, eligibility and displayed content

Current coverage preparation computes required diseases, agent coverage, missing diseases, extra diseases and unmapped agents in [Core input.rs](src/input.rs), in `prepare`. A missing disease triggers `ensure!` before prepared rows reach the rendering/policy/review workflow. Eligibility currently comes from a separate notice catalog; the agreed direction is to move requirements into the notices themselves.

Proposed behavior:

| Situation | Default result | Delivery consequence |
| --- | --- | --- |
| Agent-based notice, missing disease coverage | Row failure | Render when safe; readable original goes to review |
| Disease-based notice, missing disease coverage | Row warning | Normal bundle remains eligible under current warning policy |
| Extra covered diseases / unmapped agents | Retain warning and measurements | Review the source/reference; do not silently discard facts |
| No diseases or agents | Not applicable where the notice permits it | Eligibility remains a separate check |
| Missing/invalid requirements or unknown coverage basis | Mandatory evidence/requirements failure, even if no diseases are missing | Readable original goes to review; no inference from filenames or obsolete YAML |

**Agreed design: requirements live beside the notice wording.** Replace the separate `config/notice_versions.yaml` catalog with a shared notice-local helper that emits validated eligibility/coverage metadata and structured findings through the existing compiled report. Keep eligibility distinct from coverage basis; review affirmative, suspension, conditional and custom notices individually. Core prepares source facts and coverage measurements. The shared Typst helper evaluates the declared content requirements and emits the same findings in native and browser compilation; Core validates the compiled evidence and applies delivery policy. Do not add a second JavaScript evaluator or independently implement eligibility semantics in Rust.

A plain `assert` aborts compilation and produces no PDF. Use structured warnings/failures for conditions where a readable notice should remain available in a review bundle. Keep assertions for cases where producing any PDF is inappropriate or impossible. Review existing affirmative/suspension assertions rather than replacing every assertion indiscriminately.

**v2.0 release decision:** this is a prerelease breaking release. Remove the notice YAML catalog and its reader outright; do not add legacy compatibility, fallback loading or a deprecation period.

Implementation requirements:

- Add the shared helper and report/schema support in Core before Template adopts it. Use the ordinary compilation/report extraction; do not add source-text parsing or a second compilation just to discover requirements.
- Delete catalog loading, its data structures and catalog-only findings. Notice-local requirements are the sole contract. Missing, malformed or contradictory declarations produce explicit evidence/requirements failures; an obsolete YAML file must not supply defaults or alter the result.
- Preparation computes facts and coverage measurements without stopping on a notice-dependent mismatch. Use the R2a deferred-check contract below; final runs must resolve the render-dependent checks and preserve independent-row processing.
- Record requirements and observed results with the compiled evidence. Rebundling uses saved observations and policy, without recompilation or silently reinterpreting the original notice under a newer declaration.
- Update maintained notices/languages, fixtures, package contents, setup/readiness checks and documentation together. Remove `config/notice_versions.yaml` from starters and test fixtures. Verify valid v2 notices run without it, old YAML cannot influence checks, and missing local requirements remain visible rather than silently passing. Ordinary authored-file preservation remains; no catalog-specific import compatibility is needed.

The optional future disease catalog for aliases/labels is a separate concern; this decision retires the **notice eligibility catalog**, not reference data.

### R2a: shared contract milestone

The evaluator split above is decided. Before R2b production changes, add the proposed schema/example cases to the shared render-contract fixtures and document these concrete boundaries:

- Core adds trusted coverage measurements to the prepared notice so the shared helper can evaluate them. Template declares intent; the shared helper owns eligibility/coverage finding generation; native/browser validators enforce schema, identity, required-check presence and consistency. Core retains source parsing, explicit assignment identity/version-conflict checks and delivery policy. Remove catalog-only fields/checks, not unrelated assignment safeguards.
- Require exactly one **placed** active requirements declaration for a verified report, including an explicit neutral declaration when no condition applies. A missing, duplicate (even identical), malformed or contradictory declaration produces a mandatory structured requirements failure; the report contract must represent that failed outcome. Preserve the readable original for native review and the rendered browser preview with a failure indication. Do not turn a declaration problem into a Typst assertion/compilation failure. A conditional template emits only its active branch’s declaration; unplaced content cannot supply it. Do not scan source text.
- Distinguish declaration failures within otherwise source-matched evidence from genuinely corrupt/malformed report envelopes or wrong-row identity. The latter rejects claimed findings and produces mandatory `render.evidence_failed`. Artifact retention is independent: an already rendered readable PDF/preview remains available with an explicit failure, never a verified/ready indication. R2a needs absent/duplicate/malformed declaration and corrupt-identity cases with expected native/browser artifact retention.
- Specify the declaration field names/enums, coverage measurement shape and affected schema/envelope versions in the fixture patch. Current preparation/payload/report versions are 1/1/2; advance affected versions together for the breaking contract, updating shared identity guards and consumers. Do not overload `notice_variant` or reintroduce redundant catalog `kind` defaults.
- `prepare` returns an explicit per-entry deferred-check list **outside** observed `checks`. Eligibility/coverage absent from `checks` does not mean passed. Do not put placeholder findings into authoritative observations. After validated compilation, a valid declaration supplies `notice.requirements: pass` and exactly one result for each dependent eligibility/coverage/display check. An invalid declaration supplies mandatory `notice.requirements: fail`, with the dependent check codes and blocking reason in `blocked_checks` outside observations. Clear deferred checks when compilation is resolved; blocked is distinct from pending or not applicable. Corrupt evidence still produces mandatory `render.evidence_failed`. Neither failed branch can route as ready.
- Studio preserves that deferred list in generated examples, permits rendering of those examples, and shows a neutral “Checked when the notice compiles” advisory until a current validated result exists. Deferred checks do not increase warning counts. Keep last-successful/stale-preview labeling intact. Validate all final findings through the shared exported contract.
- Eligibility mismatch defaults to a structured failure. Convert the affirmative and suspension **eligibility assertions** to findings so readable PDFs reach review. Keep fundamental schema/input/layout assertions when no trustworthy PDF can be rendered. Preserve the current affirmative predicate and existing ISPA selection semantics; do not add new clinical rules.
- The fixture patch must include a maintained-notice table: eligibility predicate, agent/disease/neutral coverage basis, and intentional no-records/alternative-text branches for each notice/language. Determine those branches from the authored behavior, not the deleted YAML. An intentional replacement is not an accidentally empty recommendation; the display component must record that distinction.
- Keep new requirements/coverage/display failure codes non-adjustable initially. Expanding acceptance/override eligibility is separate work. Record final observations and requirements in saved evidence; rebundling applies policy to those saved results without compiling or reevaluating edited notices.

R2a is done when these fixture cases and their expected native/browser outcomes are unambiguous. R2b implements them with one shared evaluator; it must not make fresh schema/severity choices independently in each repo.


Keep three questions separate: what upstream says is overdue, whether an assignment fits the facts, and what the notice actually displays. Flu/COVID display exclusions must not remove clients or change source coverage. Do not automatically switch notice types.

The shared `overdue-agents` helper currently filters the display list after preparation and records only component presence. Add placed-content evidence for source count, displayed count and excluded agents. For an agent-based notice whose nonempty source list becomes empty, default to a row failure and review the readable PDF. Distinguish an intentional no-records replacement or explicitly authored alternative from an accidentally empty list. A disease-based notice with no agent component should not fail this display check.

## 3. Acceptance: reuse the policy foundation, define the scope

Existing infrastructure is useful but partial:

- Core keeps observed `checks` separately from `effective_checks`.
- Global and exact-row rule changes support enabled/severity plus a reason, but only for render codes marked `x-adjustable`. `data.forecast_coverage` is a preparation check and is not currently adjustable.
- Saved runs support policy changes, holds/releases and fresh numbered bundle attempts. Releasing a hold does not override a failed check.
- Warnings already permit normal delivery. Readable originals with failures go to review; no usable original means report-only.
- Raw compiler diagnostics are a separate warning source and must remain distinguishable.

Core's [AGENTS.md](AGENTS.md) currently says “Do not add … warning-waiver machinery.” The user’s request takes precedence and authorizes this design investigation. Acknowledgment that preserves findings and routing need not be a waiver; reconcile contributor guidance if the selected behavior conflicts with it.

W1 delivers **deduplicated review presentation** first. W2 then specifies **run-scoped acknowledgment**; the user wants this capability, so the design task is to choose its interface and persistence, not to reopen whether it is useful. Acknowledgment means the operator has reviewed an observation. It must not convert its observed status to pass or change delivery routing. Show total affected rows, distinct issues and unacknowledged issues separately. Preserve severity-based status/exit behavior unless a later, explicit policy change defines otherwise.

For URL checks:

1. Emit structured subjects for offending destinations instead of extracting them from prose. `content.link_https` and `content.link_destination` need per-destination identity. `content.multiple_links` concerns the complete set of destinations; accepting one link is insufficient to accept an unseen combination.
2. Default acknowledgment scope is one saved run, including its rebundle attempts. Record the issue identity, reason and acknowledgment time. A new run or changed subject needs review again; persistent project allowlists are a separate decision.
3. Match code + check-definition/resource identity + exact destination identity, or the exact sorted destination set for a multiple-links finding. Use a fingerprint for indexing; retain protected raw evidence. Any URL canonicalization must preserve meaningful path, query and fragment differences. Do not group merely by hostname.
4. Personalized QR destinations can contain client ID/DOB. Do not strip those values to make different links appear identical. Exact matching is safe for the initial design. A future authored-link identity would need its own validated template/resource scope before it can stand for many personalized destinations.
5. New links, changed templates, changed check semantics and unrelated findings must remain visible. Acknowledged details remain expandable and the decision survives report regeneration/rebundling without modifying originals.

W2 is not ready for production implementation until its short contract specifies the operator action (prefer a native CLI command for a saved local run), a revoke/undo action, lock-protected persistence/audit, report refresh, and accessible presentation. Acknowledgment should not trigger recompilation, encryption or new bundles. Exercise acknowledgment/revocation through report regeneration and rebundle; no cross-run carryover is included. Broad error-override infrastructure remains separate exploration.

A general framework should share finding identities, scopes and observed/effective history, **not make every error overridable**. Define an explicit registry of mandatory versus adjustable checks and supported scopes. Consider selected preparation checks only after they become row findings. Identity/evidence corruption, unusable originals, requested encryption failures, unsafe paths and write failures remain blocking. Do not use blanket code suppression to implement per-link acceptance.

## 4. Where checks belong and what can go to review

| Stage | Current location | Proposed boundary |
| --- | --- | --- |
| Source parsing, normalization, references, coverage and assignments | Core `input.rs` / `pipeline.rs` | Isolate row problems when trustworthy identity and facts can still be retained; coverage is the first concrete fix |
| Placed content, links, layout and render evidence | Core shared Typst library + `validation.rs` | Validate the actual notice; emit row findings with structured subjects |
| Effective severity and allowed overrides | Core `policy.rs` | Keep observations immutable and overrides explicit |
| Original/encrypted artifact creation | Core compiler/PDF/pipeline | Preserve readable originals; do not claim absent/unusable artifacts can be bundled |
| Routing, page counts, grouping and bundle writes | Core `bundles.rs` | Normal / review / held / report-only remain distinct |
| Review presentation | Core `report.rs` / terminal | Aggregate repeated warnings while retaining row evidence and actual artifact outcomes |
| Fictional browser preview | Studio | Consume the shared contract; do not create a production batch-review service |

Audit other preparation `?`/`ensure!` exits after fixing coverage. Separate shared setup failures from expected row failures; global configuration/resource/manifest ambiguity and storage failures can still stop a run. A bad row that cannot yield trustworthy render facts should remain a failed report entry while later independent rows proceed. Never fabricate a PDF solely to place a row in review. Preserve source-row identity and partial-run accounting throughout.

## 5. Completed filenames; remaining grouping and ordering

F0 is complete. [Template's active settings](../ImmuKnow-Template/config/parameters.yaml) use individual `{client_id}_{notice_variant}_{language_code}`, normal bundle `{route}_{bundle_number}`, and review bundle `review_{bundle_number}`. Those work with the starter's size-only grouping. [Core's filename guide](docs/user_guide/configuration.md#filename-templates) owns supported fields, normalization/collisions, fallback warnings and `rebundle --filenames`; do not reimplement them.

`{last_name}_{first_name}_{client_id}_{notice_variant}` and `{school}_{notice_variant}_{bundle_number}` are supported **custom examples**, not the shipped defaults. A school/variant pattern requires consistent member values; set grouping appropriately, for example `[school, notice_variant, language]`. Completed filename work did not change grouping or sorting.

Core previously grouped school/board by ID, falling back to an empty string. G1 now uses namespaced identity derived from normalized board/school names when IDs are absent and reports that fallback. Review the upstream export for missing and conflicting IDs. Entirely unknown school identity no longer becomes one normal school group. Display names remain filename inputs, not grouping identifiers. G1 outcomes: missing IDs with usable names warn and use normalized, namespaced board/school fallback keys; no usable identity fails and keeps each row separate for review; one ID associated with conflicting normalized names fails all affected rows and keeps conflicting identities apart. Different nonblank IDs remain separate even when names match. No fuzzy school matching. These findings apply only when the affected dimension participates in grouping.

S1 adds `bundling.sort_by: last_name_dob` **within each group, before splitting into bundle-size chunks**: normalized last name, then parsed ISO DOB ascending, then source row key as a stable tie-break; missing/invalid values last. Source order remains the backward-compatible default (`source`). Source row keys and run record order remain unchanged. Verified PDF/CSV/page membership agrees after sorting and rebundling; rebundle uses the saved sorting setting.

## 6. Catalog and language exploration

Normalization and display labels solve different problems. A common catalog could reduce duplicate maintenance, but simply renaming `translations/` to `languages/` will not unify disease identity. Template has English labels too, and chart versus overdue wording differs within a language.

Explore stable disease IDs with aliases and labels indexed by language **and context** (`chart`, `notice/overdue`). Core owns the schema/resolution contract; Template owns editable disease/agent data and wording; Studio preserves and consumes authored files. Retain alias passthrough/unknown handling, detect ambiguous aliases and duplicated canonical/alias label keys, and provide an explicit migration path from existing files and agent mappings. Keep catalog work separate from the small reference fixes. Adding languages beyond en/fr also requires changes to native template identity checks, shared localization and Studio; moving files alone does not add language support.

## 7. Large HTML reports: later, with a measurable target

The reported ~110 MB HTML is plausible: existing Core evidence documents ~97 MB HTML / ~177 MB JSON for a different 5,000-notice workload. Current reports render full effective checks, technical JSON and repeated help/action text for every row. Adaptive checkpoints already reduce repeated writes; they do not shrink the final view.

First measure bytes by section, report-generation time, peak memory, browser open/search/expand time and DOM size. Prototype shared help text and lossless repeated-detail encoding with an accessible readable fallback. Preserve one authoritative run record, safe escaping/paths, every finding and artifact link, offline local-file use and no-JavaScript access. Simply collapsing `<details>` does not reduce bytes or DOM size. Additional files, lazy loading or report segmentation require an explicit offline/recovery contract decision. Do not remove passing evidence by default: a previous compact-detail experiment was not adopted because it lost explanations and measurements. Set a size/responsiveness target after measuring this workload.

## 8. Profile a real run: low priority

Use the actual release executable, project, fonts, assignments and configuration in an approved local workspace. Do not rebuild or change workload inside the timing interval. First analyze existing `run.json` stage timings and finding totals; rerun only when more detail is needed.

On Linux, wrap the normal command with `/usr/bin/time -v -o /private/path/process-time.txt` and retain its exit status. On other platforms use an equivalent process wall/CPU/peak-memory tool. Keep exact command arguments, binary/resource hashes, worker counts, CPU/RAM limits, storage type and report/artifact sizes locally. Existing `timings.total_seconds` stops before final report publication and process exit; external elapsed is authoritative for complete command time. Render spans can include overlapping encryption; do not add worker spans as elapsed-time shares.

If broad timings leave the cause unclear, add an opt-in native profile for preparation, compile/export, report build/JSON/HTML writes and bundle merge. Record per-stage counts and latency distributions without client values. Use a separate instrumented run; repeat uninstrumented comparisons with the same workload and alternate order before claiming a speedup. No encryption was requested in the reported run, so encrypted synthetic benchmarks are not directly comparable. Studio's browser-preview benchmark answers a separate question.

Done means the next real run can explain the observed 384.5 seconds by measured work and resource pressure, with correct artifact/routing counts. A single elapsed value is not a regression or capacity measurement.

## Delivery sequence and verification

1. F0 is complete. Start R1 in Template, verify the resource package/sample, then update Studio's Template pin. No engine change is needed for the reference data.
2. Complete R2a's contract fixture patch first. Then implement R2b in Core, update Template's library/notices and remove YAML resources, and adopt matching pins/validators/examples in Studio. Treat the three-repo handoff as one v2.0 acceptance milestone; do not leave broken intermediate pins for consumers.
3. G1 is a separate Core change with group/membership/routing tests. It can run alongside R2; include it explicitly before S1 sorting. Coordinate Template guidance and Studio pins only if adopted engine behavior changes.
4. W1 aggregates structured URL findings and counts. W2 first freezes its CLI/report/persistence/revoke contract, then implements run-scoped acknowledgment. Neither gates R1/R2/G1.
5. S1 ordering, D1 disease-catalog exploration, H1 report-size experiments and PR1 real-run profiling remain separate. Do not expand their scope while implementing the earlier milestones.

Core owns malformed-input, shared schemas/helpers, policy, PDF and routing tests. Template owns reference data, wording/layout and packaging. Studio owns example generation, deferred/current finding presentation, authoring preservation and downloaded native handoffs. Use fictional fixtures. Verify English/French normal, warning, review and unrenderable outcomes, stable source-row identity, expected actual bundle membership, and rebundle using saved observations. Run each repo's stated checks; a pin bump also needs a fresh build and selected browser/native tests. Avoid repeating the entire Core validation suite in consumers.

Execution readiness is per work item: R1 adoption and W1 have concrete outcomes; G1/S1 are verified in Core; R2a is a concrete prerequisite task for R2b; W2 and the later experiments need their specified design/measurement outputs first. Schema names/enums and the maintained-notice predicate/replacement table are R2a outputs, not hidden decisions for three implementers to make separately.

## Core implementation checklist

Core owns native preparation, shared schemas/helpers, policy, PDFs, grouping and saved-run reports. Template owns authored configuration/reference data; Studio consumes pinned resources and native commands. Follow the milestone order and shared decisions above. F0 is delivered; unchecked work remains planned.

### Source evidence and scope

| Area | Evidence | Consequence |
| --- | --- | --- |
| Coverage | [input.rs](src/input.rs), `prepare` | Missing diseases trigger `ensure!` and abort preparation; extra/unmapped coverage already produces a row finding |
| Notice metadata | [input.rs](src/input.rs), `Version` and catalog lookup | Catalog supplies coarse eligibility only; it has no coverage basis and will be removed |
| Pipeline boundary | [pipeline.rs](src/pipeline.rs), `run_with_progress` | Preparation must finish before policy validation and rendering; total timing excludes the final report write |
| Policy | [policy.rs](src/policy.rs), `changes`, `resolve`, `apply` | Only schema-marked adjustable render codes, global or exact-row selectors, with reasons; observed checks retained |
| URL findings | [findings.typ](resources/typst/src/findings.typ), `report` | Destinations deduplicated inside a notice; one aggregate result per URL code, no structured issue identity across rows |
| Empty displayed agents | [overdue.typ](resources/typst/src/overdue.typ), `overdue-agents` | Filters display list after preparation and records presence, not a nonempty-list finding |
| Routing/grouping | [bundles.rs](src/bundles.rs), `bundle_with_progress` | Readable failed originals go to review; blank school/board IDs coalesce; source-order members; configurable filenames are already delivered |
| Reporting | [report.rs](src/report.rs), `finding`, `entry_details`, `write` | Full escaped check JSON and explanatory text repeated per row; one JSON record and HTML view |

### F0: filenames complete

Filename settings, supported fields, safe normalization/collisions, original/protected paths, PDF/CSV stems and `rebundle --filenames` are implemented and tested. [Configuration](docs/user_guide/configuration.md#filename-templates) owns the current contract. Retain that behavior; this is not pending work.

### R2a: freeze the shared requirements contract

- [ ] Use the shared plan's R2a evaluator split: Core prepares trusted coverage measurements; the shared Typst helper evaluates notice-local requirements for native and browser; Core validates evidence and applies policy. Do not implement a second JS/Rust content-rule evaluator.
- [ ] Write the shared schema/fixture patch before production changes: declaration fields/enums, version changes, exactly-one placed declaration, source identity and required finding cardinality, conditional/no-records branches, mandatory missing/invalid evidence failures, and expected eligibility/coverage/display statuses.
- [ ] Define a per-entry deferred-check list outside observed `checks` for `prepare`; document it for Studio generation/UI. Define the completed valid/invalid-declaration branches above, including `blocked_checks` for checks that cannot be evaluated. Placeholder findings must not masquerade as completed observations, and no unresolved requirement may route as ready.
- [ ] Make requirements/cardinality errors mandatory structured findings within an otherwise usable report, retaining readable originals/previews. Distinguish them from corrupt report/identity evidence (`render.evidence_failed`), whose claimed findings are rejected while rendered artifacts are retained independently. Include missing/duplicate/malformed declaration and wrong-row-identity fixture cases with native/browser expected outcomes.
- [ ] Include the explicit maintained-notice predicate/replacement table with Template. Eligibility mismatches default to structured failure; preserve existing affirmative/ISPA semantics. Keep new check codes non-adjustable initially.

Done means Template and Studio can implement against the same executable contract cases without choosing different fields, defaults or evaluators. This is the first R2 task; R2b depends on it.

### R2b: implement notice-local requirements and forecast coverage

Agreed direction for the prerelease v2.0 breaking release: requirements belong beside notice wording, using a shared helper and validated compiled metadata. Remove `notice_versions.yaml` and its reader outright, with no legacy fallback, compatibility mode or deprecation period.

- [ ] Implement the R2a shared helper/report contract for eligibility and explicit coverage basis. Use normal compilation/metadata extraction, with no source parsing or extra discovery compile. Validate declaration cardinality and mandatory final check presence in the existing report/source boundary, preserving the R2a structured-failure/artifact-retention outcomes.
- [ ] Keep Core responsible for prepared facts and missing/extra/unmapped coverage measurements. Remove the missing-coverage preparation abort and provide the measurements to the shared helper. It emits the agreed findings: missing coverage fails for agent-based notices and warns for disease-based notices; explicit neutral requirements are inapplicable. Core validates those results as part of compiled evidence.
- [ ] Implement the R2a deferred-list output for preparation and resolve render-dependent observations before applying policy. Missing/invalid final evidence is a mandatory failure even when no diseases are missing.
- [ ] Delete catalog loading, `Catalog`/`Version` parsing and catalog-only checks such as `assignment.check_unavailable`. Notice-local requirements become the sole contract. Missing/malformed/contradictory metadata produces explicit evidence/requirements failures; obsolete YAML is never consulted for defaults or a fallback.
- [ ] Emit structured warnings/failures so readable failed originals reach review bundles and other rows continue. Retain assertions for conditions where a PDF must not be produced. Unrenderable rows remain report-only.
- [ ] Preserve declared requirements and observations in the run's compiled evidence. Rebundling uses saved results/policy without recompiling or silently changing the original requirements.
- [ ] Keep display exclusions separate from source coverage and assignment eligibility. Preserve upstream assessment rather than deriving clinical status or switching the selected notice automatically.
- [ ] Audit neighboring preparation exits incrementally, distinguishing expected row problems from shared configuration, manifest identity and storage failures.
- [ ] Remove the YAML catalog from Core fixtures and references in configuration, authoring, preparation and finding/review guides. Update setup/readiness assumptions, report contracts and tests together with Template/Studio adoption. Describe this as the v2.0 contract, without a legacy path.

Acceptance cases: a mixed cohort with one agent mismatch completes other rows and retains that PDF for review; a disease notice warns for the same mismatch; structured eligibility failure retains a readable PDF while a deliberate assertion yields report-only; valid local requirements run without YAML; an obsolete/contradictory YAML file cannot influence results; missing/malformed/contradictory local metadata fails visibly without fallback; conditional declarations match placed content; preparation explains deferred checks; saved-run rebundling preserves requirements/observations. Update fixtures and cover both languages/source-row identity at the appropriate owning boundary. No legacy catalog acceptance tests or compatibility fixtures are needed.

### R2b: empty agent-display evidence

- [ ] In the placed shared component, record source/displayed counts and exclusions after exact-name deduplication/filtering.
- [ ] Emit a content failure when an agent recommendation list becomes empty under exclusions. Define intentional no-records replacements and authored alternatives so those cases are not mistaken for accidental empty content.
- [ ] Keep the PDF available for review, and preserve all facts and client membership. A disease notice with no agent component is unaffected.
- [ ] Extend report schema, native validation and shared render-contract fixtures; refresh resources through the normal downstream pin process.

Test zero/one/all excluded agents, duplicates, TIg, flu/COVID, no-records replacements, absent components and mixed normal/review bundles. Template owns the final wording/layout cases.

### W1/W2: warning aggregation, then acknowledgment design

- [ ] Start with a run-level aggregate of code/status/structured subject, affected rows and occurrence counts. Diagnose the reported 5,836 warning rows before attributing them to one code. Keep compiler diagnostics separate.
- [ ] Extend URL evidence with structured destinations/sets. `content.multiple_links` identifies a set; malformed/non-HTTPS checks identify individual destinations. Do not parse messages to build keys.
- [ ] W2 first defines the native operator action, revoke action, lock-protected persistence/audit and report refresh as described in the shared plan. Then implement acknowledgment once per exact issue in a saved run, persisted across rebundle attempts. Preserve all observed/effective findings and show acknowledged versus outstanding attention counts. Acknowledgment alone changes no severity, routing or exit status.
- [ ] Scope issue identity by code, check/resource definition and exact destination or destination set. Store fingerprints for indexing, protected evidence for inspection, reason and time. Preserve meaningful URL path/query/fragment changes. A new run or new destination requires new review.
- [ ] Keep personalized QR values out of aggregate labels/shared logs. Do not remove query values to merge personalized URLs. Defer authored-link identities and cross-run allowlists until their trust/migration contract is designed.
- [ ] Reconcile [AGENTS.md](AGENTS.md) with the selected behavior if needed. It currently prohibits warning-waiver machinery, but acknowledgment that preserves findings/routing need not be a waiver. The user’s request takes precedence; updating guidance is not a permission gate for this investigation.
- [ ] Inventory preparation/render/artifact/delivery rules in an explicit mandatory/adjustable registry before extending policy beyond render checks. Reuse observed/effective history and exact-row reasons. Decide separately whether coverage can be downgraded for one row; do not quietly make it adjustable.
- [ ] Preserve mandatory evidence/identity, unusable-original, encryption and file-operation failures. Holds remain exclusion from both bundle routes; release does not mean acceptance.

Acceptance cases: one static bad link across many rows is one review subject with every row traceable; a second link and a changed link-set remain outstanding; acknowledgment survives rebundle, not a new run; changed resources invalidate matching; broad code disable cannot masquerade as per-link acceptance; forged/stale identities and unknown policy codes are rejected; no new disclosure in summary labels. Keep old saved runs readable when acknowledgment fields are absent.

### G1: group identity; S1: optional ordering afterward

- [x] Fix blank-ID grouping. Namespace ID versus fallback-name keys; include board scope in a missing-school-ID fallback. Emit findings for fallback and contradictory identity. Entirely unknown school identity does not merge into a normal catch-all school bundle.
- [ ] Review upstream ID export with its owner; this is separate from the completed native safeguard.
- [x] Use the shared G1 outcomes: name fallback warns; no usable identity fails each row into a separate review group; conflicting normalized names under one ID fail affected rows and stay apart; different IDs never merge solely because their names match. Apply to configured grouping dimensions, with no fuzzy matching. Keep structured grouping identity distinct from filename labels.
- [x] Preserve the existing filename-template resolver and fallback diagnostics. Group identity stays separate from filename display values; mixed/missing group fields trigger explicit fallback diagnostics. Collision handling disambiguates all configured grouping dimensions even when the pattern omits them.
- [x] Add validated `bundling.sort_by`, defaulting to `source`. Opt-in `last_name_dob` uses normalized last name, parsed ISO DOB ascending, source row key tie-break; absent/invalid values last. Case and repeated whitespace normalize with Unicode NFC, preserving accents. Sort before chunking and preserve source record order/keys.
- [x] Retain effective grouping/naming/order settings in the saved record. Rebundle uses saved sorting; old originals and attempts remain available without mutating source identities.
- [x] Verify artifact links, CSV page ranges and actual PDF/member order. Delivery disposition comes from the record, not a filename prefix. All 68 release tests, formatting and release build passed.

Acceptance cases: different blank-ID schools remain separate; unknown school identity cannot silently send as one group; conflicting IDs/names are visible; slug collisions/accents/long/reserved names are safe; chunks numbered consistently; same group under different routes/dimensions cannot overwrite; equal/missing names or DOBs sort stably; PDF/CSV/member/page order agree; old saved runs and repeated rebundle attempts work. Inspect representative bundles outside the test harness.

### Later: catalog, report size and real-run profiling

- [ ] Explore a disease catalog schema with stable IDs, aliases and per-language/per-context labels. Core owns validation/resolution; Template owns data and wording. Keep current formats supported through an explicit migration, detect ambiguous aliases and avoid mixing label strings with IDs. Language expansion needs more than a folder rename.
- [ ] Measure report section sizes, memory and browser responsiveness before optimizing. Reuse explanatory text and consider lossless sharing of repeated details while preserving every check, safe escaping, local-file/no-JavaScript access, artifact links and partial-run recovery. Do not reintroduce lossy passing-detail removal as a default. Segmented/lazy reports require a contract decision.
- [ ] Profile the real release command externally through process exit, with wall/CPU/peak RSS, explicit workers and local resource fingerprints. Existing record timings separate preparation/render/delivery but exclude the final report write. Keep profiler overhead out of throughput comparisons; worker spans overlap. Add opt-in granular spans only if broad timing does not answer the question.

Use [existing performance evidence](docs/developer_guide/performance_experiments.md) and [measurement guidance](docs/developer_guide/testing.md#measure-the-complete-command). The reported unencrypted 384.5-second run is one observation; reproduce its workload before comparing it with synthetic encrypted benchmarks.

### Verification and handoff

For implementation, run focused Rust unit/CLI/render-contract checks, then `cargo fmt --all --check`, `cargo test --release --locked`, `cargo build --release --locked` and documentation checks as applicable. Use fictional fixtures; verify independent row processing, evidence, actual artifacts and saved-run compatibility rather than duplicating presentation tests here.

F0 is complete. Execute R2a before R2b; G1 and W1 are independent. Land each shared contract before its consumer settings, and verify the coordinated v2.0 handoff. Template then updates its Core revision and complete exported library, tests English/French presentation and packages resources. Studio updates matching Core/Template pins together, regenerates validators/examples, and verifies the downloaded project against the intended standalone executable. No consumer should edit installed Core resources.
