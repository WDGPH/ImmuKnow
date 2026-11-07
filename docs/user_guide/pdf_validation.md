# PDF checks and review

Each run records input preparation, PDF creation and check results in `run.json`, with a readable `report.html`. Inspect the report and representative notices before sending them. Typst components record layout and content findings for the notice actually created.

Notices with warnings can be included in the PDFs for sending under the active rules. A failed check prevents that notice from entering the PDFs for sending. If its original PDF is readable, it goes into a separate review PDF. If no PDF was created or the original is unreadable, the notice appears in the report only. Other notices can still be processed. A run with failures exits with an error; warnings alone do not cause an error exit.

The numbered `bundles-0001/` directory contains `bundle-*.pdf` for notices ready to send and `review-*.pdf` for notices requiring review. A CSV beside each PDF connects its page ranges and findings to the input rows. The run also retains original PDFs and, if configured, separate encrypted copies. Read the report for actual outcomes and paths; do not infer success from a file's presence alone.

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

`validation.rules` configures supported adjustable rules for a run. Changes use `enabled`, `severity` (`warn` or `fail`), and a nonempty `reason`. Mandatory checks cannot be disabled or downgraded. Use `validation.clients` to change a rule for exactly one input row. The report keeps the observed results in `checks` and the results after applying rules, with reasons, in `effective_checks`. Warnings do not need separate acceptance. Optional `validation.notice_length` sets a required positive page count for sending; no pages are added to reach that count. See [configuration](configuration.md).

## Rebuild bundles

Use a saved run to create another set of PDFs:

```sh
immuknow rebundle ./runs/<run-id>
immuknow rebundle ./runs/<run-id> --withhold row-000001 --reason "Pending review"
immuknow rebundle ./runs/<run-id> --release row-000001
```

Use `--policy policy.json` to apply a rules file and `--bundle-workers 4` to set the number of workers assembling PDFs. A held notice is excluded from both the PDFs for sending and the review PDFs. Releasing a hold leaves its checks in force. Each attempt records outcomes and creates a new numbered bundle directory. Review the new report and matching CSV before sending notices.
