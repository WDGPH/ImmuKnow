# Plan: row findings, review workflow and bundles

Core work from the [shared investigation plan](../plan.md). Filename templating is implemented; the remaining sections are planned work. Template owns authored configuration/reference data, and Studio consumes pinned resources and native commands. Implement native changes here rather than patching either consumer.

## Evidence from the current code

| Area | Evidence | Consequence |
| --- | --- | --- |
| Coverage | [input.rs](src/input.rs), `prepare`, around 1034–1078 | Missing diseases trigger `ensure!` and abort preparation; extra/unmapped coverage already produces a row finding |
| Notice metadata | [input.rs](src/input.rs), `Version` around 99 and catalog lookup around 811 | Catalog supports kind/requires only and rejects unknown fields; assignment basis can be resolved before coverage |
| Pipeline boundary | [pipeline.rs](src/pipeline.rs), around 688–738 | Preparation must finish before policy validation and rendering; total timing excludes the final report write |
| Policy | [policy.rs](src/policy.rs), `changes`, `resolve`, `apply` | Only schema-marked adjustable render codes, global or exact-row selectors, with reasons; observed checks retained |
| URL findings | [findings.typ](resources/typst/src/findings.typ), around 46–73 | Destinations deduplicated inside a notice; one aggregate result per URL code, no structured issue identity across rows |
| Empty displayed agents | [overdue.typ](resources/typst/src/overdue.typ), `overdue-agents` | Filters display list after preparation and records presence, not a nonempty-list finding |
| Routing/grouping | [bundles.rs](src/bundles.rs), around 117–195 | Readable failed originals go to review; blank school/board IDs coalesce; source-order members; generic filenames |
| Reporting | [report.rs](src/report.rs), `finding`, `entry_details`, `write` | Full escaped check JSON and explanatory text repeated per row; one JSON record and HTML view |

## P0: configurable filename templates — highest usability priority

Use the same authoring approach as `encryption.password.template`: explicit supported `{field}` placeholders, escaped braces and early validation. The existing `PASSWORD_FIELDS`, `format_password` and `password` in [input.rs](src/input.rs), around 300–388, provide a small parser/value-resolution precedent. Share parsing only where useful; keep filename scopes/sanitization separate and preserve every password behavior.

- [x] Add project settings for individual, normal-bundle and optional review-bundle stem templates. The keys are `filenames.individual.template`, `filenames.bundle.template` and `filenames.review_bundle.template`; these are implemented configuration. Core appends `.pdf` / `.csv`. Example individual: `{last_name}_{first_name}_{client_id}_{notice_variant}`; batch: `{school}_{notice_variant}_{bundle_number}`.
- [x] Apply the individual pattern to originals and encrypted copies in their separate directories. Keep facts/evidence row-key based and preserve row identities. Optional review pattern defaults to a review-prefixed bundle pattern.
- [x] Document the individual allowlist: all existing password fact fields, plus `row_key`, `school_id`, `board_id`, `notice_variant`. Bundle allowlist: `school`, `school_id`, `board`, `board_id`, `language_code`, `notice_variant`, `bundle_number`, `route`. Bundle fact values must be identical across actual members; do not use an arbitrary first row. No arbitrary CSV fields, expressions or derived passwords.
- [x] Validate braces, unknown/out-of-scope fields and authored directory syntax before artifact generation. Keep plain placeholders/escaped braces initially; define `bundle_number` as a minimum two-digit ordinal within each group and route.
- [x] Normalize filename substitutions consistently across platforms. Handle Unicode/accents, whitespace, separators, reserved names, trailing dots/spaces and maximum length. Preserve meaningful field values while creating safe basenames.
- [x] Preallocate collision-safe paths deterministically before worker writes: duplicates, slug/case-insensitive collisions, omitted chunk placeholders and distinct groups with the same visible name must never overwrite. Use stable row/group suffixes. Missing/mixed referenced values produce an explicit filename warning and deterministic artifact fallback, rather than guessing or losing a readable PDF.
- [x] Replace hard-coded `originals/{row_key}.pdf` and `encrypted/{row_key}.pdf` paths in [pipeline.rs](src/pipeline.rs), and both independent bundle PDF/CSV stem constructions in [bundles.rs](src/bundles.rs). Resolve each path once; all consumers use it.
- [x] Retain legacy names when settings are absent. Save nonsecret filename settings/resolved paths in the existing run/attempt record. Update original/protected links, hashes, merge inputs, CSV companions and rebundle lookups to use recorded paths. Old runs stay readable; rebundle preserves original individual files and previous attempts while recording any new bundle naming policy.
- [x] Provide Template config/examples and downstream adoption guidance. This work must not wait for acceptance infrastructure, catalog redesign, report compaction or configurable sorting. School-group identity changes remain a separate P1 task; mixed filename fields safely fall back without changing grouping or routing.

