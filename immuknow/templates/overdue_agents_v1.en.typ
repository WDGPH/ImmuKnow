#let notice = json(sys.inputs.at("data"))
#let template-version = "overdue_agents_v1"
#let template-language = "en"
#assert(notice.version_id == template-version, message: "Notice version does not match this template")
#assert(notice.language == template-language, message: "Notice language does not match this template")
#assert(notice.overdue_agents.len() > 0, message: "This overdue template requires vaccine agent data")

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
#let immunization_notice(client, client_id, immunizations_due, date, font_size) = block[

#v(0.2cm)

#conf.header_info_cim(notice.logo_path, 6cm, black, 16pt, "Request for Immunization Record")

#v(0.2cm)

#conf.client_info_tbl_en(equal_split: false, vline: false, client, client_id, font_size, "Childcare Centre", 81pt, border: false)

#v(0.3cm)

// Notice for immunizations
As of *#date* our files show that your child has not received the following immunization(s):  

#conf.client_immunization_list(immunizations_due)

Please review the Immunization Record on page 2 and update your child's record by using one of the following options:

1. By visiting #text(fill:conf.linkcolor)[#link("https://www.test-immunization.ca")]
2. By emailing #text(fill:conf.linkcolor)[#link("records@test-immunization.ca")]
3. By mailing a photocopy of your child's immunization record to Test Health, 123 Placeholder Street, Sample City, ON A1A 1A1
4. By Phone: 555-555-5555 ext. 1234

Please update Public Health and your childcare centre every time your child receives a vaccine. 

#grid(
  columns: (1fr, auto),
  gutter: 10pt,
  [*If you are choosing not to immunize your child*, a valid medical exemption or statement of conscience or religious belief must be submitted. Links to these forms can be located at #text(fill:conf.wdgteal)[#link("https://www.test-immunization.ca/exemptions")]. Please note this exemption is for childcare only and a new exemption will be required upon enrollment in elementary school.],
  [#if "qr_img" in client [
    #if "qr_url" in client [
      #link(client.qr_url)[#image(client.qr_img, width: 3cm)]
    ] else [
      #image(client.qr_img, width: 3cm)
    ]
  ]]
)

If there is an outbreak, children who are not adequately immunized may be excluded.

If you have any questions, please call 555-555-5555 ext. 1234.

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
#let vaccines_due_array = notice.overdue_agents
#let received = notice.received
#let diseases = notice.chart_diseases
#let show_validity_markers = notice.show_validity_markers
#let date = presentation.long-date(notice.date_as_of, "en", required: false)

#set page(
  margin: (top: 1cm, bottom: 2cm, left: 1.75cm, right: 2cm),
  footer: align(center, context numbering("1 / " + str(counter(page).final().first()), counter(page).get().first()))
)

#immunization_notice(data, client_row, vaccines_due_array, date, 11pt)
#pagebreak()
#vaccine_table_page(client_row)
#conf.immunization-table(5, received, diseases, 11pt, "en", show_validity_markers)
#end_of_immunization_notice()
