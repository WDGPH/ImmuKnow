#import "localization.typ": long-date
#import "findings.typ": check, component, report

#let notice-page(body, language: "en", paper: "us-letter", margins: (top: 1cm, bottom: 2cm, left: 1.75cm, right: 2cm), font: "FreeSans", font-size: 10pt, page-numbers: true) = {
  assert(language in ("en", "fr"), message: "Unsupported notice language")
  assert(type(page-numbers) == bool, message: "page-numbers must be boolean")
  set text(font: font, size: font-size, lang: language, region: "CA", fill: black)
  set par(justify: false)
  set page(paper, margin: margins, footer: if page-numbers {
    align(center, context numbering("1 / " + str(counter(page).final().first()), counter(page).get().first()))
  } else { none })
  component("page")
  body
}

#let notice-header(logo: none, title: [], logo-width: 6cm, title-size: 20pt, fill: black, placement: "left", spacing: 12pt) = {
  assert(placement in ("left", "right"), message: "Header placement must be left or right")
  layout(size => {
    let brand-width = if logo == none { 0pt } else { logo-width }
    let gap = if logo == none { 0pt } else { spacing }
    let title-width = size.width - brand-width - gap
    assert(title-width > 0pt, message: "Header logo and spacing leave no room for the title")
    let title-text(body) = {
      set par(leading: 0.65em)
      text(size: title-size, fill: fill, weight: "bold", top-edge: "bounds", bottom-edge: "bounds", body)
    }
    let heading = title-text(title)
    let maximum = measure(title-text[Ágj#linebreak()Ágj#linebreak()Ágj], width: title-width).height
    let height = measure(heading, width: title-width).height
    component("header", measurements: (title_height_pt: height.pt(), three_line_height_pt: maximum.pt()))
    context check("layout.header_title_lines", if height <= maximum + 0.1pt { "pass" } else { "warn" },
      if height <= maximum + 0.1pt { "Title fits within three lines." } else { "Title exceeds three lines." },
      component: "header", page: here().page(), measurements: (title_height_pt: height.pt(), three_line_height_pt: maximum.pt()))
    let brand = box(width: brand-width, logo)
    if logo == none { align(center, heading) }
    else if placement == "left" { grid(columns: (brand-width, 1fr), gutter: gap, align: horizon, brand, align(center, heading)) }
    else { grid(columns: (1fr, brand-width), gutter: gap, align: horizon, align(center, heading), brand) }
  })
}

// #10 window: 4.5 by 1.125 in; addressed top third aligns with envelope top-left.
#let envelope-preset = (x: 63pt, y: 180pt, width: 324pt, height: 81pt, padding: 11pt)
#let check-window(window) = {
  for key in ("x", "y", "width", "height", "padding") {
    assert(type(window.at(key)) == length and window.at(key) >= 0pt, message: "Envelope dimensions must be nonnegative absolute lengths")
  }
  assert(window.width > 2 * window.padding and window.height > 2 * window.padding, message: "Envelope padding leaves no usable area")
}

#let address-content(client, language: "en", addressee: auto, province: auto) = {
  let salutation = if addressee != auto { addressee } else if client.over_16 == none {
    if language == "en" { "To:" } else { "À:" }
  } else if language == "en" {
    if client.over_16 { "To:" } else { "To Parent/Guardian of:" }
  } else { if client.over_16 { "À:" } else { "Au parent ou tuteur de:" } }
  let region = if province == auto { client.province } else { province }
  [#salutation#linebreak()#strong(client.name)#linebreak()#strong(client.address)#linebreak()#strong(client.city), #strong(region) #strong(client.postal_code)]
}

#let address-block(client, language: "en", addressee: auto, province: auto) = {
  component("address")
  context if client.over_16 == none and addressee == auto {
    check("content.address_age_unknown", "warn", "Recipient age is unknown; a neutral addressee is used.", component: "address", page: here().page())
  }
  address-content(client, language: language, addressee: addressee, province: province)
}

