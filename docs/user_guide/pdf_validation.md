# PDF checks and review

Each run saves its authoritative evidence in `run.json` and publishes a matching pair of CSV files. Open the `records.csv` and `findings.csv` paths printed by the terminal in a spreadsheet and inspect representative notices before sending them.

`records.csv` has one row per readable source record. Filter `severity` to find errors or warnings, `evaluation_state` to find incomplete checks, and `route` to see ready, review, withheld, report-only and undecided records. Use `row_key` to join a record to its findings. Original and protected paths and inclusive bundle page ranges identify available PDFs; paths are relative to the run folder. A held record retains its original but is excluded from bundles. Ready means eligible under the effective rules; check bundle status and path to see whether an artifact was produced.

`findings.csv` contains actionable checks, compiler warnings and operational failures. Filter by code or effective status, then join by `row_key`. The observed status records the original check; the effective status and policy reason show any authorized rule change. Code counts in the terminal overlap: one source row may have more than one finding. Compiler diagnostics and run or attempt errors are reported separately. Passing and inapplicable checks remain in `run.json` rather than filling the spreadsheet.

Import client IDs and other identifiers as text to preserve leading zeros. CSV cannot force spreadsheet programs to use text. The exports prefix an apostrophe to external text that could be interpreted as a spreadsheet formula, including after leading whitespace or control characters; `run.json` retains the exact values. The files use UTF-8, standard CSV quoting and CRLF line endings.

A warning can be eligible for sending. A failed check or mandatory check that was not performed prevents normal delivery; a readable original goes to a review PDF, while a record without a usable original is report-only. A completed run can contain failures and returns a nonzero exit status. The run retains original PDFs and, when requested, separate protected copies. Link checks validate address formats; they do not test whether websites respond. For explanations of individual codes, see the [finding code reference](findings.md).

## CSV fields and types

Both CSVs use export schema 1 and carry `run_id`, integer `record_revision` and the active `bundle_attempt` (empty before a successful attempt). A failed later attempt is identified separately on its finding. `row_key` joins the files; `source_record` is the 1-based data-record ordinal, including multiline CSV records. IDs are text and may repeat. Paths are relative to the run root. Empty cells indicate unavailable values; page counts and inclusive ranges are positive integers when present.

`records.csv` columns, in order:

```text
run_id,record_revision,bundle_attempt,row_key,source_record,client_id,name,school,notice_variant,language,severity,evaluation_state,route,hold_reason,original_status,original_path,original_pages,protected_status,protected_path,bundle_status,bundle_path,bundle_start_page,bundle_end_page
```

Severity is one of `error`, `warning`, `clear` or `pending`; evaluation is `complete`, `pending` or `blocked`. Artifact statuses use `completed`, `failed`, `pending`, `not_requested` or `excluded`. For example, a held warning has severity `warning`, route `withheld`, and bundle status `excluded`; an invalid source row may have severity `error` and route `report_only` with no PDF path. A still-running row may be `pending`; a warning already observed takes precedence while evaluation remains pending.

If a run stops before a row is evaluated, its evaluation and unattempted original remain `pending`, while its severity becomes `error` because required work is unfinished. The run finding explains the interruption. Source or original failures exclude protection that could not be attempted; an attempted protection failure remains `failed`. A completed protected copy remains available even if its original later becomes unusable. Requested bundling that has not started remains `pending`; completed notice checks do not make unfinished delivery clear. Bundle page ranges appear only for completed bundle membership.

`findings.csv` columns, in order:

```text
run_id,record_revision,bundle_attempt,scope,attempt_number,row_key,client_id,finding_key,origin,code,observed_status,effective_status,disabled,policy_reason,component,page,message,issue_ids,acknowledged_issue_ids
```

Scope is `row`, `run` or `attempt`; only row findings have a row key. Origin is `check`, `compiler` or `artifact`. Observed and effective check statuses use `pass`, `warn`, `fail`, `not_run` or `not_applicable`, and `disabled` is a boolean. `issue_ids` and `acknowledged_issue_ids` are JSON arrays; an empty array is `[]`. One check can identify several subjects. A warning disabled by a rule remains visible with the original `warn`, effective `not_run`, `disabled` true and the rule reason. Compiler diagnostic blocks are separate findings. Ordinary passing checks remain in canonical evidence.

The terminal uses readable source records as its denominator, including held and failed records. Severity buckets are exclusive; code counts overlap. With zero readable records the percentages are `n/a`. Rounded percentages may not add to exactly 100 percent.

## Record review of a link warning

List distinct current URL issues and their full IDs, then record or revoke attention with a reason that does not contain client information:

