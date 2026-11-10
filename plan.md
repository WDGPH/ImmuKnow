# v2 plan: usable run reports and faster styled QR codes

This is the shared execution plan for Core, [Template](../ImmuKnow-Template/plan.md) and [Studio](../ImmuKnow-Studio/plan.md). **Phase 1 is in progress; Template and Studio adoption are pending.** The integer QR grid and finder bounds are implemented with focused release tests; reporting implementation and integrated acceptance remain in progress.

The operator should finish a run, understand its severity totals in the terminal, open two manageable spreadsheets, and find the corresponding PDFs. The implementation replaces the large HTML report and per-bundle CSVs with run-wide CSV exports, retains a trustworthy saved record for review and rebundling, and applies two measured QR optimizations. Report usability is the primary product improvement; QR throughput is a separate, bounded improvement.

This is a prerelease breaking v2 release. Existing helper signatures, boolean grids, saved-report layouts and HTML are not compatibility requirements. Update maintained callers and generated consumers together. Do not add legacy loaders, adapters, format switches or duplicate output paths without an identified supported consumer. Existing `AGENTS.md` instructions about an escaped HTML view and tests asserting the old output must be deliberately updated during implementation; the requested CSV-first design supersedes them.

## Baseline and evidence

Start from the current branches, retaining completed behavior:

| Repository | Current baseline | Responsibility |
| --- | --- | --- |
| Core | Runtime `16792decc1e4fb405f63d2780ed87d5f46dba37c`; execution baseline `c95127b` | Shared components/contracts, native processing, saved state and reports |
| Template | `91c5b1cf5e573d8c8f234d71252ea65bfbe6d9fb`, pinning Core above | Authored notices, settings, references, examples and packaged project instructions |
| Studio | `4c4c98d2f57e0042c9fc8349c274eb64a663c9fc`, pinning that pair | Browser authoring/preview, generated resources, project import/export and native handoff |

The supplied local evidence is `../performance-summary.md`, `../performance-metrics.json`, `../compilation-profile-summary.md` and `../compilation-profile-metrics.json`. These measured **Core `78b8d9b8672f14afa0b1223b72c8fa0e9903c082` with its saved project snapshot**, not current Core. Read those artifacts locally; do not copy private inputs, raw profiles or metrics into these repositories. The old plan's PR1 profiling deferral is superseded by this completed evidence. H1's earlier HTML deduplication prototype is historical, not the implementation direction.

- The full measured command created 5,838 originals / 11,704 pages in 390.52 seconds through exit, with about 3.48 GiB native peak RSS. It used English notices, one styled QR per notice, two compile workers, encryption off and 75 normal / 2 review bundles. All rows had effective warnings; 189 also had failed checks. Counts of findings, warning-bearing rows and highest-severity rows differ.
- Its 152 MB HTML contained 4.53 million DOM nodes, took about 52 seconds to become usable and reached about 3.7 GiB sampled browser/driver RSS. Seventeen full report writes produced roughly 3.4 GB cumulatively. The saved-timer-to-exit gap includes other work; it is not a pure report timer.
- Finder bounds were equivalent at all 477,320 cells across the 40 standard QR dimensions (21–177). Later matched-build 200-row commands had median paired wall reduction 7.25% (4.64–7.46%). Bulk integer-grid conversion had 11.16% (9.42–13.30%) in matched-build commands, and 7.08% wall / 7.18% CPU in the same-binary, two-worker driver. Tested PDFs, pages, checks and routes matched.
- These candidates were measured separately. Do not add percentages or promise the same gain on 5,838 rows. Combined behavior, current-source performance and alternate styling/languages still need acceptance checks.
- Lazy structural-grid construction showed a smaller 1.25% driver-wall improvement, without established complete-command benefit. History grouping was slower; path `.push` was slower; findings grouping was inconclusive. None is required implementation here.
- A resource-only edit failed to trigger a library rebuild in the isolated older checkout. **Current `build.rs` already emits `cargo:rerun-if-changed=resources`.** Reproduce and verify current behavior before proposing a fix; adding that same directive or touching a Rust file is not a solution.

## Decisions and shared contracts

### Operator workflow and output defaults