#let client-block(notice, window: envelope-preset, font-size: 10pt, min-font-size: 10pt,
  addressee: auto, province: auto, school-label: auto, show-birth-date: true,
  show-school: true, details: "right", spacing: 0pt, border: none) = {
  check-window(window)
  assert(font-size >= min-font-size, message: "Client font is below the declared readable minimum")
  assert(details in ("right", "below"), message: "Client details placement must be right or below")
  set text(size: font-size)
  let lang = notice.language
  let client = notice.client_data
  let school-label = if school-label != auto { school-label } else if lang == "en" { "School" } else { "École" }
  let address = address-content(client, language: lang, addressee: addressee, province: province)
  let info = [
    #if lang == "en" [Client ID:] else [Identifiant du client:] #strong(notice.client_id)
    #if show-birth-date [#linebreak()#if lang == "en" [Date of Birth:] else [Date de naissance:] #strong(long-date(client.date_of_birth_iso, lang, required: false))]
    #if show-school [#linebreak()#school-label: #strong(client.school)]
  ]
  block(width: 100%, breakable: false)[
    #block(width: 0pt, height: 0pt, above: 0pt, below: 0pt)[#metadata(none) <immuknow-client-origin>]
    #context {
    let origin = query(selector(<immuknow-client-origin>).before(here())).last().location().position()
    let dx = calc.max(0pt, window.x - origin.x)
    let dy = calc.max(0pt, window.y - origin.y)
    let size = measure(address, width: window.width - 2 * window.padding)
    let bottom-padding = calc.max(window.padding, window.height - size.height - window.padding)
    v(dy)
    pad(left: dx)[#grid(
      columns: if details == "right" { (window.width, 1fr) } else { (1fr,) }, gutter: spacing,
      block(width: window.width, inset: (top: window.padding, left: window.padding, right: window.padding, bottom: bottom-padding), stroke: border)[#context {
        let position = here().position()
        let bounds = (x_pt: position.x.pt(), y_pt: position.y.pt(), width_pt: size.width.pt(), height_pt: size.height.pt(), page: position.page,
          window_x_pt: window.x.pt(), window_y_pt: window.y.pt(), window_width_pt: window.width.pt(), window_height_pt: window.height.pt(), window_padding_pt: window.padding.pt())
        let overflow = (left_pt: calc.max(0pt, window.x + window.padding - position.x).pt(), top_pt: calc.max(0pt, window.y + window.padding - position.y).pt(),
          right_pt: calc.max(0pt, position.x + size.width - (window.x + window.width - window.padding)).pt(),
          bottom_pt: calc.max(0pt, position.y + size.height - (window.y + window.height - window.padding)).pt())
        let fits = position.page == 1 and overflow.values().all(value => value <= 0.1)
        component("address", measurements: bounds)
        check("layout.address_outside_window", if fits { "pass" } else { "warn" }, if fits { "Address fits the envelope safe area." } else { "Address extends outside the envelope safe area." }, component: "address", page: position.page, measurements: (: ..bounds, ..overflow))
        if client.over_16 == none and addressee == auto { check("content.address_age_unknown", "warn", "Recipient age is unknown; a neutral addressee is used.", component: "address", page: position.page) }
        address
      }],
      block(inset: window.padding)[#context {
        component("client", measurements: (client_id: notice.client_id, page: here().page(), x_pt: here().position().x.pt(), y_pt: here().position().y.pt()))
        [#metadata(notice.client_id) <immuknow-client-id>]
        if show-birth-date and client.date_of_birth_iso == "" { check("content.birth_date_unknown", "warn", "Birth date is unknown.", component: "client", page: here().page()) }
        info
      }],
    )]
  }]
}

#let signature-block(signature: none, name: [], title: [], spacing: 2pt, allow-overflow: false) = {
  [#metadata(none) <immuknow-signature-origin>]
  block(breakable: true)[
    #metadata(none) <immuknow-signature-start>
    #if signature != none [#signature#v(spacing)]
    #name#linebreak()#title
    #metadata(none) <immuknow-signature-end>
  ]
  context {
    let expected-page = query(selector(<immuknow-signature-origin>).before(here())).last().location().page()
    let position = query(selector(<immuknow-signature-start>).before(here())).last().location().position()
    let end = query(selector(<immuknow-signature-end>).before(here())).last().location().position()
    let bounds = (first_page: position.page, last_page: end.page, x_pt: position.x.pt(), y_pt: position.y.pt(), end_y_pt: end.y.pt())
    component("signature", measurements: bounds)
    let fits = position.page == expected-page and end.page == position.page
    check("layout.signature_page", if allow-overflow or fits { "pass" } else { "warn" },
      if fits { "Signature remains with preceding content." } else if allow-overflow { "Signature continuation is allowed." } else { "Signature moved to or continued on another page." }, component: "signature", page: position.page,
      measurements: (expected_page: expected-page, ..bounds))
  }
}

#let notice-style(body, notice: none, language: auto, paper: "us-letter", margins: (top: 1cm, bottom: 2cm, left: 1.75cm, right: 2cm), font: "FreeSans", font-size: 10pt, link-color: blue, privacy: none, paragraph-spacing: 0.55em, page-numbers: true) = {
  assert(notice != none, message: "notice-style requires the prepared notice for document evidence")
  let lang = if language == auto { notice.language } else { language }
  show: notice-page.with(language: lang, paper: paper, margins: margins, font: font, font-size: font-size, page-numbers: page-numbers)
  set par(spacing: paragraph-spacing)
  show link: it => underline(text(fill: link-color, it))
  body
  if privacy != none {
    context {
      let expected-page = here().page()
      v(1fr)
      block(breakable: false, width: 100%)[#context {
        component("privacy", measurements: (page: here().page()))
        check("layout.privacy_page", if here().page() == expected-page { "pass" } else { "warn" }, "Privacy notice placement.", component: "privacy", page: here().page(), measurements: (expected_page: expected-page, actual_page: here().page()))
        set par(justify: true)
        text(size: 7pt, privacy)
      }]
    }
  }
  report(notice)
}

#let notice-section(title, body, logo: none, logo-width: 6cm, title-size: 20pt, fill: black, heading-above: 0.2cm, heading-below: 0.5cm, allow-overflow: false) = {
  assert(type(allow-overflow) == bool, message: "allow-overflow must be boolean")
  pagebreak(weak: true)
  [#metadata(none) <immuknow-section-start>]
  v(heading-above)
  notice-header(logo: logo, logo-width: logo-width, title-size: title-size, fill: fill, title: title)
  v(heading-below)
  body
  [#metadata(none) <immuknow-section-end>]
  context {
      let first-page = query(selector(<immuknow-section-start>).before(here())).last().location().page()
      let last-page = query(selector(<immuknow-section-end>).before(here())).last().location().page()
      component("section", measurements: (title: str(title), first_page: first-page, last_page: last-page))
      check("layout.section_pages", if allow-overflow or first-page == last-page { "pass" } else { "warn" },
        if first-page == last-page { "Section fits on one page." } else if allow-overflow { "Section continuation is allowed." } else { "Section spans multiple pages." },
        component: "section", page: first-page, measurements: (first_page: first-page, last_page: last-page))
  }
}
