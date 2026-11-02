// @immuknow-settings: settings.typ
#import "settings.typ": *
#show: notice-style // Apply the layout and theme from Settings

// Name used in the legal wording; the printed signature may include credentials.
#let order-signatory-name = "Dr. Annie Body"

// The explicit assignment comes from the upstream assessment.
// The supplied overdue diseases must already reflect exemptions and the MOH's assessment.
#notice-page("Order for Suspension from Attendance at School")[
#align(center)[_Pursuant to s. 6 of the Immunization of School Pupils Act_]
#immuknow.client-block(
  notice,
  window: if envelope-window == none { none } else { (..envelope-window, y: 135pt) }, // Room for the order title
  font-size: client-font-size,
  details: client-details,
  addressee: "Student:",
  school-label: "School",
)
#set par(spacing: 11pt) // Separate the order, reasons, and hearing information
#v(0.1cm)
#block[
  _To: Principal of_ *#notice.client_data.school*#linebreak()
  _Serve: Parent/Guardian#if notice.client_data.over_16 == true [ and student]._
]

#v(10pt) // Separate service instructions from the order
I, *#order-signatory-name*, Medical Officer of Health for *Cedar Ridge Health Unit*, order the suspension of the above named student for a period of twenty school days,

// Sample suspension dates: set the end date using your school calendar (20 school days)
#grid(columns: (1fr, 1fr), gutter: 12pt,
  [*From:* #immuknow.long-date("2026-02-02", "en")],
  [*To:* #immuknow.long-date("2026-03-02", "en")],
)

#v(10pt) // Space after the suspension dates
*This order will be cancelled where circumstances for making the order no longer exist.*

The reasons for this order are:

#enum(
  tight: false,
  spacing: 12pt,
  [I have not received one of the following for the above named student:
    #enum(numbering: "(a)", indent: 12pt, tight: false, spacing: 10pt,
      [A statement that the student has completed the prescribed program of immunization in relation to:
        #block(above: 10pt, below: 10pt)[
          #strong(immuknow.overdue-diseases(
            notice,
            style: "comma-separated",
            include-dose: false,
            labels: presentation.selected-labels(),
          ))
        ]
      ],
      [A statement of medical exemption, OR],
      [A further medical exemption to replace one that has expired, OR],
      [A statement of conscience or religious belief (commissioned affidavit required).],
    )
  ],
  [I am not satisfied that the student has completed, has commenced and will complete, or will commence and complete the prescribed program of immunization in relation to the disease(s) indicated above.],
)

#v(10pt) // Separate the reasons from the reader information
*#if notice.client_data.over_16 == true [Student] else if notice.client_data.over_16 == false [Parent/Guardian] else [Client or representative]:*

Questions about this Order can be directed to Cedar Ridge Health Unit — Toll-free: #immuknow.link("tel:1-800-555-0100").

You are entitled to a hearing by the Health Services Appeal and Review Board if you mail or deliver to me, and the Health Services Appeal and Review Board, 151 Bloor Street West, 9th Floor, Toronto, ON M5S 1S4, and the principal of *#notice.client_data.school*, a request for a hearing within 15 days of this notice being served.

Although a hearing may be requested, this order takes effect when it is served.

#v(10pt) // Space above the signature and service date
#grid(columns: (1fr, auto), gutter: 12pt, align: horizon,
  immuknow.signature-block(
    signature: image("assets/signature.png", width: 4.5cm), // Change width; height follows the image’s aspect ratio.
    name: "Dr. Annie Body",
    title: "Medical Officer of Health",
  ),
  [*Date Served:* #date_of_delivery],
)
]
