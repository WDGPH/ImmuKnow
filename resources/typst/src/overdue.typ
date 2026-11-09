#import "localization.typ": overdue-label, no-records-message
#import "findings.typ": component
#import "ispa.typ": ispa-overdue-diseases
#import "validation.typ": strings

#let items-grid(items, columns, spacing, row-spacing, empty, style, indent) = {
  assert(style in ("bullets", "comma-separated"), message: "style must be bullets or comma-separated")
  if columns == auto { columns = 2 }
  assert(type(columns) == int and columns > 0, message: "columns must be a positive integer or auto")
  assert(empty == none or type(empty) in (str, content), message: "empty must be content, a string, or none")
  if items.len() == 0 { return if empty == none { [] } else { empty } }
  if style == "comma-separated" { return items.join(", ") }
  // Row-major reading order: left to right, then top to bottom.
  grid(columns: (1fr,) * columns, column-gutter: spacing, row-gutter: row-spacing,
    ..items.map(item => list(tight: true, indent: indent, item)))
}

// The source flag is independent of history-table display choices.
#let records-replacement(notice, no-records, language) = {
  assert(no-records == none or no-records == auto or type(no-records) in (str, content),
    message: "no-records must be auto, content, a string, or none")
  if no-records == none { return none }
  assert(type(notice.has_immunization_records) == bool, message: "has_immunization_records must be a boolean")
  if notice.has_immunization_records { return none }
  if no-records == auto { no-records-message(language) } else { no-records }
}

#let overdue-diseases(notice, style: "bullets", columns: auto, indent: 0.8cm, include-dose: false, spacing: 12pt, row-spacing: 4pt, empty: none, no-records: none, ispa-only: false, language: auto, labels: none) = {
  let lang = if language == auto { notice.language } else { language }
  assert(lang in ("en", "fr"), message: "Unsupported notice language")
  assert(type(ispa-only) == bool, message: "ispa-only must be a boolean")
  let entries = if ispa-only { ispa-overdue-diseases(notice) } else { notice.overdue_diseases }
  let doses = include-dose
  assert(type(doses) == bool, message: "include-dose must be a boolean")
  let replacement = records-replacement(notice, no-records, lang)
  component("overdue_diseases", notice: notice)
  if replacement != none { replacement } else {
    let unique = ()
    let keys = ()
    for entry in entries {
      let key = (entry.disease, if doses { entry.dose } else { none })
      if key not in keys {
        keys.push(key)
        unique.push(entry)
      }
    }
    let items = unique.map(entry => overdue-label(entry, doses, lang, labels: labels))
    items-grid(items, columns, spacing, row-spacing, empty, style, indent)
  }
}

// Ignore purely structural and metadata-only content when deciding whether a
// replacement actually gives a reader an alternative to the agent list.
#let visible-replacement(value) = {
  if value == none { return false }
  if type(value) == str { return value.contains(regex("\\S")) }
  if type(value) != content { return false }
  let kind = repr(value.func())
  // This is a syntactic check, not an analysis of painted pixels. Hidden,
  // contextual and structural nodes cannot establish visible alternative text.
  if kind in ("hide", "context", "metadata", "space", "linebreak", "parbreak", "pagebreak", "h", "v") { return false }
  if kind in ("image", "rect", "square", "circle", "ellipse", "polygon", "line", "path") { return true }
  if value.has("children") { return value.children.any(visible-replacement) }
  if value.has("child") { return visible-replacement(value.child) }
  if value.has("body") { return visible-replacement(value.body) }
  if value.has("text") { return value.text.contains(regex("\\S")) }
  false
}

#let agent-measurements(notice, ignore-agents, replacement, replacement-visible, page) = {
  let source = notice.overdue_agents
  let excluded = source.filter(agent => agent in ignore-agents).sorted().dedup()
  let displayed = if replacement != "none" { () } else {
    source.filter(agent => agent not in ignore-agents).fold((), (items, agent) =>
      if agent in items { items } else { items + (agent,) })
  }
  (page: page, source_agents: source, source_count: source.len(), excluded_agents: excluded,
    displayed_agents: displayed, displayed_count: displayed.len(), replacement: replacement,
    replacement_visible: replacement-visible)
}

#let overdue-agents(notice, style: "bullets", columns: auto, indent: 0.8cm, spacing: 12pt, row-spacing: 4pt, empty: none, no-records: none, ispa-only: false, language: auto, ignore-agents: ()) = {
  assert(type(ispa-only) == bool, message: "ispa-only must be a boolean")
  assert(not ispa-only, message: "ispa-only is not supported for overdue-agents; use overdue-diseases for ISPA-only display.")
  strings(ignore-agents, "ignore-agents")
  let lang = if language == auto { notice.language } else { language }
  assert(lang in ("en", "fr"), message: "Unsupported notice language")
  let replacement = records-replacement(notice, no-records, lang)
  context {
    let state = if replacement == none { "none" } else { "no_records" }
    let evidence = agent-measurements(notice, ignore-agents, state, if replacement == none { false } else { visible-replacement(replacement) }, here().page())
    component("overdue_agents", measurements: evidence, notice: notice)
    if replacement != none { replacement } else {
      items-grid(evidence.displayed_agents, columns, spacing, row-spacing, empty, style, indent)
    }
  }
}

#let agent-alternative(notice, body, ignore-agents: ()) = {
  strings(ignore-agents, "ignore-agents")
  context {
    let evidence = agent-measurements(notice, ignore-agents, "authored_alternative", visible-replacement(body), here().page())
    component("overdue_agents", measurements: evidence, notice: notice)
    body
  }
}
