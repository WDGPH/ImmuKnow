#let review = json(sys.inputs.at("data"))
#set page(width: 8.5in, height: 11in, margin: 18mm)
#set text(font: "FreeSans", size: 10pt)
#set par(leading: 0.7em)
#text(size: 20pt, weight: "bold", fill: rgb("b71c1c"))[REVIEW]

*Client ID:* #review.client_id \
*Source row:* #review.row_key \
*Notice:* #review.template \
*School:* #review.school \
*Board:* #review.board

#block[#text(weight: "bold")[Findings]]
#for finding in review.findings {
  block(breakable: true)[
    *#finding.status · #finding.code* \
    #finding.message
    #if finding.location != "" { [\ #finding.location] }
    #if finding.measurements != "" {
      par(text(size: 8.5pt, finding.measurements))
    }
  ]
}
#if review.findings.len() == 0 { [No warnings were recorded. This notice was explicitly selected for review.] }

#block[#text(weight: "bold")[Original notice]]
#par(text(size: 8.5pt, review.measurements))

#block[#text(weight: "bold")[After reviewing]]
Edit #raw("overrides.json") in this run directory. Add this client ID under
#raw("clients") with #raw("\"delivery\"") or #raw("\"review\""). For example:
#raw(review.override_example, block: true)
Warnings stay in the report. Delivery copies are rebuilt from the unchanged
original PDF; review sheets and marks are never removed from an old bundle.
#raw("immuknow-rebundle . --overrides ./overrides.json", block: true)
Run this command from the saved run directory. The command does not reread
source data or recompile client notices.
