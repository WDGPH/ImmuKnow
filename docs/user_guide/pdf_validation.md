# PDF checks and review

Each run records preparation, rendering and delivery findings in `run.json`, with a readable `report.html`. Inspect the report and representative notices before delivery. Typst components record layout and content findings for the notice actually rendered.

Warnings are eligible for delivery by default. A failed check blocks delivery of that notice; when its original PDF is readable, the notice is included in a separate review bundle. Independent notices can continue. A run with failures exits nonzero; warnings alone do not cause a nonzero exit.

The numbered `bundles-0001/` directory contains `bundle-*.pdf` for deliverable notices, `review-*.pdf` for review notices, and a matching CSV beside each PDF to associate its page ranges and findings with source rows. The run also retains original PDFs and, if configured, separate encrypted copies. Read the report for actual outcomes and paths; do not infer success from a file's presence alone.

## Rule settings and notice length

`validation.rules` configures supported adjustable rules for a run. Changes use `enabled`, `severity` (`warn` or `fail`), and a nonempty `reason`. Mandatory checks cannot be disabled or downgraded. Use `validation.clients` for a bounded override that selects exactly one source row. Observations remain in `checks`; the applied results and reasons are recorded in `effective_checks`. Warning acceptance is unnecessary because warnings are eligible for delivery by default. An optional `validation.notice_length` specifies a fixed positive page count for delivery; no pages are added to reach that count. See [configuration](configuration.md).

## Rebuild bundles

Use a saved run to create another delivery attempt:

```sh
immuknow rebundle ./runs/<run-id>
immuknow rebundle ./runs/<run-id> --withhold row-000001 --reason "Pending review"
immuknow rebundle ./runs/<run-id> --release row-000001
```

Use `--policy policy.json` for a policy supplied to the delivery attempt and `--bundle-workers 4` to set bundling parallelism. Withholding keeps a notice out of delivery; releasing a hold leaves its checks in force. Each attempt records outcomes and creates a new numbered bundle directory. Review the new report and matching file before distributing notices.
