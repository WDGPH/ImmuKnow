# PDF checks, review and rebundling

Open a run's `report.html` to inspect its source rows, selected notices, findings
and actual output results. `run.json` is the authoritative record. Findings do
not disappear when a delivery choice changes.

Python checks the actual original PDF's readability, page count, hash and
labelled client ID. Typst supplies component checks and measured layout evidence
from the content placed in the notice. A readable PDF is retained when checking
fails, with an evidence-unavailable warning. Quality warnings preserve useful
PDFs; missing templates and failed compilation cannot produce a selected notice.
There are no configurable PDF rule severities, hidden text measurements or
fixed two-page requirement.

## Delivery and review

For each readable original, routing uses these rules in order:

1. An explicit client destination wins.
2. Otherwise, any warning not allowed for delivery selects review.
3. Otherwise, select delivery.

The run's `overrides.json` starts with empty allowances and client choices:

```json
{
  "allow_delivery_warnings": [],
  "clients": {}
}
```

Allow a named warning type or choose a destination for a particular client:

```json
{
  "allow_delivery_warnings": ["data.school_unmatched"],
  "clients": {
    "1234567890": "delivery",
    "1234567891": "review"
  }
}
```

Client choices require unique ten-digit source IDs. Unknown IDs, invalid
choices, duplicate JSON keys and warning-code typos fail the attempt before
replacement. A documented warning code can be allowed even when absent in this
run; a custom authored warning code can be allowed when it appears in the run.
An allowance changes routing and preserves the warning. A client override also
preserves failed checks and unsuccessful encryption outcomes. It cannot invent
a PDF or resolve ambiguous source identity.

Common warning codes include:

| Code | Finding |
|---|---|
| `data.school_unmatched` | School has no reference match |
| `source.address_incomplete` | Source mailing address is incomplete |
| `source.age_unknown` | Birth or delivery date cannot establish age |
| `source.history_unparsed` | Unusable source history fragments were retained |
| `assignment.eligibility_conflict` | Facts conflict with the explicitly selected notice |
| `assignment.check_unavailable` | No applicability check is registered for that template |
| `content.translation_missing` | A required label uses its fallback text |
| `layout.address_outside_window` | Measured address bounds exceed the envelope safe area |
| `layout.section_pages` | A section continues beyond its intended page |
| `output.evidence_unavailable` | A readable original's checks could not be completed |
| `delivery.encryption_failed` | Requested individual encryption failed |
| `delivery.group_unknown` | The selected delivery grouping lacks an identifier |

The report gives the precise codes, messages and measurements for every finding.
Other supported source-field, history, header, signature, compiler and output
warnings can be selected by their documented check code in the report.

## Bundle contents

Delivery bundles contain unchanged original notice pages. They retain grouping
by size, school or board. Missing grouping identifiers produce a visible
`Unknown` group and a warning, rather than dropping the notice.

Review bundles form one group, split by the configured client count. Each client
appears once, even with several warnings. A review sheet immediately precedes
each notice and includes its client ID, source row key, selected template, all
findings, useful measurements and the exact override/rebundle instructions.
Sheets may span several pages; findings are never truncated to fit one page.

Every copied review notice page has a small red `REVIEW` mark in an added outer
band. Its original content keeps the same physical size and is neither covered
nor scaled. Originals remain unchanged. The report records separate review-sheet
and notice page ranges, as well as the full span of each client's placement.
These ranges come from the assembled PDFs.

Individual encryption is optional and separate from bundles. Passwords use
normalized saved facts. Missing referenced facts, including an unknown birth
date for the default compact birth-date password, fail encryption instead of
creating an empty password. Independent clients continue. Successful encrypted
copies are verified and saved under `encrypted/`; originals remain available for
review and rebundling. Password settings and expanded passwords are not saved.

## Rebundle a saved run

After reviewing findings, edit the override file and run:

```bash
immuknow-rebundle ./runs/<run-id> \
  --overrides ./runs/<run-id>/overrides.json
```

The override path is optional; the default is `overrides.json` inside that run.
From the saved run directory, use:

```bash
immuknow-rebundle . --overrides ./overrides.json
```

Rebundling reads the saved record and original PDFs, checks every original hash
and page count, and assembles a complete replacement set. It uses the run's
available system fonts and frozen timestamp for fixed review sheets and marks. Source CSV
and authored template directories can be moved or removed. Notices are not
recompiled, facts are not prepared again, and encryption is not rerun.

A notice moved from review to delivery comes from its original PDF. Its old
review copy is replaced with the active set; no stamp-erasure operation is used.
Warnings and earlier delivery attempts remain in `run.json`.

Invalid choices, missing or changed originals, and failed assembly leave the
previous committed bundle set and memberships active. Interrupted replacement
is detected through the saved attempt status and the fixed `bundles.next` and
`bundles.previous` directories. The next invocation restores the previous set
before beginning a new attempt, or removes the backup when JSON already records
a completed replacement. There is no separate transaction manifest.

The command's exit status describes the current rebundling attempt. A successful
new attempt returns 0 even when earlier failures remain in the run's audit
history. Unsupported run formats are refused; only format version 1 is supported.
Originals, facts and reports contain client information and belong in sensitive
run storage outside Git.
