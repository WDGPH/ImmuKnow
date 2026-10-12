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

As of *#date_as_of* our files show that #if notice.client_data.over_16 == true [you are] else if notice.client_data.over_16 == false [your child is] else [the named client is] up-to-date for #if notice.client_data.over_16 == true [your] else if notice.client_data.over_16 == false [their] else [the client's] immunization(s)! #if notice.client_data.over_16 == true [Your] else if notice.client_data.over_16 == false [Their] else [The client's] Immunization Record can be viewed on page 2.

For any future received vaccines, you can update #if notice.client_data.over_16 == true [your record] else if notice.client_data.over_16 == false [your child's record] else [the client's record] by using one of the following options:

1. By visiting #link(records-url)
2. By emailing #link("mailto:" + records-email)[#records-email]
3. By mailing a photocopy of #if notice.client_data.over_16 == true [your] else if notice.client_data.over_16 == false [your child's] else [the client's] immunization record to #health-unit-name, #health-unit-address
4. By Phone: #health-unit-phone

Please update Public Health#if notice.client_data.over_16 == false [ and your childcare centre] every time #if notice.client_data.over_16 == true [you receive] else if notice.client_data.over_16 == false [your child receives] else [the client receives] a vaccine.

If you have any questions, please call #health-unit-phone.

Thank you for helping to keep our children safe.

#immuknow.qr-code(notice, ..affirmative-qr)

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