```sh
immuknow warnings runs/example-run
immuknow acknowledge runs/example-run ISSUE_ID --reason "Reviewed destination"
immuknow acknowledge runs/example-run ISSUE_ID --reason "Review withdrawn" --revoke
```

An acknowledgment applies to the exact issue in that saved run, including later rebundles. A changed destination is a different issue. Acknowledgment records attention; it does not change severity, routing, exit status or PDFs. The warning command also identifies inactive acknowledgments. `findings.csv` carries issue IDs and acknowledged IDs for reviewable findings.

If the CSV pair is missing or stale, repair the output problem and run `immuknow warnings runs/example-run --refresh`. Refresh reads the last saved checkpoint, including a readable failed or running `.incomplete` run, and regenerates the pair without recompiling or replaying a review action. Earlier generations remain available as immutable snapshots. Unsupported saved-run schema versions require the matching older executable.

## What Core checks during a run

| Check | Purpose | When it runs |
| --- | --- | --- |
| Source data, assignments and required password facts | Catch missing, inconsistent or unusable inputs. | Production preparation. |
| Notice evidence, layout and delivery rules | Check the selected client, content, placement and page count; decide whether the notice can be sent. | Every production notice. |
| PDF creation and file operations | Require successful Typst export, a nonempty document, successful writes and publication. | Every production notice. |
| Encryption settings and bundle structure | Require the configured protection, a usable normalized password and consistent page counts. Parse source PDFs when needed to encrypt or combine them. | Every requested protected copy or bundle. |
| Saved-PDF reopening, password refusal/access and preserved content | Detect regressions in the pinned PDF libraries and Core's integration. | Automated round-trip tests and release acceptance checks. |

Core trusts successful calls to the pinned Typst exporter and PDF writer. It does not reopen every newly written PDF or authenticate every newly encrypted copy during production. Those library contracts do not establish that wording, client information or layout is correct; the notice checks and operator review still apply. Successful file operations also do not promise protection from later storage corruption or modification.

## Know which PDF you are sending

Originals are the source for both normal and review bundles. Encrypted PDFs are
separate per-person copies; bundles are **not encrypted** by enabling notice
encryption. If requested encryption fails, a readable original goes to review,
even if its other checks passed. Review the encryption outcome before using an
individual copy, and choose your approved delivery method for each artifact.

Bundles retain notice pages and links, but do not combine document-level tags,
outlines or catalog attachments. Forms are rejected. Keep the original or
individual encrypted document when document-level accessibility structure is
required. Inspect the actual delivery files as well as the originals.

## Rule settings and notice length

`validation.rules` configures supported adjustable rules for a run. Changes use `enabled`, `severity` (`warn` or `fail`), and a nonempty `reason`. Mandatory checks cannot be disabled or downgraded. Use `validation.clients` to change a rule for exactly one input row. The report keeps the observed results in `checks` and the results after applying rules, with reasons, in `effective_checks`. Warnings do not need separate acceptance for delivery. Optional `validation.notice_length` sets a required positive page count for sending; no pages are added to reach that count. See [configuration](configuration.md).

To record attention without changing rules, use [link warning review](#record-review-of-a-link-warning).

## Rebuild bundles

Use a saved run to create another set of PDFs:

```sh
immuknow rebundle ./runs/<run-id>
immuknow rebundle ./runs/<run-id> --withhold row-000001 --reason "Pending review"
immuknow rebundle ./runs/<run-id> --release row-000001
```

Use `--policy policy.json` to apply a rules file and `--bundle-workers 4` to set the number of workers assembling PDFs. A held notice is excluded from both the PDFs for sending and the review PDFs. Releasing a hold leaves its checks in force. Each attempt records outcomes and creates a new numbered bundle directory. Review the current CSV pair and the selected bundle paths before sending notices. A failed later attempt retains the previous active decisions and bundles; its error appears separately.

To change only the next bundle attempt's names, supply `--filenames filenames.json`:

```json
{
  "bundle": {"template": "{school}_{notice_variant}_{bundle_number}"},
  "review_bundle": {"template": "review_{school}_{notice_variant}_{bundle_number}"}
}
```

```sh
immuknow rebundle ./runs/<run-id> --filenames filenames.json
```

The file replaces bundle/review filename settings; omit `review_bundle` for the
automatic review prefix, or use `{}` to restore legacy bundle names. Individual
settings are rejected here because saved originals and protected copies retain
their paths. Previous bundle attempts remain. The run records the effective
filename settings, resolved paths and any fallback warnings for the new attempt.
