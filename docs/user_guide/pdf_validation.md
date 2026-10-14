# PDF checks, review and rebundling

Open a run's `report.html` to inspect its source rows, selected notices, findings
and actual output results. `run.json` is the authoritative record. Findings do
not disappear when a delivery choice changes.

Python checks the actual original PDF's readability, page count, hash and
labelled client ID. Typst supplies component checks and measured layout evidence
from the content placed in the notice. A readable PDF is retained when checking
fails, with a blocking evidence failure. Quality warnings preserve useful
PDFs; missing templates and failed compilation cannot produce a selected notice.
There is no default fixed page count.

## Delivery and review

For each readable original, the shared evaluator in
`immuknow/validation_policy.py` applies these decisions in order:

1. Failed original checks select review. Mandatory identity, readability and
   evidence checks cannot be accepted as warnings. Unknown or malformed check
   evidence fails the delivery attempt.
2. A row explicitly withheld by the operator stays in review.
3. Each unresolved warning selects review until individually accepted.
4. An otherwise eligible original enters delivery.

There are no blanket warning allowances or force-delivery destinations.
Encryption failures affect the separate encrypted copy; they never substitute
an unencrypted file for a requested encrypted output. Print bundles use originals.

Each attempt saves `evaluations` by immutable source row key in `run.json`,
including observations, resolved results and `warning_tokens`. Each token
identifies one warning occurrence, including when the same rule warns on two
pages. Inspect the original PDF and that evaluation, then copy the exact token:

```bash
immuknow-rebundle ./runs/<run-id> \
  --accept-warning <token-from-report> --reason "Reviewed signature continuation"
```

Repeat `--accept-warning` for each warning reviewed. A nonempty reason is
required. Decisions are retained in `warning_acceptances` with the run, source
row, original PDF hash, evidence hash, rule identity and acceptance time. A
changed PDF, source binding, resource, observation, warning set or rule definition
invalidates the affected acceptance. A stale token is refused, and an earlier
acceptance remains visible without releasing changed evidence. Unknown or
incomplete mandatory evidence requires renewed checking and a new run.

To replace the set of rows kept in review independently of findings, use
`--withhold row-000001` (repeat for additional rows). Use `--clear-withheld`
to clear that set. Omitting both retains it. These choices never accept warnings
or bypass failures. Source row keys work even when an external identifier is
absent; names are never used as selectors.

The report provides each rule code, message, location and measurements.

## Rule settings

These checks are enabled and warn by default. Each permits `enabled: false`
or `severity: fail`, for a run or an explicitly selected source row.

| Check | Rule code |
| --- | --- |
| Address fits the envelope window | `layout.address_outside_window` |
| Signature stays with preceding content | `layout.signature_page` |
| Privacy text stays on its expected page | `layout.privacy_page` |
| Section stays within its page boundary | `layout.section_pages` |
| History columns have enough width | `layout.history_width` |
| Title fits its line limit | `layout.header_title_lines` |
| Placed content has a translation | `content.translation_missing` |

Set rules in `parameters.yaml`. Every change needs a reason:

```yaml
validation:
  rules:
    layout.signature_page:
      severity: fail
      reason: Keep signatures on the letter page
  clients:
    - selector:
        scheme: panorama
        value: "0000000001"
      rules:
        layout.signature_page:
          severity: warn
          reason: This letter needs a longer signature block
```

Settings apply in order: defaults, run settings, then row settings. Each field
retains its source and reason. A row setting only replaces fields it supplies.
To select a row without an external identifier, use
`selector: {input_sha256: "<input hash from run.json>", row_key: row-000001}`.
Each selector must match exactly one source row. Unknown rules, unsupported
fields, invalid types and multiple selectors for the same row are refused.

Disabled checks appear as `not_run`, never as passed. Identity, row binding,
required evidence and PDF readability cannot be disabled or downgraded.
Other rules retain their recorded severity. Contact and link checks are not yet
available as controls. `immuknow/validation_policy.py` owns policy resolution
and mandatory protections. Render check definitions come from the shared
`templates/lib/immuknow/report-v2.json` schema in the package.

To change settings for a saved run, put the contents of the `validation` section
in a JSON file and run:

```bash
immuknow-rebundle ./runs/<run-id> --policy rules.json
```

This replaces the saved settings; omitted settings return to defaults. An empty
object (`{}`) restores all defaults. Omitting `--policy` retains the saved settings.
Every attempt saves its rule definitions, resolved settings and results.
Rule changes invalidate affected warning acceptances. Recheck the report before
accepting warnings again. Changing enabled state or severity reuses retained
findings; measurement limits are authored in the templates and require a new run.

