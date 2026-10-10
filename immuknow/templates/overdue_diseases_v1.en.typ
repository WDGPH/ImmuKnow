#let notice = json(sys.inputs.at("data"))
#let template-version = "overdue_diseases_v1"
#let template-language = "en"
// @immuknow-settings: settings/overdue_diseases_v1.en.typ
#import "settings/overdue_diseases_v1.en.typ": list-columns, history-diseases, history-ignore-agents, history-include-other, history-show-validity, history-min-rows, envelope-window, page-margins, body-font, body-size, logo-width, title-size, signature-width, signature-height, client-font-size, client-details, address-addressee
#import "lib/immuknow/lib.typ" as ik
// Shared project settings are edited by the playground layout selectors.
#let layout = ik.project-layout(json("layout-settings.json"), template-version + "." + template-language, window: envelope-window)
#ik.check-notice(notice, version: template-version, language: template-language)

// --- CCEYA NOTICE TEMPLATE (TEST VERSION) --- //
// Description: A typst template that dynamically generates CCEYA templates.
// NOTE: All contact details are placeholders for testing purposes only.
// ----------------------------------------- //

#import "conf.typ"
#import "presentation.typ" as presentation

#show: ik.notice-page.with(language: template-language, paper: layout.paper, margins: page-margins, font: body-font, font-size: body-size)
#show link: it => box(underline(it))

// Immunization Notice Section
#let immunization_notice(client, date) = block[

#v(0.2cm)

#ik.notice-header(logo: image(notice.logo_path, width: logo-width), logo-width: logo-width, title-size: title-size, title: "Request for Immunization Record")

#v(0.2cm)

#ik.client-block(notice, window: layout.window, font-size: client-font-size, details: client-details, addressee: address-addressee)

#v(0.3cm)

// Notice for immunizations
As of *#date* our files show that your child has not received the following immunization(s):  

#set list(indent: 0.8cm)
#strong(ik.overdue-diseases(notice, columns: list-columns, labels: presentation.selected-labels()))

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

#ik.signature-block(signature: image(notice.signature_path, width: signature-width, height: signature-height, fit: "contain"), name: "Dr. Jane Smith, MPH", title: "Associate Medical Officer of Health")

  
]

#let vaccine_table_page() = block[
  
  #v(0.5cm)

  #ik.notice-header(logo: image(notice.logo_path, width: logo-width), logo-width: logo-width, title-size: 20.5pt, title: "Immunization Record")

  #v(0.5cm)

  For your reference, the immunization(s) on file with Public Health are as follows:  
  
]

#let end_of_immunization_notice() = [
  #set align(center)
  End of immunization record ]

#let data = notice.client_data
#let date = presentation.long-date(notice.date_as_of, "en", required: false)


#immunization_notice(data, date)
#pagebreak()
#vaccine_table_page()
#ik.immunization-history(notice, diseases: history-diseases, ignore-agents: history-ignore-agents, include-other: history-include-other, show-validity: history-show-validity, min-rows: history-min-rows, font-size: 11pt, labels: presentation.selected-labels())
#end_of_immunization_notice()
