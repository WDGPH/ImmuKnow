# Render-report version 4 evidence

`resources/typst/report.json` owns the compiled report schema. Native and browser
validators compare its complete `notice` with prepared facts before trusting a
report. The saved native projection has a different purpose from this compiled
envelope; it retains the validated facts digest and semantic evidence needed to
review and rebundle without storing another complete notice or check list.

| Fields | Compiled report | Consumer or reason |
| --- | --- | --- |
| `notice`, `identity`, `requirements`, `blocked_checks` | Retain complete facts and explicit evaluation state | Native/browser source association and mandatory requirement validation |
| `components`, component presence/absence findings, `page_count` | Retain | Detect missing, inconsistent or wrong-page evidence |
| Address `x_pt`, `y_pt`, `width_pt`, `height_pt`, `page`, `window_*_pt` | Retain once in component measurements | Studio envelope guide and address source target; finite bounds and page validation |
| Client `x_pt`, `y_pt`, `width_pt`, `height_pt`, `page` | Retain once in component measurements | Studio source target and validated placement |
| Address/client `text`, `row_key`, `client_id`, `source_matches` | Retain | Bind placed content to the exact source facts |
| Header `title_height_pt`, `three_line_height_pt` | Keep only on a warning/failure comparison; header component is an empty measurement object | Successful arithmetic has no editor or source-validation consumer |
| Signature `first_page`, `last_page`, `x_pt`, `y_pt`, `end_y_pt`; section `title`, `first_page`, `last_page` | Retain in component measurements | Placed page locations and Studio source navigation |
| History `administrations`, `displayed_rows`, `page` and source identity | Retain | History/source evidence and Studio navigation |
| Agent/disease display source identity, exact source/excluded/displayed lists, counts and replacement evidence | Retain, including passing outcomes | Validate source preservation and intentional replacement/exclusion |
| `data.forecast_coverage.measurements` lists | Retain, including passing/not-applicable outcomes | Native/browser equality with prepared `forecast_coverage` |
| `qr_urls`, link component `page`/`url`, warning `subjects` | Retain exact values | Artifact/link verification and stable warning issue identities |
| Successful `layout.*` check measurements | Omit; retain status, code, component and page | Geometry belongs to components; passing arithmetic remains local to compilation |
| Warning/failure address comparison | Retain overflow margins; component retains the address/window rectangles | Explain correction without another full rectangle copy |
| Warning/failure title, width, privacy, signature and section comparisons | Retain useful actual/expected dimensions or pages | Explain why the layout needs review |

The shared fixtures exercise both removal of successful duplicate measurements
and preservation of warning detail. Source mismatches, invalid geometry, missing
semantic evidence and unsupported report versions still fail validation. Native
saved evidence can omit editor rectangles after validation, while retaining
semantic evidence and page locations; consumers must use that saved type rather
than validate it as a complete compiled report.