## Bundle contents

Delivery bundles contain unchanged original notice pages. They retain grouping
by size, school or board. Missing grouping identifiers produce a visible
`Unknown` group and a warning, rather than dropping the notice.

Review bundles form one group, split by the configured client count. Each client
appears once, even with several warnings. A review sheet immediately precedes
each notice and includes its client ID, source row key, selected template, all
findings, useful measurements and the individual warning tokens and rebundle instructions.
Sheets may span several pages; findings are never truncated to fit one page.

Every copied review notice page has a small red `REVIEW` mark in an added outer
band. Its original content keeps the same physical size and is neither covered
nor scaled. Originals remain unchanged. The report records separate review-sheet
and notice page ranges, as well as the full span of each client's placement.
These ranges come from the assembled PDFs.
Before replacing the active set, ImmuKnow opens every written bundle and compares
each page with its selected source page, including its content and resources.
Missing, duplicated, changed or reordered pages fail the attempt even when the
total page count is unchanged.

### Fixed notice length

When delivery needs a fixed number of PDF pages per notice, set an explicit count:

```yaml
validation:
  notice_length:
    enabled: true
    count: 2
    unit: pages
```

The count applies to every notice in each delivery bundle. It counts PDF pages,
including existing blank pages; no blank pages are added. It does not count
physical sheets, depend on printer settings, or include review sheets. The rule
is disabled by default and requires bundling to be enabled. It has no per-client
exception or warning setting.

Each written delivery batch records the expected and actual counts in `run.json`.
A mismatch fails the attempt and preserves the previous bundle set. Accepting a
signature or other layout warning cannot waive it. A held notice remains listed
in review; it is not silently removed from the accounting. Change this setting
for a saved run through `--policy`, just like the other validation settings.

### Encrypted copies

Individual encryption is optional and separate from bundles. Copies use AES-256,
revision 6, with a 256-bit key. The package includes the required encryption
backend. The written settings, nonempty password access and page count are
checked before publishing; `run.json` records the verified method. Passwords use
normalized saved facts. Missing referenced facts, including an unknown birth
date for the default compact birth-date password, fail encryption instead of
creating an empty password. Independent clients continue. Successful encrypted
copies are verified and saved under `encrypted/`; originals remain available for
review and rebundling. Password settings and expanded passwords are not saved.
The tests also open encrypted copies with MuPDF and compare their rendered pages
with the originals. Browser checks open English and French copies in Chromium’s
PDF viewer, including an accented password. The required recipient readers and
versions still need acceptance testing.

## Rebundle a saved run

To reevaluate and rebuild using already recorded acceptances:

```bash
immuknow-rebundle ./runs/<run-id>
```

Rebundling reads the saved record and original PDFs, checks every original hash
and page count, verifies retained payload bindings and resource hashes, and assembles a complete replacement set. It uses the run's
available system fonts and frozen timestamp for review sheets and marks. Source CSV
and authored template directories can be moved or removed. Notices are not
recompiled, facts are not prepared again, and encryption is not rerun.

Each attempt records the application code and data format files it uses, along
with the Python and pypdf versions and saved resources. For review
pages, it also records the review templates, compiler file and reported version.
File hashes identify the exact copies; earlier attempt records stay unchanged.
Unsupported saved data or compiler versions are refused before
delivery, including when no review pages are needed.

A notice moved from review to delivery comes from its original PDF. Its old
review copy is replaced with the active set; no stamp-erasure operation is used.
Warnings and earlier delivery attempts remain in `run.json`.

Only one process can change a run at a time. Rebundling locks the run before
reading its record and keeps it locked through recovery and replacement. A
second attempt stops with “This run is in use”; unrelated runs can proceed.
New runs use the same protection through their final report write. The operating
system releases the lock when a process exits, including after an interruption.
Do not delete `.run.lock` to bypass a busy run.

Invalid choices, missing or changed originals, and failed assembly leave the
previous committed bundle set and memberships active. Interrupted replacement
is detected through the saved attempt status and the fixed `bundles.next` and
`bundles.previous` directories. The next invocation restores the previous set
before beginning a new attempt, or removes the backup when JSON already records
a completed replacement. There is no separate transaction manifest.

The command's exit status describes the current rebundling attempt. A successful
new attempt returns 0 even when earlier failures remain in the run's audit
history. Unsupported run formats are refused; only format version 2 is supported.
Originals, facts and reports contain client information and belong in sensitive
run storage outside Git.