1. `run` and `rebundle` print source-row severity counts and percentages, separate delivery counts, a short code summary, run/attempt errors, and the exact paths to the current `records.csv` and `findings.csv` on stderr. Preserve the canonical `run.json` path on stdout and current progress modes for maintained scripts. `--progress off` continues to suppress human progress/summary output; failures still return nonzero.
2. `records.csv` has one row per readable source record, including failed preparation, no-PDF records and holds. Filter it by severity or delivery route; use its original/protected/bundle paths and inclusive bundle page ranges to locate output.
3. `findings.csv` contains actionable observations and their effective results, compiler diagnostics and operational failures. Filter by code, row key or effective severity. Ordinary passing/not-applicable checks stay in canonical evidence, without filling the spreadsheet with every successful measurement.
4. `warnings RUN`, `acknowledge RUN ISSUE_ID --reason ...`, revoke, holds/releases and policy rebundling remain native workflows. Acknowledgment records attention only; it changes neither severity, routing, PDFs nor exit status. `warnings RUN --refresh` regenerates both CSVs from canonical state, including a partial/failed run; it never compiles or creates bundles. Mutating acknowledgments still requires a completed, valid run.
5. Generate **no HTML report and no per-bundle CSV**. No optional HTML is planned: the measured pain comes from an unnecessary second detailed interface, and spreadsheets plus the existing native review commands cover this workflow. Keep bundle PDF naming, grouping and page membership. Remove CSV-stem assumptions from filename documentation and tests.

### Severity, denominator and routing

Use one small shared native summary/projection implementation for CLI and CSV. Do not introduce a generic reporting framework or a second policy engine.

| Concept | v2 rule |
| --- | --- |
| Denominator | Number of readable CSV data records assigned stable `row_key`s, including invalid/held/no-PDF rows; never PDF count, distinct client IDs or physical CSV lines. State the denominator. |
| Highest effective severity | Mutually exclusive `error`, `warning`, `clear`, `pending`, in that priority order. `error` includes effective failures, mandatory checks not performed, invalid evidence and failures of requested artifacts. `warning` includes effective warnings and raw compiler warnings. `clear` requires completed evaluation, successful required artifacts and no effective warning/error. Otherwise use `pending`. |
| Incomplete work | A running record may be `pending`; an error or warning already observed takes precedence. Include `evaluation_state` separately so warnings never disguise pending checks. On a terminated failed run, required unfinished work becomes a blocking outcome; do not invent passing results or copy a global error into every row. |
| Blocked versus disabled | Invalid requirements retain their mandatory failure and explicit dependent `blocked_checks`; they are errors, not pending or not-applicable. A policy-disabled adjustable check remains explicitly disabled with its reason and does not itself create an error. Deferred checks remain outside observations until resolved. |
| Percentages | `100 * bucket_count / source_record_count`, one decimal place. For zero readable records print counts and `n/a` percentages. Header-only/empty input retains existing input validation and returns any applicable run error; never divide by zero or fabricate rows. Rounded percentages need not sum exactly to 100. |
| Delivery | Separate `ready`, `review`, `withheld`, `report_only`, `undecided` routing counts. Holds do not erase severity. A readable failed original remains reviewable; no usable original remains report-only. Ready is eligibility, not proof a bundle exists or a warning-free record. |
| Artifact failures | Failed original/protected output raises that row to error. An initial bundle-write failure identifies affected planned members as delivery errors without claiming a completed bundle. A failed later rebundle leaves the previous active row decisions/membership intact and reports the failed attempt separately. |
| Per-code summary | Count distinct affected row keys once per code/effective severity, with the same denominator. A row can appear under several codes; label these counts as overlapping. Show compiler diagnostics in a separately labeled warning line. Show run/attempt findings separately without a record percentage. |

Default terminal code summary: all error codes, then at most ten warning codes ordered by affected-row count descending and code for ties; give the omitted-code count and CSV path. No raw personalized subjects, client names or full diagnostic messages in the terminal aggregate. `findings.csv` remains complete. A global setup or output failure must be visible even when there are no rows or all row checks passed. Exit status follows the actual run/attempt outcome, not whether acknowledgment is outstanding.

### CSV v1 contract

