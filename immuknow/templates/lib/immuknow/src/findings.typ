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
  [#metadata((
    schema_version: report-schema.properties.schema_version.const,
    notice: notice,
    identity: (row_key: notice.row_key, template: notice.template, client_id: notice.client_id, version_id: notice.version_id, language: notice.language),
    page_count: counter(page).final().first(), components: components, checks: checks,
    qr_urls: evidence.filter(it => it.url != none).map(it => it.url).dedup(),
    measurements: measurements,
  )) <immuknow-report>]
}