Acceptance cases: names with spaces/accents/unsafe characters; every supported field in the correct scope; escaped/malformed braces and unknown fields; missing values and mixed bundle metadata; duplicate IDs/names and normalized/case collisions; chunk numbers past 99 and omitted number placeholders; original/protected copies remain distinct; review/normal names and PDF/CSV stems agree; report links/hashes and rebundle work with custom paths; password output/redaction unchanged; legacy configs/runs retain existing behavior. Use fictional data and inspect representative filenames and artifacts.

## P1: notice-local requirements and forecast coverage

Agreed direction for the prerelease v2.0 breaking release: requirements belong beside notice wording, using a shared helper and validated compiled metadata. Remove `notice_versions.yaml` and its reader outright, with no legacy fallback, compatibility mode or deprecation period.

- [ ] Add a shared notice-local helper/report contract for eligibility and explicit coverage basis. Extend the existing schemas, native validator and evidence fixtures. Use normal compilation and metadata extraction; avoid source parsing or an extra compilation/discovery pass.
- [ ] Keep Core responsible for prepared facts and missing/extra/unmapped coverage measurements. Remove the missing-coverage preparation abort; evaluate notice-dependent results after reading the actual compiled declaration. Missing coverage fails for agent-based notices and warns for disease-based notices; review other bases explicitly.
- [ ] Define preparation output for checks deferred until rendering. A preparation-only result must not claim notice requirements have already passed. Final unresolved requirements must be visible and conservatively handled.
- [ ] Delete catalog loading, `Catalog`/`Version` parsing and catalog-only checks such as `assignment.check_unavailable`. Notice-local requirements become the sole contract. Missing/malformed/contradictory metadata produces explicit evidence/requirements failures; obsolete YAML is never consulted for defaults or a fallback.
- [ ] Emit structured warnings/failures so readable failed originals reach review bundles and other rows continue. Retain assertions for conditions where a PDF must not be produced. Unrenderable rows remain report-only.
- [ ] Preserve declared requirements and observations in the run's compiled evidence. Rebundling uses saved results/policy without recompiling or silently changing the original requirements.
- [ ] Keep display exclusions separate from source coverage and assignment eligibility. Preserve upstream assessment rather than deriving clinical status or switching the selected notice automatically.
- [ ] Audit neighboring preparation exits incrementally, distinguishing expected row problems from shared configuration, manifest identity and storage failures.
- [ ] Remove the YAML catalog from Core fixtures and references in configuration, authoring, preparation and finding/review guides. Update setup/readiness assumptions, report contracts and tests together with Template/Studio adoption. Describe this as the v2.0 contract, without a legacy path.

Acceptance cases: a mixed cohort with one agent mismatch completes other rows and retains that PDF for review; a disease notice warns for the same mismatch; structured eligibility failure retains a readable PDF while a deliberate assertion yields report-only; valid local requirements run without YAML; an obsolete/contradictory YAML file cannot influence results; missing/malformed/contradictory local metadata fails visibly without fallback; conditional declarations match placed content; preparation explains deferred checks; saved-run rebundling preserves requirements/observations. Update fixtures and cover both languages/source-row identity at the appropriate owning boundary. No legacy catalog acceptance tests or compatibility fixtures are needed.

## P1: empty agent-display evidence

- [ ] In the placed shared component, record source/displayed counts and exclusions after exact-name deduplication/filtering.
- [ ] Emit a content failure when an agent recommendation list becomes empty under exclusions. Define intentional no-records replacements and authored alternatives so those cases are not mistaken for accidental empty content.
- [ ] Keep the PDF available for review, and preserve all facts and client membership. A disease notice with no agent component is unaffected.
- [ ] Extend report schema, native validation and shared render-contract fixtures; refresh resources through the normal downstream pin process.

Test zero/one/all excluded agents, duplicates, TIg, flu/COVID, no-records replacements, absent components and mixed normal/review bundles. Template owns the final wording/layout cases.

## P1: warning presentation, acknowledgment and policy boundaries

- [ ] Start with a run-level aggregate of code/status/structured subject, affected rows and occurrence counts. Diagnose the reported 5,836 warning rows before attributing them to one code. Keep compiler diagnostics separate.
- [ ] Extend URL evidence with structured destinations/sets. `content.multiple_links` identifies a set; malformed/non-HTTPS checks identify individual destinations. Do not parse messages to build keys.
- [ ] Prototype acknowledgment once per exact issue in a saved run, persisted across rebundle attempts. Preserve all observed/effective findings and show acknowledged versus outstanding attention counts. Acknowledgment alone changes no severity, routing or exit status.
- [ ] Scope issue identity by code, check/resource definition and exact destination or destination set. Store fingerprints for indexing, protected evidence for inspection, reason and time. Preserve meaningful URL path/query/fragment changes. A new run or new destination requires new review.
- [ ] Keep personalized QR values out of aggregate labels/shared logs. Do not remove query values to merge personalized URLs. Defer authored-link identities and cross-run allowlists until their trust/migration contract is designed.
- [ ] Reconcile [AGENTS.md](AGENTS.md) with the selected behavior if needed. It currently prohibits warning-waiver machinery, but acknowledgment that preserves findings/routing need not be a waiver. The user’s request takes precedence; updating guidance is not a permission gate for this investigation.
- [ ] Inventory preparation/render/artifact/delivery rules in an explicit mandatory/adjustable registry before extending policy beyond render checks. Reuse observed/effective history and exact-row reasons. Decide separately whether coverage can be downgraded for one row; do not quietly make it adjustable.
- [ ] Preserve mandatory evidence/identity, unusable-original, encryption and file-operation failures. Holds remain exclusion from both bundle routes; release does not mean acceptance.

