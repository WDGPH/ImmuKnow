# Finding code reference

Use the code in a report's **Technical details** to find the check below. The message, page and measurements describe the particular observation; inspect the actual notice and source information before acting. Checks describe supplied data and document output, not a clinical assessment or immunization status. The upstream system assesses status.

A check may pass, warn, fail, be not applicable, or be not run. Default severity depends on the observation. Supported rules can change the effective severity or disable a check, with a recorded reason; mandatory checks cannot be disabled or downgraded. The report retains observed and effective results. An effective failure blocks the normal bundle; warnings can be included under the active rules. A `not_run` result blocks delivery unless the check was disabled by an effective rule. See [PDF checks and review](pdf_validation.md) and [configuration](configuration.md).

The entries below explain issue outcomes; many of the same checks also produce a passing result. A component-absence result is informational and not applicable. Raw compiler messages may also produce a warning even when no separate finding code is present; the report includes those rows in its warning filter.

## Source and reference

### `source.client_id_missing` {#source-client-id-missing}

The source client ID is empty. Verify the person and supply the correct ID in the source before rerunning.

### `source.first_name_missing` {#source-first-name-missing}

The source first name is empty. Verify and correct the source if a name is required for this notice.

### `source.last_name_missing` {#source-last-name-missing}

The source last name is empty. Verify and correct the source if a name is required for this notice.

### `source.school_name_missing` {#source-school-name-missing}

The source school name is empty. Verify the school and correct the source if needed.

### `source.board_name_missing` {#source-board-name-missing}

The source board name is empty. Verify the board and correct the source if needed.

### `source.client_id_format` {#source-client-id-format}

A nonempty Panorama client ID does not contain exactly ten ASCII digits. Check leading zeroes and the source value, then rerun.

### `source.address_incomplete` {#source-address-incomplete}

One or more mailing address fields are missing. The message identifies them. Verify the address and update the source before mailing.

### `source.age_unknown` {#source-age-unknown}

Age could not be calculated from the birth and delivery dates. Check both dates and their formats, and rerun.

### `source.overdue_unusable` {#source-overdue-unusable}

An overdue disease, dose, or agent fragment could not be interpreted fully. Compare the message and source value with the input format; correct it and rerun. The original value is retained.

### `data.school_match` {#data-school-match}

The source school name and ID were compared with the configured reference. A name-only match warns; mismatched IDs, an ID associated with another name, or no match fail. Compare the source and the referenced snapshot and correct the appropriate file before rerunning.

### `data.duplicate_client_id` {#data-duplicate-client-id}

This ID occurs on multiple rows and was explicitly allowed in configuration. All rows are retained and use the same notice assignment. Review each row and its notice before sending; warnings are eligible for delivery.

### `data.duplicate_overdue_agents` {#data-duplicate-overdue-agents}

An overdue agent appears more than once in the source. Repetition can be expected when one agent covers several diseases. Review the source and notice; the facts are retained and this warning allows delivery.

### `data.duplicate_overdue_diseases` {#data-duplicate-overdue-diseases}

An overdue disease appears more than once after disease names are standardized, even if the dose numbers differ. Review the source and dose numbers; the facts are retained and this warning allows delivery.

### `data.forecast_coverage` {#data-forecast-coverage}

The configured agent lookup compares forecasted agents with supplied overdue diseases. Extra diseases or unmapped agents warn; no supplied diseases or agents is not applicable. Review the source and lookup measurements. Missing disease coverage can instead stop preparation with a run error; inspect that error and correct the inputs or reference.

## Assignment

### `assignment.extra_manifest_row` {#assignment-extra-manifest-row}

The assignment file includes client IDs absent from the CSV. Compare the two files and remove or explain extra assignments before rerunning.

### `assignment.version_conflict` {#assignment-version-conflict}

The source version differs from the explicitly selected template version. Confirm the intended selection with the notice owner and correct the source or assignment.

### `assignment.eligibility_conflict` {#assignment-eligibility-conflict}

The selected notice's catalog applicability rule does not match the supplied facts. Check the assignment, source data and catalog rule with the notice owner; choose the appropriate notice and rerun.

### `assignment.check_unavailable` {#assignment-check-unavailable}

The selected notice has no matching catalog rule, so applicability could not be checked. Verify the assignment and catalog with the notice owner.

## Content

### `content.translation_missing` {#content-translation-missing}

A requested translation was unavailable. Inspect the notice text and language; ask the template maintainer to provide the missing translation.

### `content.history_mapping` {#content-history-mapping}

The history component could not map one or more agents. Review the source history and configured agent reference, correct the mapping or source, and rerun.

### `content.history_validity` {#content-history-validity}

Validity coverage varies across the cohort. Review the displayed history and source validity information with the data owner.