Publish headers, types and examples in Core's owning reporting guide and fictional fixtures at the start of Phase 1. These are the only two tabular exports. Both carry `run_id`, `record_revision` and `bundle_attempt` so detached files can be identified. `bundle_attempt` identifies the active successful delivery snapshot, or is empty before one exists; failed attempts are identified separately on their findings.

`records.csv` columns, in order:

```text
run_id,record_revision,bundle_attempt,row_key,source_record,client_id,name,school,
notice_variant,language,severity,evaluation_state,route,hold_reason,
original_status,original_path,original_pages,protected_status,protected_path,
bundle_status,bundle_path,bundle_start_page,bundle_end_page
```

- `source_record` is the 1-based CSV data-record ordinal, including quoted multiline records; `row_key` is the stable join/action key. Client IDs may repeat and are text. `name`/`school` use available source/prepared display values; missing facts remain blank. Preserve existing notice variant/language identity.
- `evaluation_state` is `complete`, `pending` or `blocked`; the blocked-check list/reasons live in JSON and relevant finding rows. Artifact statuses are explicit `completed`, `failed`, `pending`, `not_requested` or `excluded` as appropriate. A held record retains available originals/protected copies, but has excluded bundle status and no bundle path/range. Grouping off means `not_requested`, not a missing-bundle failure.
- Paths use `/`, are relative to the run root and are populated only for published usable artifacts. Page counts/ranges are positive integers when present, with 1-based inclusive bundle ranges. Missing values are empty cells, never `0`, guessed paths or literal `null`. PDF links are ordinary paths, not spreadsheet formulas.

`findings.csv` columns, in order:

```text
run_id,record_revision,bundle_attempt,scope,attempt_number,row_key,client_id,
finding_key,origin,code,observed_status,effective_status,disabled,policy_reason,
component,page,message,issue_ids,acknowledged_issue_ids
```

- `scope` is `row`, `run` or `attempt`; only row findings require `row_key`. `origin` is `check`, `compiler` or `artifact`. `attempt_number` identifies attempt-specific findings, including failed rebundles. `finding_key` identifies one saved occurrence within its scope, not merely its code; repeated page-level checks must not collapse.
- Include a check occurrence if either observed or effective status is `warn`/`fail`, or it is a mandatory unresolved/blocked outcome. Thus a warning disabled/downgraded by policy remains inspectable with both statuses and its reason. Exclude ordinary pass/not-applicable and still-pending checks from this actionable table; pending counts/state remain visible in records and CLI. Preserve underlying status vocabulary (`pass`, `warn`, `fail`, `not_run`, `not_applicable`) and explicit `disabled` boolean.
- Emit distinct artifact/global error observations where no existing finding explains the failure; do not count the same failure twice. Raw compiler warnings remain distinguishable. Until the compiler supplies structured diagnostics, emit one compiler-warning finding per nonempty saved diagnostic block, with its complete useful text; do not parse arbitrary text into invented codes or severities.
- `message` explains what needs review, including a small relevant actual/expected value when useful. Do not export arbitrary measurement maps, source payloads or one column for every check. Preserve exact subjects in canonical evidence; do not add a duplicate raw-URL column to this table.
- `issue_ids` and `acknowledged_issue_ids` are JSON arrays of full IDs, empty as `[]`. One check may have several subjects, so arrays avoid duplicating finding rows. The second is the acknowledged subset of the first. `warnings` continues to show outstanding, acknowledged and inactive reviews, and JSON retains full review history/reasons. Acknowledgments are not findings and need no artificial CSV rows.
- Write UTF-8 CSV with a header, standard quoting/CRLF and deterministic source-record/finding order. Test commas, quotes, embedded newlines and French characters. Use real integer/boolean formatting, finite numbers only, and no locale-dependent thousands separators. Document importing identifiers as text; CSV cannot force spreadsheet typing or preserve leading zeros after automatic numeric conversion.
- Protect exported untrusted text against spreadsheet formula interpretation, including leading whitespace/control characters followed by `=`, `+`, `-` or `@`: prefix an apostrophe in the CSV presentation where needed. Apply this to names, IDs, paths, messages, policy/hold reasons and other external text, not typed numeric cells. Document the presentation escape; canonical JSON retains exact values. Do not use `="..."` formulas to preserve IDs.

### Saved state, exports and recovery

