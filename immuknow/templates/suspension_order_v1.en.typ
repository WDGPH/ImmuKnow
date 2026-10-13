// @immuknow-settings: settings.typ
#import "settings.typ": *
#show: notice-style // Apply the layout and theme from Settings

// The explicit assignment comes from the upstream assessment.
// The supplied overdue diseases must already reflect exemptions and the MOH's assessment.
#notice-page("Order for Suspension from Attendance at School")[
#align(center)[_Pursuant to s. 6 of the Immunization of School Pupils Act_]
#immuknow.client-block(
  notice,
  window: suspension-window,
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
I, *#signature-name*, Medical Officer of Health for *#health-unit-name*, order the suspension of the above named student for a period of twenty school days,

#grid(columns: (1fr, 1fr), gutter: 12pt,
  [*From:* #immuknow.long-date(suspension-start, "en")],
  [*To:* #immuknow.long-date(suspension-end, "en")],
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

Questions about this Order can be directed to #health-unit-name — Toll-free: #health-unit-phone.

You are entitled to a hearing by the Health Services Appeal and Review Board if you mail or deliver to me, and the Health Services Appeal and Review Board, #hearing-board-address, and the principal of *#notice.client_data.school*, a request for a hearing within 15 days of this notice being served.

Although a hearing may be requested, this order takes effect when it is served.

#v(10pt) // Space above the signature and service date
#grid(columns: (1fr, auto), gutter: 12pt, align: horizon,
  immuknow.signature-block(
    signature: signature,
    name: signature-name,
    title: "Medical Officer of Health",
  ),
  [*Date Served:* #date_of_delivery],
)
]
