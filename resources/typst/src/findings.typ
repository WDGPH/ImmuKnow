// Findings are metadata attached only to content that is actually placed.
#let check(code, status, message, component: none, page: none, measurements: none) = {
  assert(status in ("pass", "warn", "fail", "not_applicable", "not_run"), message: "Unknown check status")
  let value = (code: code, stage: "render", status: status, message: message)
  if component != none { value.insert("component", component) }
  if page != none { value.insert("page", page) }
  if measurements != none { value.insert("measurements", measurements) }
  [#metadata(value) <immuknow-check>]
}
#let component(name, measurements: (:), url: none, notice: none) = {
  if notice != none {
    measurements.insert("row_key", notice.row_key)
    measurements.insert("client_id", notice.client_id)
  }
  [#metadata((name: name, measurements: measurements, url: url, notice: notice)) <immuknow-component>]
}
#let report-schema = json("../report.json")
#let known-components = report-schema.properties.components.properties.keys()

// Query the final placed elements, never a state updated during layout iterations.
#let report(notice) = context {
  let evidence = query(<immuknow-component>).map(it => it.value)
  let components = (:)
  let measurements = (:)
  let checks = query(<immuknow-check>).map(it => it.value)
  for name in known-components {
    let placed = evidence.filter(it => it.name == name)
    components.insert(name, placed.len() > 0)
    if placed.len() == 0 {
      checks.push((code: "component." + name + ".absent", stage: "render", status: "not_applicable", message: "Component was not used.", component: name))
    } else {
      measurements.insert(name, placed.map(it => {
        let value = it.measurements
        if it.notice != none { value.insert("source_matches", it.notice == notice) }
        value
      }))
    }
  }
  if components.address {
    let addresses = measurements.address
    let defined = addresses.any(area => "window_width_pt" in area)
    checks.push((code: "layout.envelope_window_missing", stage: "render",
      status: if defined { "pass" } else { "warn" }, component: "address", page: addresses.first().page,
      message: if defined { "An envelope window was specified." } else { "No envelope window was specified; address placement could not be checked." }))
  }
  let qr-urls = evidence.filter(it => it.url != none).map(it => it.url).dedup()
  let link-urls = evidence.filter(it => it.name == "link").map(it => it.measurements.url)
  let destinations = (qr-urls + link-urls).dedup()
  let web-urls = (qr-urls + link-urls.filter(url => not url.contains(regex("(?i)^(mailto|tel):")))).dedup()
  let invalid-web-urls = web-urls.filter(url => not url.contains(regex("(?i)^https://[^\\s/?#]+([/?#]|$)")) or url.contains(regex("\\s")))
  let https-check = (code: "content.link_https", stage: "render",
    status: if web-urls.len() == 0 { "not_applicable" } else if invalid-web-urls.len() > 0 { "warn" } else { "pass" },
    message: if web-urls.len() == 0 { "No web links were placed." }
      else if invalid-web-urls.len() > 0 { "A web link is missing HTTPS or a host, or contains spaces." }
      else { "Web links use HTTPS and include a host." })
  if invalid-web-urls.len() > 0 {
    https-check.insert("subjects", invalid-web-urls.sorted().dedup().map(url => (kind: "url", urls: (url,))))
  }
  checks.push(https-check)
  // Basic address checks; these do not test whether a destination responds.
  let valid-destination(url) = {
    if url.contains(regex("[\\s\\p{Cc}]")) { return false }
    if url.contains(regex("(?i)^https://[^/?#@:]+(:[0-9]+)?([/?#]|$)")) { return true }
    if url.contains(regex("(?i)^mailto:[^@/?#]+@[^@/?#]+(\\?[^#]*)?$")) { return true }
    url.contains(regex("(?i)^tel:\\+?[0-9]([0-9().-]*[0-9])?(;ext=[0-9]+)?$"))
  }
  let invalid-destinations = destinations.filter(url => not valid-destination(url))
  let destination-check = (code: "content.link_destination", stage: "render",
    status: if destinations.len() == 0 { "not_applicable" } else if invalid-destinations.len() > 0 { "warn" } else { "pass" },
    message: if destinations.len() == 0 { "No links were placed." }
      else if invalid-destinations.len() > 0 { "Use a complete HTTPS, mailto or tel address without spaces or control characters. Check: " + invalid-destinations.join(", ") }
      else { "Link destinations use HTTPS, mailto or tel address formats." })
  if invalid-destinations.len() > 0 {
    destination-check.insert("subjects", invalid-destinations.sorted().dedup().map(url => (kind: "url", urls: (url,))))
  }
  checks.push(destination-check)
  let multiple-check = (code: "content.multiple_links", stage: "render",
    status: if destinations.len() == 0 { "not_applicable" } else if destinations.len() > 1 { "warn" } else { "pass" },
    message: if destinations.len() == 0 { "No links were placed." }
      else if destinations.len() > 1 { "This notice has " + str(destinations.len()) + " different link destinations. Check that each is intended." }
      else { "One link destination was placed." })
  if destinations.len() > 1 {
    multiple-check.insert("subjects", ((kind: "url_set", urls: destinations.sorted().dedup()),))
  }
  checks.push(multiple-check)
  [#metadata((
    schema_version: report-schema.properties.schema_version.const,
    notice: notice,
    identity: (row_key: notice.row_key, template: notice.template, client_id: notice.client_id, version_id: notice.version_id, language: notice.language),
    page_count: counter(page).final().first(), components: components, checks: checks,
    qr_urls: qr-urls,
    measurements: measurements,
  )) <immuknow-report>]
}