### `content.history_age_unknown` {#content-history-age-unknown}

A history displaying vaccination ages lacks a usable birth date. Verify the birth date in the source and rerun, or review the notice without ages.

### `content.address_reader_unknown` {#content-address-reader-unknown}

The intended reader is unknown, so a neutral addressee is used. Confirm the intended recipient and update the source or template if needed.

### `content.birth_date_unknown` {#content-birth-date-unknown}

The component expects to display a birth date but none is available. Verify the source date and review the notice.

### `content.link_https` {#content-link-https}

A web link or QR destination lacks HTTPS or a host, or contains spaces. Check the destination in the template or configuration. This is a format check and does not test reachability.

### `content.link_destination` {#content-link-destination}

A link or QR destination does not match the supported HTTPS, `mailto:` or `tel:` address formats. Correct the destination and inspect the resulting notice. This check does not contact the destination.

### `content.multiple_links` {#content-multiple-links}

More than one distinct link or QR destination is present. Inspect each destination and confirm that the differences are intended.

## Layout and components

Inspect the indicated notice page and measurements where available. Ask the template maintainer to correct the component or page settings and regenerate the notice when needed.

### `layout.history_width` {#layout-history-width}

History columns need more width than is available. Reduce columns or adjust template widths, then inspect the history.

### `layout.header_title_lines` {#layout-header-title-lines}

The title exceeds the measured space. Review the header and adjust the title or layout.

### `layout.address_outside_window` {#layout-address-outside-window}

The address falls outside the configured envelope window. Compare the printed page with the actual envelope and adjust placement or window settings.

### `layout.client_details_in_window` {#layout-client-details-in-window}

Client details overlap the envelope window. Inspect the page and adjust the template to keep unintended details out of the window.

### `layout.envelope_window_missing` {#layout-envelope-window-missing}

An address component was placed without an envelope window definition, so its window placement could not be checked. Define the correct window or inspect placement manually.

### `layout.signature_page` {#layout-signature-page}

The signature block does not fit as expected. Inspect the page break and adjust the layout or overflow setting.

### `layout.privacy_page` {#layout-privacy-page}

The privacy notice is on a different page from the expected page. Inspect the indicated pages and adjust page breaks or the expected page.

### `layout.section_pages` {#layout-section-pages}

A section spans pages when overflow was not allowed. Inspect the section and adjust its layout or overflow setting.

### `layout.link_width` {#layout-link-width}

A displayed link needs more width than is available. Inspect the link and adjust its text or available width.

### `component.*.absent` {#component-absent}

The named shared component was not used in the notice; this is recorded as not applicable. Confirm the template uses the component if it is required for that notice. Its absence alone does not establish that the notice is incorrect.

## Generation and output

### `compiler.warning` {#compiler-warning}

The notice compiler reported a warning. Open notice creation messages, inspect the resulting PDF and ask the template maintainer to resolve the cause.

### `compiler.font_substitution` {#compiler-font-substitution}

A font was substituted. Inspect the notice for text and layout changes; provide the intended font or update the template.

### `compiler.layout_nonconvergent` {#compiler-layout-nonconvergent}

Layout did not converge reliably. Ask the template maintainer to review the compiler messages and layout dependencies, then regenerate and inspect the notice.

### `rendering.failed` {#rendering-failed}

Notice compilation failed. Inspect the original error or creation messages, correct the template, fonts or inputs identified there, and run again.

### `render.evidence_failed` {#render-evidence-failed}

The PDF was created but its required render evidence was missing, invalid or inconsistent. A readable original remains available for review. Ask the template maintainer to correct the evidence and regenerate it.

### `output.readable` {#output-readable}

PDF export returned no pages or no bytes. Ask the template maintainer to inspect the creation error and regenerate the notice. Core trusts successful Typst PDF export and uses the page count from the same compiled document; it does not parse the exported bytes again. Older runs also used this code for a failed PDF inspection or inconsistent page count.

### `encryption.failed` {#encryption-failed}

A requested encrypted copy could not be created. Check the error, encryption settings and required source fields; correct them and rerun. A readable original goes to review.

### `delivery.original_unusable` {#delivery-original-unusable}

The original PDF is missing or unreadable during bundle assembly. Restore or regenerate a usable original before rebuilding bundles.

### `delivery.notice_length` {#delivery-notice-length}

The original page count differs from the configured required notice length. Inspect the original and the setting; correct the template or setting and rebuild. Pages are not added to meet the count.

## Artifact filenames and grouping

### `output.filename_fallback` {#output-filename-fallback}

A filename template referenced a missing value, a value that differs across
bundle members, or produced no usable filename characters. A deterministic
fallback was used and the artifact remains available. Review the recorded path,
pattern and grouping; supply the value or choose a supported consistent field.
This warning does not change delivery eligibility.
