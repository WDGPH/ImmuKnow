#import "localization.typ": overdue-label, no-records-message
#import "findings.typ": component
#import "ispa.typ": ispa-overdue-diseases

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
    let items = entries.map(entry => overdue-label(entry, doses, lang, labels: labels))
    items-grid(items, columns, spacing, row-spacing, empty, style, indent)
  }
}

#let overdue-agents(notice, style: "bullets", columns: auto, indent: 0.8cm, spacing: 12pt, row-spacing: 4pt, empty: none, no-records: none, ispa-only: false, language: auto) = {
  assert(type(ispa-only) == bool, message: "ispa-only must be a boolean")
  assert(not ispa-only, message: "ispa-only is not supported for overdue-agents; use overdue-diseases for ISPA-only display.")
  let lang = if language == auto { notice.language } else { language }
  assert(lang in ("en", "fr"), message: "Unsupported notice language")
  let replacement = records-replacement(notice, no-records, lang)
  component("overdue_agents", notice: notice)
  if replacement != none { replacement } else {
    items-grid(notice.overdue_agents, columns, spacing, row-spacing, empty, style, indent)
  }
}
