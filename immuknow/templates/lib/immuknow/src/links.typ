#import "findings.typ": check, component

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