Acceptance cases: one static bad link across many rows is one review subject with every row traceable; a second link and a changed link-set remain outstanding; acknowledgment survives rebundle, not a new run; changed resources invalidate matching; broad code disable cannot masquerade as per-link acceptance; forged/stale identities and unknown policy codes are rejected; no new disclosure in summary labels. Keep old saved runs readable when acknowledgment fields are absent.

## P1/P2: group identity and order (coordinate with P0 filename templates)

- [ ] Fix blank-ID grouping first. Namespace ID versus fallback-name keys; include board scope in a missing-school-ID fallback. Emit findings for fallback and contradictory identity. Entirely unknown school identity must not merge into a normal catch-all school bundle. Review upstream ID export as a separate source issue.
- [ ] Define structured group metadata so display labels do not become grouping identifiers. Resolve same-ID/different-name and same-name/different-ID cases explicitly.
- [ ] Supply validated group labels to the P0 filename-template resolver. Group identity stays separate from filename display values; mixed/missing group fields need explicit fallback diagnostics. Collision handling must disambiguate all configured grouping dimensions even when the pattern omits them.
- [ ] Add a validated within-group ordering option; keep source order as the default. Opt-in order: normalized last name, parsed ISO DOB ascending, source row key tie-break; absent/invalid values last. Choose deterministic case/accent rules. Sort before chunking and preserve source record order/keys.
- [ ] Update the existing delivery record/attempt handling to retain effective grouping/naming/order settings. Preserve old originals and attempts; decide how rebundle selects new settings without mutating source identities.
- [ ] Update artifact links, hashes, CSV page ranges and any documented filename assumptions. Delivery disposition comes from the record, not a filename prefix.

Acceptance cases: different blank-ID schools remain separate; unknown school identity cannot silently send as one group; conflicting IDs/names are visible; slug collisions/accents/long/reserved names are safe; chunks numbered consistently; same group under different routes/dimensions cannot overwrite; equal/missing names or DOBs sort stably; PDF/CSV/member/page order agree; old saved runs and repeated rebundle attempts work. Inspect representative bundles outside the test harness.

## Later: catalog, report size and real-run profiling

- [ ] Explore a disease catalog schema with stable IDs, aliases and per-language/per-context labels. Core owns validation/resolution; Template owns data and wording. Keep current formats supported through an explicit migration, detect ambiguous aliases and avoid mixing label strings with IDs. Language expansion needs more than a folder rename.
- [ ] Measure report section sizes, memory and browser responsiveness before optimizing. Reuse explanatory text and consider lossless sharing of repeated details while preserving every check, safe escaping, local-file/no-JavaScript access, artifact links and partial-run recovery. Do not reintroduce lossy passing-detail removal as a default. Segmented/lazy reports require a contract decision.
- [ ] Profile the real release command externally through process exit, with wall/CPU/peak RSS, explicit workers and local resource fingerprints. Existing record timings separate preparation/render/delivery but exclude the final report write. Keep profiler overhead out of throughput comparisons; worker spans overlap. Add opt-in granular spans only if broad timing does not answer the question.

Use [existing performance evidence](docs/developer_guide/performance_experiments.md) and [measurement guidance](docs/developer_guide/testing.md#measure-the-complete-command). The reported unencrypted 384.5-second run is one observation; reproduce its workload before comparing it with synthetic encrypted benchmarks.

## Verification and handoff

For implementation, run focused Rust unit/CLI/render-contract checks, then `cargo fmt --all --check`, `cargo test --release --locked`, `cargo build --release --locked` and documentation checks as applicable. Use fictional fixtures; verify independent row processing, evidence, actual artifacts and saved-run compatibility rather than duplicating presentation tests here.

Prioritize filename configuration/path support first, without waiting for unrelated contracts. Land each shared reader/contract before its consumer settings. Template then updates its Core revision and complete exported library, tests English/French presentation and packages resources. Studio updates matching Core/Template pins together, regenerates validators/examples, and verifies the downloaded project against the intended standalone executable. No consumer should edit installed Core resources.