Advance `run_schema_version` from 1 to **2**; add CSV export schema version **1**. Support the new run schema directly. Reject unsupported saved-run versions with an actionable message to use the matching old executable; do not rewrite existing runs or add migration infrastructure in this prerelease task. The application version string alone is not a provenance check.

Keep `run.json` as the one authoritative saved record, protected by the existing per-run OS lock and atomic replacement. Keep source rows, assignments, configured policy, source/resource/template identities, original/protected artifact outcomes/hashes, requirements, provenance, warning review history and delivery attempts. Rebundling must work without the original authored project and without recompilation/reinterpretation of the notice.

Reduce duplication deliberately:

- Save each observed check once, with a stable occurrence key. Store effective results as small keyed records containing status, disabled state and policy reason; resolve shared message, subjects and evidence through the observed check. Keep observed/effective distinctions explicit, including policy-disabled checks. Attempt-specific delivery observations/results belong to that attempt.
- Retain prepared facts once in each row's canonical notice, and a validated render-evidence projection referencing that row/fact digest. Do not retain another whole `render_report.notice`, another full copy of its checks, or a second routine `facts/*.json` output solely because the compiler used it. Preserve source CSV/resource snapshots and rendered identity/page count, components, requirements, QR destinations, required source/display evidence and useful failure evidence. Full compiled evidence is validated **before** this persistence projection. Do not replace full-fact provenance validation with an identity-only comparison.
- The persisted projection is explicitly a saved-evidence type, not a partially valid shared render envelope. Adapt Core/Template/Studio native test readers accordingly. Checks needed to authorize delivery, diagnose a failure, validate identity or manage an acknowledgment are never silently dropped to meet a size target.

Keep exports simple and consistent. `record_revision` identifies committed semantic state; attaching the matching export pointer does not increment it.

1. Retain adaptive canonical JSON checkpoints during processing; write them through a streaming serializer/atomic temporary file instead of building HTML and serialized JSON strings together. Do not create CSVs at every notice checkpoint. A checkpoint records its revision, stage, per-row pending state and `exports: null`.
2. At normal completion, controlled failure, successful rebundle, failed rebundle or acknowledgment/revocation, persist the new canonical revision first, with `exports: null`. This preserves work/review history even if presentation writing fails. For rebundling, publish all completed bundle PDFs before selecting the new active attempt; a bundle failure never selects that attempt.
3. Stream the two CSVs from that committed revision into a fresh `reports-NNNN.incomplete/` directory under the run. Close/flush both; rename the directory to `reports-NNNN/`; atomically update `run.json.exports` with its revision, CSV schema version, relative paths and file hashes. Hold the run lock throughout. Readers see either no current export or a complete matching pair. Do not overwrite old CSVs, create root-level copies/symlinks or claim two independent renames are a transaction.
4. Each successful delivery attempt retains its effective results, holds, routes, member/page mapping, filename policy and the export generation made for that attempt. Earlier attempt exports remain immutable. Acknowledgment/revocation creates a new report generation for the active attempt, without a new bundle attempt; prior snapshots remain available. A refresh with unchanged canonical state and valid exports can return their existing paths. Generate files only at the listed events, retain snapshots needed by delivery/review history, and add no garbage-collection subsystem in this task.
5. A failed rebundle appends its failure, requested settings/holds and affected planned members while preserving the previous active bundle set and row decisions. Its refreshed CSV includes the failed attempt finding and current active records. The CLI says the attempt failed and names the retained active attempt; it must not present retained files as newly produced output.
6. If export publication fails after canonical mutation, return a failure explaining that state was saved but CSVs are unavailable and provide `warnings RUN --refresh`. That command accepts readable running/failed `.incomplete` runs as well as completed runs, validates them under lock, and regenerates from the last checkpoint only. It does not replay an acknowledgment or hold action. A failed refresh leaves canonical facts/history unchanged and no current export pointer. Unselected staged/orphan directories are never treated as current outputs.
7. Preserve the outer run `.incomplete` convention. Rename a successfully finalized run only after its current export pair is selected. A finalization failure keeps the partial path discoverable, with saved state and a clear error. Abrupt termination can lose work since the last checkpoint, as today; refresh reports that checkpoint accurately and does not claim to resume compilation. Extend existing status/read guards accordingly.

### Purposeful render evidence and measurements

