#import "lib/immuknow/lib.typ" as immuknow
#import "presentation.typ" as presentation

#let paper-size = "us-letter"

#let page-margins = (top: 1cm, bottom: 2cm, left: 1.75cm, right: 2cm)
#let envelope-window = (x: 63pt, y: 120pt, width: 324pt, height: 81pt, padding: 11pt)

#let client-details = "right"

#let logo-width = 7cm

#let body-font = "FreeSans"
#let body-size = 10pt
#let heading-color = black
#let link-color = rgb("#0000ee")
#let accent-color = rgb("#005568")
#let title-size = 20pt
#let client-font-size = 10pt

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

#let notice = json(sys.inputs.at("data"))
#let template-filename = sys.inputs.at("notice-template")
#assert(template-filename == notice.template, message: "Selected template identity differs from the facts")
#immuknow.check-notice(
  notice,
  version: sys.inputs.at("notice-version"),
  language: sys.inputs.at("notice-language"),
)
#let logo = image("assets/logo.svg", width: logo-width)
#let dates = immuknow.notice-dates(notice)
#let date_of_delivery = dates.date_of_delivery
#let date_as_of = dates.date_as_of
#let date_of_birth = dates.date_of_birth

#let letter(body) = immuknow.letter(
  body,
  notice: notice,
  language: notice.language,
  paper: paper-size,
  margins: page-margins,
  font: body-font,
  font-size: body-size,
  link-color: link-color,
)

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

#let immunization-history() = immuknow.immunization-history(
  notice,
  diseases: ("Diphtheria", "Tetanus", "Pertussis", "Polio", "Hib", "Pneumococcal",
    "Rotavirus", "Measles", "Mumps", "Rubella", "Meningococcal", "Varicella"),
  ignore-agents: ("RSVAb", "VarIg", "HBIg", "RabIg", "Ig"),
  include-other: true,
  show-validity: false,
  omit-invalid: false,
  show-age: false,
  min-rows: 5,
  font-size: if notice.language == "fr" { 10.6pt } else { 11pt },
  heading-size: auto,
  indicator-font: "FreeSans",
  indicator-size: auto,
  indicator-offset: (x: 0pt, y: 0pt),
  labels: presentation.selected-labels(),
)
