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
#let report-schema = json("../report-v2.json")
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
  let invalid = web-urls.any(url => not url.contains(regex("(?i)^https://[^\\s/?#]+([/?#]|$)")) or url.contains(regex("\\s")))
  checks.push((code: "content.link_https", stage: "render",
    status: if web-urls.len() == 0 { "not_applicable" } else if invalid { "warn" } else { "pass" },
    message: if web-urls.len() == 0 { "No web links were placed." }
      else if invalid { "A web link is missing HTTPS or a host, or contains spaces." }
      else { "Web links use HTTPS and include a host." }))
  checks.push((code: "content.multiple_links", stage: "render",
    status: if destinations.len() == 0 { "not_applicable" } else if destinations.len() > 1 { "warn" } else { "pass" },
    message: if destinations.len() == 0 { "No links were placed." }
      else if destinations.len() > 1 { "This notice has " + str(destinations.len()) + " different link destinations. Check that each is intended." }
      else { "One link destination was placed." }))
  [#metadata((
    schema_version: report-schema.properties.schema_version.const,
    notice: notice,
    identity: (row_key: notice.row_key, template: notice.template, client_id: notice.client_id, version_id: notice.version_id, language: notice.language),
    page_count: counter(page).final().first(), components: components, checks: checks,
    qr_urls: qr-urls,
    measurements: measurements,
  )) <immuknow-report>]
}
