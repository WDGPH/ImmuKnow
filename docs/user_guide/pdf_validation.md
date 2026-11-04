# Notice validation, review and rebundling

Open a run's `report.html` to inspect its rows, findings and actual output
results. For runs of 1,000 or more rows, follow links to the notice pages; selected
notices, full source values and run details are in `run.json`. Some large run or
attempt check details are shortened in the HTML view. `run.json` is the
authoritative record. Findings do not disappear when a delivery choice changes.

Typst owns notice content and layout checks. Its report records findings from
the components placed in each notice. Python validates that report against the
prepared input and selected source row, then records the original PDF's
readability, page count and hash. The PDF page count must agree with the report.
A readable PDF is marked as needing review when required evidence is missing or
invalid. Quality warnings preserve useful PDFs; missing templates and failed
compilation cannot produce a selected notice. There is no default fixed page count.

Reports retain the notice data used for layout. It must match the prepared input,
and each placed personal-content helper must use that same data. This catches
changed facts even when row and client IDs are unchanged. That check happens
when the notice is produced. Later review uses the accepted findings. Python does not extract PDF text or independently check its link
destinations. Use the supplied helpers so the Typst report includes their checks.

The supplied link and QR helpers warn when a web link lacks HTTPS or a host, or
contains spaces, in Studio and native runs. They also warn when the notice has several different link
destinations, counting QR codes and ordinary links together. Repeated links to
the same destination count once. Several destinations may be intentional; review
the warning or change its rule setting. Email and phone details still need author
review. These checks do not contact websites or parse email addresses and phone
numbers.

QR destinations support accented characters and other Unicode text.

## Review status

Each readable original has an eligibility decision in `run.json`, also shown
alongside any exported findings. The shared evaluator applies these decisions in order:

1. Failed original checks require review. Mandatory source binding, readability and
   evidence checks cannot be accepted as warnings. Unknown or malformed check
   evidence fails the delivery attempt.
2. A row explicitly withheld by the operator stays in review.
3. Each unresolved warning requires review until individually accepted.
4. An otherwise eligible original is marked `delivery`.

`eligibility` is `review` or `delivery`; it records readiness, not physical
placement. All readable originals share one bundle set using the selected
grouping and size, including notices with failed checks or an operator hold.
Successful assembly does not mean every notice has been cleared. There is no
blanket warning acceptance or way to mark a failed original eligible.

Encryption failures affect the separate encrypted copy; they never substitute
an unencrypted file for a requested encrypted output. Bundles use originals.

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
row, individual warning, reason and acceptance time. A token also identifies
the warning's effective rule setting and the review policy version. Changing
that rule setting requires renewed acceptance; changing an unrelated rule or
adding an operator hold preserves the decision. A token from another run or
row is refused. Original PDFs and their findings remain unchanged: correct the
input or template and generate a new run when a notice needs changing.

To replace the set of rows kept in review independently of findings, use
`--withhold row-000001` (repeat for additional rows). Use `--clear-withheld`
to clear that set. Omitting both retains it. These choices record review state; they do not omit pages from bundles, accept
warnings or bypass failures. Source row keys work even when an external identifier is
absent; names are never used as selectors.

The report provides each rule code, message, location and measurements.

