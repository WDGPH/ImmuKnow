// Findings are metadata attached only to content that is actually placed.
#let check(code, status, message, component: none, page: none, measurements: none) = {
  assert(status in ("pass", "warn", "fail", "not_applicable", "not_run"), message: "Unknown check status")
  let value = (code: code, stage: "render", status: status, message: message)
  if component != none { value.insert("component", component) }
  if page != none { value.insert("page", page) }
  if measurements != none { value.insert("measurements", measurements) }
  [#metadata(value) <immuknow-check>]
}
#let component(name, measurements: (:), url: none) = [#metadata((name: name, measurements: measurements, url: url)) <immuknow-component>]
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
      measurements.insert(name, placed.map(it => it.measurements))
    }
  }
  [#metadata((
    schema_version: report-schema.properties.schema_version.const,
    identity: (row_key: notice.row_key, template: notice.template, client_id: notice.client_id, version_id: notice.version_id, language: notice.language),
    page_count: counter(page).final().first(), components: components, checks: checks,
    qr_urls: evidence.filter(it => it.url != none).map(it => it.url).dedup(),
    measurements: measurements,
  )) <immuknow-report>]
}