Advance shared render-report schema **3 → 4** for the measurement cleanup; prepared payload/preparation schemas remain at **2** because facts and deferred-check semantics do not change. Update the exported schema, native validator, shared Typst emitters, Core contract fixtures and Studio validators/types together. Do not accept both old/new render contracts through fallback code.

Keep the full compiled notice and strict native/browser full-fact comparison at the trust boundary. Preserve finite-number/page-bound checks and source/placed-component matching. The cleanup changes representation, not checks or clinical meaning:

| Data | v2 treatment |
| --- | --- |
| Eligibility/coverage, source/display/exclusion/replacement evidence, required-check presence, exact link subjects | Retain and validate, even for passing checks when needed to establish correctness. Coverage measurements remain available to the existing source-equality validation. |
| Address/client geometry, envelope window geometry, history/section page locations | Keep once in top-level component `measurements` in the shared compiled report: Studio uses these for overlays and source targets. Move `viewer.ts` away from looking for a passing check's duplicate geometry; retain `preview-sources.ts` consumers. |
| Routine successful numeric margins, title-height comparisons, width comparisons and other repeated check geometry | Remove redundant per-check measurement copies. Preserve result/code/page/component and the authoritative component evidence that has a real validation/editor use. Measurements used only to evaluate a passing check remain local to compilation. |
| Failed/warning numeric comparisons | Retain concise meaningful actual/expected/overflow values when they explain correction; put the actionable part in the message and retain necessary structured detail in canonical evidence. Avoid an undifferentiated technical dump. |
| Native saved component evidence | Preserve semantic evidence, identity and page locations. Do not persist editor-only rectangles and successful diagnostic arithmetic merely because they were present in the compiled envelope; native projection and shared browser envelope have distinct purposes. |

Make a short field-by-field retention table beside the schema fixtures when implementing this change; resolve every removal against its actual validator/editor/acknowledgment consumer. This is a bounded source inventory, not a new configurable evidence system. No diagnostic flag or plugin framework is required.

### QR implementation contract

`resources/typst/lib.typ` exposes `qr-code`; the boolean grid from `src/qr-encode.typ` is internal. Choose the natural integer representation already supplied by the plugin:

- Keep the existing WASM matrix protocol: one width byte followed by row-major 0/1 bytes. Implement `array(encoded.slice(1)).chunks(size)` in the shared Typst encoder and use explicit `dark == 1` in the styled renderer. Keep only the maintained integer-grid helper/callers; do not wrap it in a boolean compatibility layer. Verify dimensions and byte values through contract tests.
- Replace the finder closure scan with the exact coordinate predicate for the three 7×7 finder regions. Retain existing drawing command order, colors, geometry, four-module quiet zone and hyperlink evidence. Keep the existing SVG/run fast paths for default styling and non-RGB color support.
- Keep correction levels, Unicode/ECI destinations, module/corner styles, logo masks/padding and structural-marker protection. There is no reason to rebuild/change QR WASM for these two Typst-only changes; preserve its pinned source/artifact/license verification.
- Optional follow-on: one isolated lazy-reserved-grid probe for square/no-logo styling, after the two changes pass. Adopt only with exact-output style/logo coverage and repeatable complete-command benefit beyond control variation. Stop after one controlled comparison if the effect is negligible; do not let this delay the required handoff.
- Colored run merging, geometry changes, allocator replacement, engine/layout forks, cache redesign, four-worker scheduling and history/findings rewrites are out of this implementation. If a later project intentionally changes geometry, it needs decoding/appearance validation rather than pretending PDF hashes should match.

## Execution: finish Core, then Template, then Studio

Sol coordinates the implementation. Most coding belongs to Terra subagents working in parallel where files and responsibilities are independent. Within Core, the reporting Terra owns native reporting/CLI/bundles/review modules, render-report v4 emitters/schema/validation and their focused tests. The QR Terra owns `resources/typst/src/qr-encode.typ`, `qr.typ`, `qr-style.typ` and `tests/qr.rs`. Sol owns build reproducibility, integration, shared-contract decisions and the migration ledger; assign any additional work explicitly and serialize overlapping fixture/documentation edits. Request an occasional Astra review at the consequential contract/recovery design and integrated acceptance points, not for every patch. No subagent needs to reproduce another lane's tests.