A history table's `content.history_mapping` error prevents delivery eligibility and cannot be
accepted as a warning or changed through rule settings. Correct the agent name
or reference mapping, or explicitly exclude it with `ignore-agents`, then generate
a new run. See [history options](phu_templates.md#component-choices-and-findings).

## Rule settings

These checks are enabled and warn by default. Each permits `enabled: false`
or `severity: fail`, for a run or an explicitly selected source row.

| Check | Rule code |
| --- | --- |
| Address fits the envelope window | `layout.address_outside_window` |
| An envelope window is specified for the address | `layout.envelope_window_missing` |
| Client details stay outside the envelope window | `layout.client_details_in_window` |
| Signature stays with preceding content | `layout.signature_page` |
| Privacy text stays on its expected page | `layout.privacy_page` |
| Section stays within its page boundary | `layout.section_pages` |
| History columns have enough width | `layout.history_width` |
| Title fits its line limit | `layout.header_title_lines` |
| Placed content has a translation | `content.translation_missing` |
| Link destinations use HTTPS, mailto or tel address formats | `content.link_destination` |
| Web links use HTTPS and include a host | `content.link_https` |
| Multiple link destinations have been reviewed | `content.multiple_links` |

The client-details check compares the supplied block's bounds with the window
on the first page, for both right and below placement. It does not check other
content placed elsewhere by the author.
If addresses are placed without any specified window, a separate warning is
recorded. Fit and overlap are not reported as passing for an unspecified window.

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
Remove settings for retired PDF text and link checks when the error names them;
Typst's content and layout rules now determine those findings.

Disabled checks appear as `not_run`, never as passed. Identity, row binding,
required evidence and PDF readability cannot be disabled or downgraded.
Other rules retain their recorded severity. `immuknow/validation_policy.py` owns
policy resolution
and mandatory protections. Render check definitions come from the shared
`typst/report-v2.json` schema in the package.

To change settings for a saved run, put the contents of the `validation` section
in a JSON file and run:

```bash
immuknow-rebundle ./runs/<run-id> --policy rules.json
```

This replaces the saved settings; omitted settings return to defaults. An empty
object (`{}`) restores all defaults. Omitting `--policy` retains the saved settings.
Every attempt saves its rule definitions, resolved settings and results.
Historical PDF text and link findings remain recorded but do not determine
current routing. Rule changes invalidate affected warning acceptances. Recheck the report before
accepting warnings again. Changing enabled state or severity reuses retained
findings; measurement limits are authored in the templates and require a new run.

## Bundle contents

ImmuKnow opens completed new bundles and checks their page counts. It records
which notices were copied and where their pages begin and end. Page copying is
covered by regression tests; routine runs do not compare every written page
with its source. A same-count page substitution would therefore not be detected
by this final check.

Every readable original appears once in the configured bundle set. Choose
[grouping](configuration.md#group-bundles) by school, board, notice language,
page count, or a combination, and set the maximum notices per bundle. Review
status does not change grouping. Each PDF contains unchanged original notice
pages, with no added marks or cover sheets. The report records actual notice
page ranges.

### Findings CSV

Each bundle PDF has a matching CSV with the same filename stem, for example
`board_001_example_001.pdf` and `board_001_example_001.csv`. Import that CSV into
a spreadsheet, keeping `client_id` as text to preserve leading zeroes. Each row
identifies a finding for a notice in that bundle, including the source row,
client ID, eligibility, notice page range, check code, `effective_status`,
message, measurements and warning acceptance details. A finding tied to an
original page also gives its corresponding `bundle_page`; unlocated findings
leave that page blank. Filter by row, status or check code to focus the review.

Accepted warnings remain visible. Use the exact `warning_token` with
`immuknow-rebundle --accept-warning` after reviewing the notice. Editing a CSV
does not change findings or eligibility. An operator-held notice with no
findings has a row explaining the hold, with blank check fields. A clean bundle
has a CSV containing only column headers. Rows without a usable original cannot
appear in a bundle CSV; their failures remain in `report.html` and `run.json`.
The latter remains the complete, authoritative record.

Each successful attempt has its own directory containing the PDFs and matching
CSVs. Earlier complete sets remain available when a later attempt fails. Text cells that could be interpreted
as spreadsheet formulas are prefixed with an apostrophe in the export;
original values remain unchanged in `run.json`. Treat CSVs as sensitive client
information, like the PDFs and HTML report.

### Fixed notice length

When delivery needs a fixed number of PDF pages per notice, set an explicit count:

```yaml
validation:
  notice_length:
    enabled: true
    count: 2
    unit: pages
```

The count applies to every notice in every bundle, including notices needing
review or held by the operator. It counts PDF pages, including existing blank
pages; no blank pages are added. It does not count
physical sheets or depend on printer settings. The rule is disabled by default and requires bundling to be enabled. It has no per-client
exception or warning setting.

Each written bundle records the expected and actual counts in `run.json`.
A mismatch fails the attempt and preserves the previous bundle set. Accepting a
signature or other layout warning cannot waive it. Holding a notice does not
remove it from the bundle or waive the page count. Change this setting for a saved run through `--policy`, just like the other validation settings.

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

Rebundling uses the saved findings, original PDFs and grouping settings to
produce a new PDF/CSV set. Source CSV and authored template directories can be
moved or removed. Typst, installed fonts and encryption passwords are not needed.
The CLI trusts its completed originals, facts, reports and resource snapshots;
manually changing these files is unsupported. Saved hashes identify the files
originally produced and are not repeatedly checked for outside edits.

Each attempt records the application code and data format files it uses, along
with the Python and pypdf versions, saved resources and output hashes.
Earlier attempt records stay unchanged.
Only supported run formats can be loaded. The compiler version used to create
a notice does not prevent copying its completed PDF pages.

Accepting warnings updates eligibility; bundle grouping still follows the saved
configuration. Warnings and earlier delivery attempts remain in `run.json`.

Only one process can change a run at a time. Rebundling locks the run before
reading its record and keeps it locked through the final save. A
second attempt stops with “This run is in use”; unrelated runs can proceed.
New runs use the same protection through their final report write. The operating
system releases the lock when a process exits, including after an interruption.
Do not delete `.run.lock` to bypass a busy run.

Each new set starts in `bundles/attempt-<number>-<id>.incomplete`. The suffix is
removed after the PDF/CSV set is written, and the run record then points to it.
A failed attempt leaves the previous published set active. Interrupted folders
are left alone; another attempt uses a new name. The report links the last
published set even when a later attempt fails. Only sets recorded as completed
in `run.json` are active outputs.

An initial run whose directory still ends in `.incomplete` cannot be rebundled.
Inspect its partial report, correct the cause and start a new run. Completed and
abandoned output directories can be managed as whole folders; there is no
automatic resumption or cleanup of interrupted attempts.

The command's exit status describes the current rebundling attempt. A successful
new attempt returns 0 even when earlier failures remain in the run's audit
history. Unsupported run formats are refused; only format version 2 is supported.
Originals, facts and reports contain client information and belong in sensitive
run storage outside Git.
