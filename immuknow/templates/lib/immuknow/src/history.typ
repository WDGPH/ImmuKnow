#import "validation.typ": strings
#import "localization.typ": disease-label, table-labels
#import "findings.typ": component, check

// Project preserved facts only after applying the author's display options.
#let history-view(notice, diseases: (), ignore-agents: (), include-other: true, show-validity: false, omit-invalid: false) = {
  strings(diseases, "diseases", unique: true)
  assert("Other" not in diseases, message: "Use include-other instead of adding Other to diseases")
  strings(ignore-agents, "ignore-agents")
  assert(type(include-other) == bool, message: "include-other must be a boolean or auto")
  assert(type(show-validity) == bool, message: "show-validity must be a boolean or auto")
  assert(type(omit-invalid) == bool, message: "omit-invalid must be a boolean")
  let columns = diseases + if include-other { ("Other",) } else { () }
  let items = notice.history.filter(item => item.agent not in ignore-agents and (not omit-invalid or item.validity != "invalid"))
  let dates = items.map(item => item.date_given).dedup()
  let rows = ()
  for date in dates {
    let on-date = items.filter(item => item.date_given == date)
    // Separating all status groups keeps unknown from masking known conflicts.
    let groups = if show-validity {
      ("valid", "invalid", "unknown").map(status => on-date.filter(item => item.validity == status)).filter(group => group.len() > 0)
    } else { (on-date,) }
    for (index, group) in groups.enumerate() {
      let marks = (:)
      for item in group {
        for disease in item.diseases {
          if disease in diseases { marks.insert(disease, if show-validity { item.validity } else { "recorded" }) }
        }
        if include-other and (item.diseases.len() == 0 or item.diseases.any(d => d not in diseases)) {
          marks.insert("Other", if show-validity { item.validity } else { "recorded" })
        }
      }
      rows.push((date: date, rowspan: if index == 0 { groups.len() } else { 0 }, agents: group.map(item => item.display_name), marks: marks))
    }
  }
  (columns: columns, rows: rows, show-validity: show-validity)
}

// Completed calendar months, treating month-end as the anniversary when needed.
#let age-at-vaccination(birth, given, language) = {
  if birth == none or birth == "" or given < birth { return "—" }
  let born = birth.split("-").map(int)
  let dose = given.split("-").map(int)
  let leap = calc.rem(dose.at(0), 4) == 0 and (calc.rem(dose.at(0), 100) != 0 or calc.rem(dose.at(0), 400) == 0)
  let days = (31, if leap { 29 } else { 28 }, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31).at(dose.at(1) - 1)
  let months = (dose.at(0) - born.at(0)) * 12 + dose.at(1) - born.at(1)
  if dose.at(2) < calc.min(born.at(2), days) { months -= 1 }
  let years = calc.floor(months / 12)
  let remainder = calc.rem(months, 12)
  if language == "fr" { str(years) + " a " + str(remainder) + " m" }
  else { str(years) + " yr " + str(remainder) + " mo" }
}

