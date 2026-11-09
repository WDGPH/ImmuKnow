# PDF checks and review

Each run records input preparation, PDF creation and check results in `run.json`, with a readable `report.html`. Inspect the report and representative notices before sending them. Typst components record layout and content findings for the notice actually created.

The report starts with counts of source rows by delivery decision. Its warning summary groups repeated link warnings by exact destination or destination set, counts affected rows and occurrences, and links back to each source row. Summary labels omit destination values; the original findings retain their evidence. Other warnings are counted by check code, and notice creation messages are counted separately. The summary uses effective warnings, so a finding changed to failure or disabled by policy is not counted as a warning. Older saved runs without structured link subjects show those warnings by check code. These counts do not change delivery decisions. The warning-row count and filter also include notice creation messages. Warning counts overlap those decisions: a Ready row can still have warnings. Search names, client IDs, schools or finding text, and filter by decision or warnings. Each row shows its main finding; expand **Findings and files** for failures, warnings, next steps and PDF links. Passed, inapplicable and policy-disabled checks are under **Other checks**. Unperformed checks that were not disabled remain prominent because they block the normal bundle. Technical details retain check codes, measurements and any rule change with its original and effective result. Without JavaScript, all rows remain available and browser Find still works.

Ready means eligible under the effective rules, not proof that a bundle was produced. Check the actual bundle links and run errors. Counts describe source rows, not unique people or immunization outcomes. Link checks validate address formats; they do not test whether websites respond.

Notices with warnings can be included in the PDFs for sending under the active rules. A failed check, or a check that was not run and was not disabled, prevents that notice from entering the PDFs for sending. If its original PDF is readable, it goes into a separate review PDF. If no PDF was created or the original is unreadable, the notice appears in the report only. Other notices can still be processed. A run with failures exits with an error; warnings alone do not cause an error exit.

The numbered `bundles-0001/` directory contains PDFs for notices ready to send and separate review PDFs. Defaults are `bundle-*.pdf` and `review-*.pdf`; [filename templates](configuration.md#filename-templates) can customize them. A CSV beside each PDF connects its page ranges and findings to the input rows. The run also retains original PDFs and, if configured, separate encrypted copies. Read the report for actual outcomes and paths; do not infer success from a file's presence alone.

For explanations and investigation steps for individual codes, see the [finding code reference](findings.md).

## Record review of a link warning

List the current distinct URL issues and their full issue IDs from a completed
run. The report shows the same IDs and affected source rows. Then record or
revoke a review with a reason that does not contain client information:

```sh
immuknow warnings runs/example-run
immuknow acknowledge runs/example-run ISSUE_ID --reason "Reviewed destination"
immuknow acknowledge runs/example-run ISSUE_ID --reason "Review withdrawn" --revoke
```

An acknowledgment applies to that exact issue in that saved run, including
later rebundles. A changed destination or destination set is a different issue;
a new run starts with no acknowledgments. The report retains the review history
and shows current and inactive acknowledgments. Acknowledgment records attention:
it does not alter findings, severity, routing, exit status, PDFs or bundles.
Warnings without structured subjects, including older runs, remain visible by
check code but cannot be acknowledged as exact link issues.

If the run record was saved but the HTML view could not be refreshed, repair the
output problem and run `immuknow warnings runs/example-run --refresh`. This
regenerates the view without creating PDFs or changing the review history.

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

Use `--policy policy.json` to apply a rules file and `--bundle-workers 4` to set the number of workers assembling PDFs. A held notice is excluded from both the PDFs for sending and the review PDFs. Releasing a hold leaves its checks in force. Each attempt records outcomes and creates a new numbered bundle directory. Review the new report and matching CSV before sending notices.

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