Complete and iterate on Core before moving to Template, then make the appropriate Studio changes. These are three repository phases, not a sequence of lockstep consumer releases. Internal Core iterations do not require repeated Template/Studio pin changes. Keep a short migration ledger as Core evolves so the later consumer work is mechanical. Select exact commits only at the final repository handoffs.

### Phase 1 — all Core work

**Start with fixtures and build reproducibility.**

- [ ] Add the CSV headers/type examples, summary edge cases, saved-schema v2 shape and report-schema v4 retention table to owning guides/fictional fixtures. Include no-PDF, held, override, duplicate client ID, compiler warning, blocked/pending, zero-row and failed-attempt examples. Use typed summary/export records; do not spread ad hoc `Value` fallbacks across writers.
- [ ] Audit `src/report.rs`, `pipeline.rs`, `bundles.rs`, `terminal.rs`, `warnings.rs`, `warning_review.rs`, `policy.rs`, `main.rs`, `validation.rs`, Typst measurement emitters and exported schemas. Record exact maintained consumers in Template tests and Studio's `types.ts`, `render-contract.ts`, `viewer.ts`, `preview-sources.ts` and `tests/check_typst_project.py`.
- [x] Verify isolated current-source resource rebuilds with `scripts/check-resource-rebuild.sh`: baseline, resource-only edit, addition and removal all refresh exported bytes and identity under ordinary cached release builds. Existing directory tracking works; no build.rs change is needed.

Use these fixtures to coordinate the two Core lanes; iterate within Core as needed. Current resource builds must be trustworthy before QR measurements are accepted.

**Terra reporting lane — CSV-first reporting and saved evidence.**

- [ ] Implement report-schema v4 emission/validation and the saved projection. Update all direct readers of the changed saved shape; preserve full-fact validation and strict review-history gates.
- [ ] Replace eager HTML generation with streaming CSV export and canonical checkpoints/publication described above. Remove `src/report.js`, `src/report.css`, HTML construction, bundle CSV writes/fields and obsolete tests. Keep PDF assembly/page membership checks; HTML escaping tests become meaningful CSV text/quoting tests where relevant.
- [ ] Use one summary implementation for terminal and exports, including artifact failures, distinct-row code counts, raw diagnostics and separate run/attempt findings. Reconcile effective status/route after policy changes and holds. Print actual selected CSV paths rather than a nonexistent `report.html` path.
- [ ] Update run, rebundle, warnings/refresh, acknowledge/revoke and sample-check integration. Adapt errors so final reporting failure cannot hide the original processing error or lose an already saved review action.
- [ ] Update `AGENTS.md`, README, architecture/CLI/report-review/finding/configuration/ecosystem/testing guides and links. Explain spreadsheet filtering, text IDs, relative PDF paths, effective versus observed results, attempted versus active bundles, refresh and unsupported old saved schemas. Do not leave instructions to open HTML or locate a matching per-bundle CSV.

Focused acceptance: one mixed fictional journey covers clear/warning/error rows, a held warning, failed original, failed protected copy, failed initial bundle write, failed later rebundle, overridden/disabled warning, repeated code on multiple pages, compiler diagnostics and global failure. Assert exact CSV memberships/counts/statuses, no invented artifacts, no per-bundle CSV/HTML, and independently verify real PDF page ranges. Test all-failed rows, malformed input with recoverable records, no readable rows, non-ASCII/quoted/formula-like text and stable row joins. Fault-inject export writes/rename and canonical publication at the boundaries above; verify locks, previous attempt preservation, refresh and acknowledgment/revoke idempotent recovery without recompilation. These boundary tests replace old representation snapshots rather than duplicating them.

**Terra QR lane — the two measured changes.**

- [x] Implement finder bounds and integer bulk conversion; remove obsolete scalar conversion and boolean-only helper tests. The focused QR release suite passes; combined current-source performance and representative notice checks remain below.
- [x] Retain independent decoder tests in `tests/qr.rs` for requested correction levels, UTF-8/ECI and boundary sizes through version 40. Add the all-standard-dimension finder predicate oracle and integer-grid shape/value checks.
- [ ] Exercise the real styled renderer across square/dots/rounded/separated modules, square/rounded corners, distinct finder/alignment colors, default SVG/run paths and logo/mask accept/reject boundaries. Inspect rendered representative English/French notices, including long content; use focused raster/decode checks where necessary to verify actual styled output rather than only raw matrices.

