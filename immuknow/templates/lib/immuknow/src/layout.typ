#import "localization.typ": long-date

#let notice-page(body, language: "en", paper: "us-letter", margins: (top: 1cm, bottom: 2cm, left: 1.75cm, right: 2cm), font: "FreeSans", font-size: 10pt, page-numbers: true) = {
  assert(language in ("en", "fr"), message: "Unsupported notice language")
  assert(type(page-numbers) == bool, message: "page-numbers must be boolean")
  set text(font: font, size: font-size, lang: language, region: "CA", fill: black)
  set par(justify: false)
  set page(paper, margin: margins, footer: if page-numbers {
    align(center, context numbering("1 / " + str(counter(page).final().first()), counter(page).get().first()))
  } else { none })
  body
}

// Pass image content resolved in the consuming project, never a package-relative path.
#let notice-header(logo: none, title: [], logo-width: 6cm, title-size: 16pt, fill: black, placement: "left", spacing: 12pt) = {
  assert(placement in ("left", "right"), message: "Header placement must be left or right")
  let brand = box(width: logo-width, logo)
  let heading = align(center + bottom, text(size: title-size, fill: fill, weight: "bold", title))
  if placement == "left" {
    grid(columns: (1fr, 1fr), gutter: spacing, brand, heading)
  } else {
    grid(columns: (1fr, 1fr), gutter: spacing, heading, brand)
  }
}

// Printed page coordinates in points, measured from its top-left corner.
// The preset matches the former 81pt contact row, including its 11pt inset.
#let envelope-preset = (x: 1.75cm, y: 165.1pt, width: 202.28pt, height: 81pt, padding: 11pt)

#let check-window(window) = {
  assert(type(window) == dictionary, message: "Envelope window must be a dictionary")
  for key in ("x", "y", "width", "height", "padding") {
    assert(key in window and type(window.at(key)) == length,
      message: "Envelope window " + key + " must be an absolute physical length")
    assert(window.at(key) >= 0pt, message: "Envelope dimensions cannot be negative")
  }
  assert(window.width > 2 * window.padding and window.height > 2 * window.padding,
    message: "Envelope safety padding leaves no usable area")
}

#let evidence(values) = {
  // Zero-sized, nonprinting metadata text remains extractable in the PDF.
  // The same numbers are exposed as Typst metadata for preview guide overlays.
  [#metadata(values) <immuknow-layout>]
  box(width: 0pt, height: 0pt, text(size: 0.1pt, fill: white,
    values.pairs().map(pair => "MEASURE_" + upper(pair.at(0)) + ":" + str(pair.at(1))).join(" ")))
}

#let address-block(client, language: "en", addressee: auto, province: "Ontario") = {
  assert(language in ("en", "fr"), message: "Unsupported address language")
  let salutation = if addressee != auto { addressee } else if language == "en" {
    if client.over_16 { "To:" } else { "To Parent/Guardian of:" }
  } else {
    if client.over_16 { "Au:" } else { "Au parent ou tuteur de:" }
  }
  [#salutation#linebreak()
  #strong(client.name)#linebreak()
  #strong(client.address)#linebreak()
  #strong(client.city), #strong(province) #strong(client.postal_code)]
}

#let client-block(notice, window: envelope-preset, font-size: 10pt, min-font-size: 10pt,
  addressee: auto, province: "Ontario", school-label: auto, show-birth-date: true,
  show-school: true, details: "right", spacing: 0pt, border: none) = {
  check-window(window)
  assert(font-size >= min-font-size, message: "Client font is below the declared readable minimum")
  assert(details in ("right", "below"), message: "Client details placement must be right or below")
  set text(size: font-size)
  let language = notice.language
  let client = notice.client_data
  let school-label = if school-label != auto { school-label } else if language == "en" { "Childcare Centre" } else { "Centre de garde d'enfants" }
  let address = address-block(client, language: language, addressee: addressee, province: province)
  let info = [
    #if language == "en" [Client ID:] else [Identifiant du client:] #smallcaps(strong(notice.client_id))
    #if show-birth-date [#linebreak()#if language == "en" [Date of Birth:] else [Date de naissance:] #strong(long-date(client.date_of_birth_iso, language, required: false))]
    #if show-school [#linebreak()#school-label: #smallcaps(strong(client.school))]
  ]
  block(width: 100%, breakable: false)[
    #block(width: 0pt, height: 0pt, above: 0pt, below: 0pt)[#metadata(none) <immuknow-client-origin>]
    #context {
    let origin = query(<immuknow-client-origin>).first().location().position()
    assert(origin.page == 1, message: "Client block must start on the first page")
    let dx = window.x - origin.x
    let dy = window.y - origin.y
    assert(dx >= -0.1pt and dy >= -0.1pt,
      message: "Envelope window overlaps preceding content or the left page margin. Move the window or reduce preceding content.")
    let size = measure(address, width: window.width - 2 * window.padding)
    let height = calc.max(window.height, size.height + 2 * window.padding)
    v(calc.max(0pt, dy))
    pad(left: calc.max(0pt, dx))[
      #grid(columns: if details == "right" { (window.width, 1fr) } else { (1fr,) }, gutter: spacing,
        block(width: window.width, height: height, inset: window.padding, stroke: border, address),
        block(inset: window.padding, info))
    ]
    evidence((
      layout_version: 1, window_x: window.x.pt(), window_y: window.y.pt(),
      window_width: window.width.pt(), window_height: window.height.pt(),
      window_padding: window.padding.pt(), address_x: (origin.x + calc.max(0pt, dx) + window.padding).pt(),
      address_y: (origin.y + calc.max(0pt, dy) + window.padding).pt(),
      address_width: size.width.pt(), address_height: size.height.pt(),
      contact_height: height.pt(), address_page: origin.page,
    ))
  }]
}

#let signature-block(signature: none, name: [], title: [], spacing: 2pt) = block(breakable: false)[
  #if signature != none [#signature#v(spacing)]
  #name#linebreak()#title
  #box(width: 0pt, height: 0pt, text(size: 0.1pt, fill: white, "MARK_END_SIGNATURE_BLOCK"))
]

// The consuming entry point loads its project-owned JSON explicitly.
#let project-layout(settings, notice-key, window: envelope-preset) = {
  assert(settings.at("schema_version", default: none) == 1, message: "Unsupported layout settings schema")
  let selected = settings.notices.at(notice-key, default: (:))
  let paper = selected.at("paper", default: "us-letter")
  assert(paper in ("us-letter", "us-legal", "a4"), message: "Unsupported project paper size")
  let envelope = selected.at("envelope", default: "authored")
  if envelope != "authored" {
    assert(envelope in settings.presets, message: "Unknown project envelope preset")
    let preset = settings.presets.at(envelope)
    assert(type(preset.width_pt) in (int, float) and type(preset.height_pt) in (int, float), message: "Preset window dimensions must be numeric PDF points")
    window = (..window, width: preset.width_pt * 1pt, height: preset.height_pt * 1pt)
  }
  check-window(window)
  (paper: paper, window: window)
}