#let immunization-history(
  notice, diseases: (), ignore-agents: (), include-other: true,
  show-validity: false, omit-invalid: false, show-age: false, age-width: 64pt, min-rows: 5, font-size: 11pt,
  date-width: 75pt, disease-width: 12pt, agent-width: 1fr,
  inset: (x: 1pt, y: 2pt), stroke: 0.5pt, language: auto, labels: none,
  heading-size: auto, indicator-font: "FreeMono", indicator-size: auto, indicator-offset: (x: 0pt, y: 0pt),
) = {
  let lang = if language == auto { notice.language } else { language }
  let headings = table-labels(lang)
  assert(type(min-rows) == int and min-rows >= 0, message: "min-rows must be a nonnegative integer")
  assert(type(font-size) == length and font-size > 0pt, message: "font-size must be a positive length")
  heading-size = if heading-size == auto { font-size } else { heading-size }
  indicator-size = if indicator-size == auto { font-size } else { indicator-size }
  assert(type(heading-size) == length and heading-size > 0pt, message: "heading-size must be a positive length or auto")
  assert(type(indicator-font) == str and indicator-font != "", message: "indicator-font must name a typeface")
  assert(type(indicator-size) == length and indicator-size > 0pt, message: "indicator-size must be a positive length or auto")
  assert(type(indicator-offset) == dictionary and type(indicator-offset.at("x", default: none)) == length and type(indicator-offset.at("y", default: none)) == length,
    message: "indicator-offset needs x and y lengths")
  let view = history-view(notice, diseases: diseases, ignore-agents: ignore-agents, include-other: include-other, show-validity: show-validity, omit-invalid: omit-invalid)
  assert(type(show-age) == bool, message: "show-age must be a boolean")
  let count = view.columns.len() + 2 + if show-age { 1 } else { 0 }
  let widths = (date-width,) + if show-age { (age-width,) } else { () } + view.columns.map(_ => disease-width) + (agent-width,)
  let cells = ()
  let marker(status) = if status in ("valid", "recorded") { "⬤" } else if status == "invalid" { "○" } else { "?" }
  let indicator(status) = box(text(font: indicator-font, size: indicator-size, top-edge: "bounds", bottom-edge: "bounds", marker(status)))
  for row in view.rows {
    if row.rowspan > 0 {
      cells.push(table.cell(rowspan: row.rowspan, align: center + horizon, box(row.date)))
      if show-age {
        cells.push(table.cell(rowspan: row.rowspan, align: right + horizon, box(age-at-vaccination(notice.client_data.date_of_birth_iso, row.date, lang))))
      }
    }
    for column in view.columns {
      cells.push(if column in row.marks { move(dx: indicator-offset.x, dy: indicator-offset.y, indicator(row.marks.at(column))) } else { "" })
    }
    cells.push(row.agents.join(", "))
  }
  for _ in range(calc.max(0, min-rows - view.rows.len())) {
    cells += range(count).map(_ => [#v(0.8em)])
  }
  let footer(body) = table.cell(colspan: count, stroke: none, align: left, body)
  set text(size: font-size, lang: lang, region: "CA")
  context {
    component("history", measurements: (administrations: notice.history.len(), displayed_rows: view.rows.len(), unparsed_entries: notice.unparsed_history.len(), page: here().page()))
    if show-validity {
      let complete = notice.validity_coverage == "all_present" and notice.history.all(item => item.validity != "unknown")
      check("content.history_validity", if complete { "pass" } else { "warn" }, if complete { "Administration validity is known." } else { "Validity is mixed or unknown; unknown administrations have a distinct mark." }, component: "history", page: here().page())
    }
    if show-age and notice.client_data.date_of_birth_iso == "" { check("content.history_age_unknown", "warn", "Birth date is unknown; vaccination ages are unavailable.", component: "history", page: here().page()) }
    if notice.unparsed_history.len() > 0 { check("content.history_unparsed", "warn", "Unparsed history entries are displayed below the table.", component: "history", page: here().page(), measurements: (unparsed_entries: notice.unparsed_history.len())) }
  }
  layout(size => {
    if type(date-width) == length and type(disease-width) == length {
      let minimum = date-width + view.columns.len() * disease-width + 40pt + if show-age { age-width } else { 0pt }
      context check("layout.history_width", if size.width >= minimum { "pass" } else { "warn" }, "History column width compared with available space.", component: "history", page: here().page(), measurements: (available_width_pt: size.width.pt(), minimum_width_pt: minimum.pt()))
    }
    table(
    columns: widths, inset: inset, stroke: stroke,
    align: (x, y) => if x == 0 or x == count - 1 { left + horizon } else { center + horizon },
    table.header(repeat: true,
      table.cell(align: center + horizon, text(size: heading-size, headings.date)),
      ..if show-age { (table.cell(align: center + horizon, text(size: heading-size, headings.age)),) } else { () },
      ..view.columns.map(column => table.cell(align: center + bottom, rotate(-90deg, reflow: true, box(text(size: heading-size, top-edge: "bounds", bottom-edge: "bounds", disease-label("diseases_chart", column, lang, labels: labels)))))),
      table.cell(align: center + horizon, text(size: heading-size, headings.vaccine)),
    ),
    ..cells,
    footer(headings.unspecified),
    ..if view.show-validity {
      (footer(grid(columns: (disease-width, 1fr), gutter: 4pt, align: (center + horizon, left + horizon), indicator("valid"), headings.valid)),) + if omit-invalid { () } else { (footer(grid(columns: (disease-width, 1fr), gutter: 4pt, align: (center + horizon, left + horizon), indicator("invalid"), headings.invalid)),) }
    } else { () },
    ..if view.show-validity { (footer(grid(columns: (disease-width, 1fr), gutter: 4pt, align: (center + horizon, left + horizon), indicator("unknown"), headings.unknown)),) } else { () },
    )
  })
  if notice.unparsed_history.len() > 0 {
    block[
      #strong(if lang == "fr" { "Entrées non interprétées" } else { "Unparsed entries" })
      #for entry in notice.unparsed_history [#linebreak()#entry]
    ]
  }
}