Exit: exact PDF bytes/page counts/rendered findings for the unchanged-geometry comparisons, strict source binding, unchanged readable-failure routing and no weakened logo protection. Compare QR-only arms with the same reporting contract; report-schema v4 intentionally differs from v3 and is compared semantically across that boundary.

**Sol integration — focused correctness and performance acceptance.**

Run this acceptance work once for the integrated Core candidate; repeat affected checks only after a change, failure or unresolved concern. Benchmark pair counts below are bounded starting targets, not statistical guarantees.

- [ ] Build release candidates outside timing, record source/binary/resource/font identities, use identical filesystem/root controls and fixed timestamps/inputs/assignments/settings/workers/eviction. Keep profilers, builds and browser tests outside throughput comparisons. Preserve artifact integrity checks.
- [ ] Use a fixed fictional 1,000+ row workload representing both variants, realistic history lengths and QR payload sizes, with colored finders/alignment deliberately exercising the styled-grid path. Measure current baseline and combined behavior; compare reporting-only against combined to isolate the QR effect. Add a QR-only arm only if attribution needs it. Reserve the roughly 5,800-row paired confirmation for the integrated candidate and its matched control. Include a separate default-SVG/non-RGB-run control so bypassing the grid is not mistaken for a failed optimization or a claimed gain. Keep a separate correctness cohort for rare styles/languages/failures. Do not use repeated cached identical notices as the throughput workload.
- [ ] For the combined QR comparison, start with four balanced alternating complete-command pairs on the 1,000+ row cohort and one paired full-size confirmation. Extend only if noise, inconsistent results or a new concern requires it; a single full-size confirmation supports only a limited full-size claim. Record each pair, median paired wall/CPU deltas, ranges, peak RSS, output size/bytes written and launch-to-exit time. Control-versus-control rebuild variation bounds interpretation; noisy results are inconclusive, not an automatic pass from a positive median. A local private full-workload replay is optional if available and authorized, never a dependency requiring private data in Git.
- [ ] Accept the required QR changes only when correct and repeatably beneficial in complete-command wall and CPU beyond the measured control variation. No fixed 7%/11% promise; report actual combined measurements. Require no material peak-RSS regression (investigate a reproducible >5% increase) and no OOM. If source/build controls fail, stop performance claims and fix that path first.
- [ ] Measure reporting separately: final CSV export wall/CPU/RSS, canonical checkpoint serialization/writes, total native wall, both CSV sizes and failed-run refresh. On the same 5,800-row fixture target the combined CSVs at no more than 25% of the old HTML plus bundle-CSV bytes, export/refresh under 2 seconds on the measured machine, and no full presentation writes at intermediate checkpoints. Treat these as proposed targets, not achieved results; if a target misses, report the measured reason without dropping evidence. Verify opening/filtering/joining the CSVs in a representative spreadsheet application, including leading-zero ID import and formula-safe text; never claim measured spreadsheet usability from file size alone.
- [ ] Run `cargo fmt --all --check`, `cargo test --release --locked`, `cargo build --release --locked`, documentation checks and `typst-plugins/qr/build.sh --check` as appropriate. Validate extracted executable/resource exports outside the checkout. Record measured limits and actual tests; retain only sanitized aggregate results/fictional harnesses in review artifacts.

Exit: one exact verified Core commit is suitable for consumer pins.

### Phase 2 — all Template migration

