// @immuknow-settings: settings.typ
#import "settings.typ": *
#show: notice-style // Apply the layout and theme from Settings

// Page 1: the letter. Each if/else below chooses wording for the client or their parent
// over_16 is true for clients aged 16 or older.
#notice-page("Request for Immunization Record")[
#immuknow.client-block(
  notice,
  window: envelope-window,
  font-size: client-font-size,
  details: client-details,
  addressee: address-addressee,
) // Mailing address and client details
#v(0.3cm) // Space before the message

As of *#date_as_of* our files show that #if notice.client_data.over_16 == true [you have] else if notice.client_data.over_16 == false [your child has] else [the named client has] not received the following immunization(s):

#set list(indent: 0.8cm)
#strong(
  immuknow.overdue-diseases(
    notice,
    style: list-style,
    columns: list-columns,
    include-dose: include-dose,
    labels: presentation.selected-labels(),
  )
)

Please review the Immunization Record on page 2 and update #if notice.client_data.over_16 == true [your record] else if notice.client_data.over_16 == false [your child's record] else [the client's record] by using one of the following options:

1. By visiting #link(records-url)
2. By emailing #link("mailto:" + records-email)[#records-email]
3. By mailing a photocopy of #if notice.client_data.over_16 == true [your] else if notice.client_data.over_16 == false [your child's] else [the client's] immunization record to #health-unit-name, #health-unit-address
4. By Phone: #health-unit-phone

Please update Public Health#if notice.client_data.over_16 == false [ and your childcare centre] every time #if notice.client_data.over_16 == true [you receive] else if notice.client_data.over_16 == false [your child receives] else [the client receives] a vaccine.

#grid(
  columns: (1fr, auto),
  gutter: 10pt,
  [*If you are choosing not to #if notice.client_data.over_16 == true [be immunized] else if notice.client_data.over_16 == false [immunize your child] else [immunize the client]*, a valid medical exemption or statement of conscience or religious belief must be submitted. Links to these forms can be located at #link(exemptions-url). Please note this exemption is for childcare only and a new exemption will be required upon enrollment in elementary school.],
  [#immuknow.qr-code(notice, ..qr)]
)

If there is an outbreak, children who are not adequately immunized may be excluded.

If you have any questions, please call #health-unit-phone.

  Sincerely,

#immuknow.signature-block(
  signature: signature,
  name: signature-name,
  title: "Associate Medical Officer of Health",
)

]

#notice-page("Immunization Record")[
  For your reference, the immunization(s) on file with Public Health are as follows:

  #immunization-history()
  #align(center)[End of immunization record]
]
