#import "lib/immuknow/lib.typ" as immuknow
#import "presentation.typ" as presentation

// Page and envelope
// Paper: keep one choice uncommented
#let paper-size = "us-letter" // Letter · 8.5 × 11 in
// #let paper-size = "us-legal" // Legal · 8.5 × 14 in
// #let paper-size = "a4" // A4 · 210 × 297 mm

#let page-margins = (top: 1cm, bottom: 2cm, left: 1.75cm, right: 2cm) // Space between the page edges and the letter
// #10 envelope: 9.5 × 4.125 in; window: 4.5 × 1.125 in, 0.875 in from left and 0.5 in from bottom.
// Compact address position; adjust y and the fold position to suit your envelope/stuffer.
// Address window: x is the distance from the left; y is the distance from the top.
#let envelope-window = (x: 63pt, y: 120pt, width: 324pt, height: 81pt, padding: 11pt) // Window position, size, and space around the address
// Other sample windows: uncomment one in place of the line above.
// #let envelope-window = (x: 1.75cm, y: 165.1pt, width: 100mm, height: 45mm, padding: 11pt) // DL
// #let envelope-window = (x: 1.75cm, y: 165.1pt, width: 90mm, height: 45mm, padding: 11pt) // C5

#let suspension-window = if envelope-window == none { none } else { (..envelope-window, y: 135pt) } // Room for the order title and legal subtitle

#let client-details = "right" // Client details beside the address; "below" places them underneath

#let logo-width = 7cm // Logo width
#let signature-width = 4.5cm // Signature width
#let signature-height = 1.5cm // Signature height

// Theme
// Match your organization’s fonts and colours. Colour values can be copied from your brand guide
#let body-font = "FreeSans" // Letter typeface
#let body-size = 10pt // Letter text size
#let heading-color = black // Colour of the letter and history headings
#let link-color = rgb("#0000ee") // Colour of website and email links
#let accent-color = rgb("#005568") // Default colour of the QR code
#let title-size = 20pt // Size of the letter and history headings
#let client-font-size = 10pt // Size of the address and client details

// Letter features
#let health-unit-name = "Cedar Ridge Health Unit" // Issuing organization
#let health-unit-address = "123 Example Street, Demo City, ON N0N 0N0" // Mailing address
#let records-url = "https://example.org/immunization" // Submit immunization records
#let records-email = "records@example.org" // Records email address
#let exemptions-url = "https://example.org/exemptions" // Exemption forms
#let health-unit-phone = "1-800-555-0100" // Public contact number
#let signature-name = "Dr. Annie Body" // Printed name below the signature
// Reader wording is chosen in the Template using the client’s age
#let address-addressee = auto // Same reader as the letter

#let list-style = "bullets" // "comma-separated" for a plain inline list
#let list-columns = 1 // Columns when using bullets
#let include-dose = false // Add the overdue disease dose number

// QR destination is resolved in Typst and shared by the code and its clickable link
#let qr = (
  enabled: true,
  url: notice => immuknow.query-url("https://example.org/update", (
    client_id: notice.client_id,
    dob: notice.client_data.date_of_birth_iso,
    lang: notice.language,
  )),
  width: 3cm,
  foreground: accent-color,
  background: white,
  module-shape: "square",
  corner-style: "square",
)
// #let qr = (..qr, enabled: false)
// #let qr = (..qr, url: "https://example.org/immunization") // One destination for everyone

#let affirmative-qr = (..qr, enabled: false) // QR options for up-to-date notices

// Suspension order: sample dates; set the end date using your school calendar (20 school days)
#let suspension-start = "2026-02-02"
#let suspension-end = "2026-03-02"
#let hearing-board-address = "151 Bloor Street West, 9th Floor, Toronto, ON M5S 1S4"

// Notice data and supporting imports.
#let notice = json(sys.inputs.at("data"))
#let template-filename = sys.inputs.at("notice-template")
#assert(template-filename == notice.template, message: "Selected template identity differs from the facts")
#immuknow.check-notice(
  notice,
  version: sys.inputs.at("notice-version"),
  language: sys.inputs.at("notice-language"),
)
#let logo = image("assets/logo.png", width: logo-width)
#let signature = image("assets/signature.png", width: signature-width, height: signature-height, fit: "contain")
#let dates = immuknow.notice-dates(notice)
#let date_of_delivery = dates.date_of_delivery
#let date_as_of = dates.date_as_of
#let date_of_birth = dates.date_of_birth

#let notice-style(body) = immuknow.notice-style(
  body,
  notice: notice,
  language: notice.language,
  paper: paper-size,
  margins: page-margins,
  font: body-font,
  font-size: body-size,
  link-color: link-color,
)

// Each section starts a fresh page; unexpected continuation produces a finding
#let notice-page(title, body, allow-overflow: false) = immuknow.notice-section(
  title, body,
  logo: logo,
  logo-width: logo-width,
  title-size: title-size,
  fill: heading-color,
  heading-above: 0.2cm,
  heading-below: 0.5cm,
  allow-overflow: allow-overflow,
)

// History options are evaluated only when the letter inserts this component
#let immunization-history() = immuknow.immunization-history(
  notice,
  diseases: ("Diphtheria", "Tetanus", "Pertussis", "Polio", "Hib", "Pneumococcal",
    "Rotavirus", "Measles", "Mumps", "Rubella", "Meningococcal", "Varicella"),
  ignore-agents: ("RSVAb", "VarIg", "HBIg", "RabIg", "Ig"), // Vaccines left out of the table
  include-other: true, // Include a column for other vaccines
  show-validity: false, // Show which doses count toward requirements
  omit-invalid: false, // Exclude invalid doses from the history
  show-age: false, // Add age in years and months after the vaccination date
  min-rows: 5, // Minimum number of vaccination rows
  font-size: if notice.language == "fr" { 10.6pt } else { 11pt },
  heading-size: auto, // Same size as chart text; use e.g. 11pt to override
  indicator-font: "FreeSans", // Consistent dots across letter typefaces
  indicator-size: auto, // Same size as chart text
  indicator-offset: (x: 0pt, y: 0pt), // Optical adjustment for your typeface
  labels: presentation.selected-labels(),
)
