#import "../vendor/codetastic/codetastic.typ" as codes
#import "qr-style.typ": draw-qr
#import "findings.typ": check, component

// Use the supplied link, a fixed URL, or a function that builds a URL for this notice.
#let qr-code(notice, enabled: true, url: none, width: 3cm, error-correction: auto,
  foreground: black, background: white, module-shape: "square", corner-style: "square",
  logo: none, logo-size: 30%, logo-padding: 0.3mm,
) = {
  assert(type(enabled) == bool, message: "QR enabled must be true or false")
  if not enabled { return [] }
  assert(url != none and url != auto, message: "QR url must be an explicit string or notice function")
  let destination = if type(url) == function { url(notice) } else { url }
  assert(type(destination) == str and destination != "", message: "QR destination must be a nonempty URL")
  assert(type(width) == length and width > 0pt, message: "QR width must be a positive length")
  assert(module-shape in ("square", "dots", "rounded"), message: "QR module-shape must be square, dots, or rounded")
  assert(corner-style in ("square", "rounded"), message: "QR corner-style must be square or rounded")
  assert(type(foreground) == color and type(background) == color, message: "QR foreground and background must be colours")
  assert(type(logo-size) == ratio and logo-size >= 5% and logo-size <= 30%, message: "QR logo-size must be between 5% and 30%")
  assert(logo == none or type(logo) in (content, dictionary), message: "QR logo must be image content, an image/mask dictionary, or none")
  assert(type(logo-padding) == length and logo-padding >= 0pt and logo-padding <= 1mm, message: "QR logo-padding must be between 0mm and 1mm")
  let mask = if type(logo) == dictionary { logo.at("mask") } else { none }
  let picture = if type(logo) == dictionary { logo.at("image") } else { logo }
  assert(picture == none or type(picture) == content, message: "QR logo image must be content")
  if mask != none {
    assert(type(mask) == dictionary and mask.at("size", default: 0) == 128 and type(mask.at("runs", default: none)) == array, message: "QR image mask must have size 128 and an array of runs")
    assert(mask.runs.len() <= 8192, message: "QR image mask has too many runs")
    for run in mask.runs {
      assert(type(run) == array and run.len() == 3 and run.all(v => type(v) == int), message: "QR image mask runs must contain three integers")
      let (y, start, end) = run
      assert(y >= 0 and y < 128 and start >= 0 and end <= 128 and start < end, message: "QR image mask run is out of bounds")
    }
  }
  let ecl = if error-correction == auto { if logo == none { "l" } else { "h" } } else { error-correction }
  assert(logo == none or ecl == "h", message: "QR centre images require error-correction: h (or auto)")
  let styled = module-shape != "square" or corner-style != "square" or logo != none
  component("qr", notice: notice, url: destination)
  link(destination, codes.qrcode(destination, width: width, quiet-zone: 4, ecl: ecl,
    colors: (background, foreground),
    draw: if styled { draw-qr.with(module-shape: module-shape, corner-style: corner-style, logo: picture, logo-size: logo-size, logo-padding: logo-padding, logo-mask: mask) } else { none },
  ))
}

// Percent-encode UTF-8 bytes once, preserving only RFC 3986 unreserved characters.
#let url-encode(value) = {
  assert(type(value) == str, message: "URL component must be a string")
  let digits = "0123456789ABCDEF"
  array(bytes(value)).map(byte => {
    if (byte >= 65 and byte <= 90) or (byte >= 97 and byte <= 122) or (byte >= 48 and byte <= 57) or byte in (45, 46, 95, 126) { str.from-unicode(byte) }
    else { "%" + digits.at(calc.floor(byte / 16)) + digits.at(calc.rem(byte, 16)) }
  }).join()
}
#let query-url(base, values) = {
  assert(type(base) == str and type(values) == dictionary, message: "query-url needs a URL and a dictionary of strings")
  if values.len() == 0 { return base }
  let parts = base.split("#")
  let address = parts.first()
  let fragment = if parts.len() > 1 { "#" + parts.slice(1).join("#") } else { "" }
  let query = values.pairs().map(pair => url-encode(pair.at(0)) + "=" + url-encode(pair.at(1))).join("&")
  address + (if address.contains("?") { "&" } else { "?" }) + query + fragment
}

// Record a placed external link for comparison with the PDF destination.
#let notice-link(destination, keep-together: true, ..body) = {
  assert(type(destination) == str and destination != "", message: "Link destination must be nonempty text")
  assert(type(keep-together) == bool, message: "Link keep-together must be boolean")
  if keep-together { context {
    let owner = here()
    // Measure the enclosing line without putting the eventual fallback in a box.
    box(layout(size => box(width: 0pt, height: 0pt)[
      #metadata((owner: owner, size: size)) <immuknow-link-space>
    ]))
    let spaces = query(<immuknow-link-space>).filter(it => it.value.owner == owner)
    let available = if spaces.len() > 0 { spaces.first().value.size } else { (width: 0pt, height: 0pt) }
    let linked = link(destination, ..body)
    let natural = measure(linked)
    let fits = natural.width <= available.width + 0.1pt
    let placed = context {
      component("link", measurements: (page: here().page(), url: destination))
      check("layout.link_width", if fits { "pass" } else { "warn" },
        if fits { "Link text fits within the available line width." }
        else { "Link text exceeds the available line width and was allowed to wrap." },
        component: "link", page: here().page())
      linked
    }
    // Explicit multiline labels must also be able to continue onto another page.
    if fits and natural.height <= available.height { box(placed) } else { placed }
  } } else { context {
    component("link", measurements: (page: here().page(), url: destination))
    link(destination, ..body)
  } }
}
