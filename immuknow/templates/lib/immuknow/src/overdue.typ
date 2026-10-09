#import "localization.typ": overdue-label

#let items-grid(items, columns, spacing, row-spacing, empty) = {
  if columns == auto { columns = 2 }
  assert(type(columns) == int and columns > 0, message: "columns must be a positive integer or auto")
  assert(empty == none or type(empty) in (str, content), message: "empty must be content, a string, or none")
  if items.len() == 0 { return if empty == none { [] } else { empty } }
  // Row-major reading order: left to right, then top to bottom.
  grid(columns: (1fr,) * columns, column-gutter: spacing, row-gutter: row-spacing,
    ..items.map(item => list(tight: true, item)))
}

#let overdue-diseases(notice, columns: auto, include-dose: auto, spacing: 12pt, row-spacing: 4pt, empty: none, language: auto, labels: none) = {
  let lang = if language == auto { notice.language } else { language }
  assert(lang in ("en", "fr"), message: "Unsupported notice language")
  let doses = if include-dose == auto { notice.rendering_defaults.include_dose } else { include-dose }
  assert(type(doses) == bool, message: "include-dose must be a boolean or auto")
  let items = notice.overdue_diseases.map(entry => overdue-label(entry, doses, lang, labels: labels))
  items-grid(items, columns, spacing, row-spacing, empty)
}

#let overdue-agents(notice, columns: auto, spacing: 12pt, row-spacing: 4pt, empty: none, language: auto) = {
  let lang = if language == auto { notice.language } else { language }
  assert(lang in ("en", "fr"), message: "Unsupported notice language")
  items-grid(notice.overdue_agents, columns, spacing, row-spacing, empty)
}
