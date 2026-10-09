#let notice = json(sys.inputs.at("data"))
#let template-version = "affirmative_schedule_v1"
#let template-language = "en"
// Author controls: auto inherits prepared rendering defaults; () and false are explicit.
#let list-columns = 1
#let history-diseases = auto
#let history-ignore-agents = auto
#let history-include-other = auto
#let history-show-validity = auto
#let history-min-rows = 5
#import "lib/immuknow/lib.typ" as ik
#ik.check-notice(notice, version: template-version, language: template-language)

// --- CCEYA NOTICE TEMPLATE (TEST VERSION) --- //
// Description: A typst template that dynamically generates CCEYA templates.
// NOTE: All contact details are placeholders for testing purposes only.
// ----------------------------------------- //

#import "/templates/conf.typ"
#import "/templates/presentation.typ" as presentation

// General document formatting 
#set text(fill: black)
#set par(justify: false)
#set page("us-letter")

// Formatting links - prevent URLs from splitting across lines
#show link: it => box(underline(it))

// Font formatting
#set text(
  font: "FreeSans",
  size: 10pt
)
#set text(lang: "en", region: "CA")

// Immunization Notice Section
#let immunization_notice(client, client_id, date, font_size) = block[

#v(0.2cm)

#conf.header_info_cim(notice.logo_path, 6cm, black, 16pt, "Request for Immunization Record")

#v(0.2cm)

#conf.client_info_tbl_en(equal_split: false, vline: false, client, client_id, font_size, "Childcare Centre", 81pt, border: false)

#v(0.3cm)

// Notice for immunizations
As of *#date* our files show that your child is up-to-date for their immunization(s)! Their Immunization Record can be viewed on page 2.


For any future received vaccines, you can update your child's record by using one of the following options:

1. By visiting #text(fill:conf.linkcolor)[#link("https://www.test-immunization.ca")]
2. By emailing #text(fill:conf.linkcolor)[#link("records@test-immunization.ca")]
3. By mailing a photocopy of your child's immunization record to Test Health, 123 Placeholder Street, Sample City, ON A1A 1A1
4. By Phone: 555-555-5555 ext. 1234

Please update Public Health and your childcare centre every time your child receives a vaccine. 


If you have any questions, please call 555-555-5555 ext. 1234.


Thank you for helping to keep our children safe.


  Sincerely, 

#conf.signature(notice.signature_path, "Dr. Jane Smith, MPH", "Associate Medical Officer of Health")

// Invisible marker for layout validation
#box(width: 0pt, height: 0pt)[
  #text(size: 0.1pt, fill: white)[MARK_END_SIGNATURE_BLOCK]
]
  
]

#let vaccine_table_page(client_id) = block[
  
  #v(0.5cm)

  #grid(
  
  columns: (50%,50%), 
  gutter: 5%, 
  [#image(notice.logo_path, width: 6cm)],
  [#set align(center + bottom)
    #text(size: 20.5pt, fill: black)[*Immunization Record*]]
  
)

  #v(0.5cm)

  For your reference, the immunization(s) on file with Public Health are as follows:  
  
]

#let end_of_immunization_notice() = [
  #set align(center)
  End of immunization record ]

#let client_row = notice.client_id
#let data = notice.client_data
#let date = presentation.long-date(notice.date_as_of, "en", required: false)

#set page(
  margin: (top: 1cm, bottom: 2cm, left: 1.75cm, right: 2cm),
  footer: align(center, context numbering("1 / " + str(counter(page).final().first()), counter(page).get().first()))
)

#immunization_notice(data, client_row, date, 11pt)
#pagebreak()
#vaccine_table_page(client_row)
#ik.immunization-history(notice, diseases: history-diseases, ignore-agents: history-ignore-agents, include-other: history-include-other, show-validity: history-show-validity, min-rows: history-min-rows, font-size: 11pt, labels: presentation.selected-labels())
#end_of_immunization_notice()
