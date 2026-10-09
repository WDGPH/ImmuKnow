#import "validation.typ": strings
#import "localization.typ": disease-label, table-labels, long-date

#let inherit(value, notice, name) = if value == auto { notice.rendering_defaults.at(name) } else { value }

// Project preserved facts only after applying the author's display options.
#let history-view(notice, diseases: auto, ignore-agents: auto, include-other: auto, show-validity: auto) = {
  diseases = inherit(diseases, notice, "diseases")
  ignore-agents = inherit(ignore-agents, notice, "ignore_agents")
  include-other = inherit(include-other, notice, "include_other")
  show-validity = inherit(show-validity, notice, "show_validity")
  strings(diseases, "diseases", unique: true)
  assert("Other" not in diseases, message: "Use include-other instead of adding Other to diseases")
  strings(ignore-agents, "ignore-agents")
  assert(type(include-other) == bool, message: "include-other must be a boolean or auto")
  assert(type(show-validity) == bool, message: "show-validity must be a boolean or auto")
  assert(not show-validity or notice.validity_coverage != "mixed",
    message: "Cannot display validity markers reliably: mixed cohort validity coverage. Disable show-validity or correct the source data.")
  let columns = diseases + if include-other { ("Other",) } else { () }
  let items = notice.history.filter(item => item.agent not in ignore-agents)
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

#let immunization-history(
  notice, diseases: auto, ignore-agents: auto, include-other: auto,
  show-validity: auto, min-rows: 5, font-size: 11pt,
  date-width: 75pt, disease-width: 20pt, agent-width: 1fr,
  inset: 4pt, stroke: 0.5pt, language: auto, labels: none,
) = {
  let lang = if language == auto { notice.language } else { language }
  let headings = table-labels(lang)
  assert(type(min-rows) == int and min-rows >= 0, message: "min-rows must be a nonnegative integer")
  assert(type(font-size) == length and font-size > 0pt, message: "font-size must be a positive length")
  let view = history-view(notice, diseases: diseases, ignore-agents: ignore-agents, include-other: include-other, show-validity: show-validity)
  let count = view.columns.len() + 2
  let widths = (date-width,) + view.columns.map(_ => disease-width) + (agent-width,)
  let cells = ()
  let marker(status) = if status in ("valid", "recorded") { "⬤" } else if status == "invalid" { "○" } else { "?" }
  for row in view.rows {
    if row.rowspan > 0 { cells.push(table.cell(rowspan: row.rowspan, long-date(row.date, lang))) }
    for column in view.columns {
      cells.push(if column in row.marks { marker(row.marks.at(column)) } else { "" })
    }
    cells.push(row.agents.join(", "))
  }
  for _ in range(calc.max(0, min-rows - view.rows.len())) {
    cells += range(count).map(_ => [#v(0.8em)])
  }
  let footer(body) = table.cell(colspan: count, stroke: none, align: left, body)
  set text(size: font-size, lang: lang, region: "CA")
  layout(size => {
    if type(date-width) == length and type(disease-width) == length {
      assert(size.width >= date-width + view.columns.len() * disease-width + 40pt,
        message: "History columns exceed available width; select fewer diseases, widen the page, or adjust column widths")
    }
    table(
    columns: widths, inset: inset, stroke: stroke,
    align: (x, y) => if x == 0 or x == count - 1 { left } else { center },
    table.header(repeat: true,
      headings.date,
      ..view.columns.map(column => rotate(-90deg, reflow: true, disease-label("diseases_chart", column, lang, labels: labels))),
      headings.vaccine,
    ),
    ..cells,
    footer(headings.unspecified),
    ..if view.show-validity {
      (footer([⬤ #headings.valid]), footer([○ #headings.invalid]), footer([? #headings.unknown]))
    } else { (footer([⬤ #headings.recorded]),) },
    )
  })
}