After Core is coherent and verified, follow [Template's plan](../ImmuKnow-Template/plan.md). Update its `core-revision.txt` to the exact verified Core commit, refresh the whole generated library, update its native journey/readers and packaged operator instructions, and verify both languages, styling and package contents. Retain all authored settings/reference fixes. Produce one verified Template commit pinning that exact Core commit; generated library bytes remain untracked.

### Phase 3 — appropriate Studio migration

After the Template migration is verified, follow [Studio's plan](../ImmuKnow-Studio/plan.md). Update Core pin plus Template dependency/lock together; install the exact clean native source through `scripts/native_core.py` and verify its fingerprint. Regenerate shared assets/validators/examples. Update report-schema types, measurement consumers and downloaded-project acceptance readers; keep the browser compiler unchanged unless a proven engine requirement emerges. Verify browser findings/overlays/source targets and the downloaded native CSV/rebundle journey together.

Keep this migration ledger current during Core implementation; consumer mutation waits for its repository phase. Record final names and one fixture/example per changed boundary, not a development diary:

| Core change | Template migration | Studio migration |
| --- | --- | --- |
| CSV-first outputs selected by `exports.records.path` / `exports.findings.path` | `scripts/run.py` output and README; `tests/test_sample.py` replaces per-bundle CSV assumptions; `tests/conftest.py` retains canonical source rows | Download instructions; `tests/check_typst_project.py` and native journey |
| Saved-run v2 `saved_evidence` and keyed effective results | `scripts/check.py` finding summary; native sample/presentation readers and mock records in `tests/test_check.py` | `tests/check_typst_project.py` native/browser parity reader and artifact membership assertions |
| Render-report v4: successful `layout.*` checks omit `measurements`; component geometry remains authoritative | Maintained notice/render checks; [retention table](tests/fixtures/render-evidence.md) and shared fixtures | Types/generated validators; move `viewer.ts` envelope guide to `summary.measurements.address`; retain `preview-sources.ts` |
| Integer grid and finder bounds | Complete shared-library refresh; representative styles/languages | Regenerated complete resources; styled preview/download checks |
| Final Core resource identity | Exact `core-revision.txt` and verified package | Matching Core pin, Template Git pin/lock and native fingerprint |

Consumer readers use `checks[].finding_key` for observed occurrences and join `effective_checks[]` by that key. Effective records contain only `finding_key`, `status`, `disabled` and `policy_reason`; messages, codes, subjects and semantic measurements belong to the observed check. `saved_evidence` replaces `render_report`, with `saved_evidence_version: 1` and `facts_sha256` binding the row's one canonical `notice`; it contains no duplicate notice/check list and is not a complete compiled-report envelope. Read `qr_urls`, requirements, components and retained semantic/page evidence there. Separate `facts/*.json` files no longer exist. Core's CLI, grouping and warning-review tests demonstrate the new joins, selected CSV paths and immutable attempt/review exports.

Regeneration at the consumer phases: Template runs `immuknow project sync --replace` and `immuknow project check --sample`; Studio updates its lock with `uv lock --upgrade-package immuknow-template-resources`, installs through `uv run --locked python -m scripts.native_core install`, and runs `npm run prepare:assets` / `npm run generate:contracts` before the fresh site build. Generated resources/validators stay untracked.

**Pin rule:** Core implementation → Template adoption/verification → Studio adoption/verification. Do not pin uncommitted changes, branch names or the old profiling revision. Every handoff records exact revisions and actual checks. If integration requires adopting a different Core revision, refresh matching consumer pins and affected checks. The existing verified pair remains valid while unrelated Core iteration continues. Publishing revisions/builds is a separate action; local pins are not available to fresh external installs until published. No push, merge or deployment is requested by this plan.

## Completed behavior and intentionally deferred work

Retain the completed F0 filename defaults/customization, R1 Meningococcal/TIg fixes, R2 notice-local requirements with no `notice_versions.yaml` fallback, R3 independent-row failure isolation, G1 safe school/board grouping, S1 optional last-name/DOB ordering, W1 exact structured warning subjects and W2 run-scoped acknowledgment. Preserve source-row identity, observed versus effective policy, readable failures in review, no-PDF report-only rows, original/protected separation, AES-256 revision 6 protection, unique attempt directories and OS locks. Do not rerun the earlier feature design merely because report tests change.

Disease identity/alias/language catalog migration remains deferred. Its useful exploration remains: stable IDs must be separate from labels; labels need language and chart/overdue contexts; `Other` is a chart category, not an invented disease; normalization, history, ISPA comparisons, aliases and fallback labels need explicit migration fixtures. Moving translation directories alone solves none of that. Upstream school identifier/export review remains external. Neither item gates this reporting/QR work.

No unresolved product question requires user approval. Implementation assumptions are explicit above: local spreadsheets are the detailed review interface, exact compiled provenance is validated before compact persistence, and only the two demonstrated QR changes are mandatory. Any measured limitation should narrow a performance claim rather than silently expand this scope.
