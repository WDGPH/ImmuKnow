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
Failed checks must be corrected; they cannot be accepted as warnings.
Inspect the original PDF and the latest evaluation in #raw("report.html").
Accept each eligible warning with its exact token and a reason:
#raw("immuknow-rebundle . --accept-warning <token> --reason \"Reviewed\"", block: true)
#for (code, token) in review.warning_tokens {
  block(breakable: true)[*#code* \ #text(size: 8pt, raw(token))]
}
Tokens expire when the PDF, evidence, warnings or rules change. Findings and
individual acceptances stay in #raw("run.json"). Delivery copies use unchanged
originals; review sheets and marks are never removed from an old bundle.
Use #raw("--withhold " + review.row_key) to keep this row in review. The command
does not reread source data or recompile client notices.
