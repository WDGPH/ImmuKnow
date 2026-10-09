#import "/templates/presentation.typ" as presentation

#let vax_valid = ("⬤")
#let vax_invalid = ("○")

#let validity-dot(status, show-validity-markers: false) = {
  if not show-validity-markers {
    vax_valid
  } else if status == "invalid" or status == "Invalid" or status == false {
    vax_invalid
  } else {
    vax_valid
  }
}


// Custom colours
#let wdgteal = rgb(0, 85, 104)
#let darkred = rgb(153, 0, 0)
#let darkblue = rgb(0, 83, 104)
#let linkcolor = rgb(0, 0, 238)

#let header_info_cim(
  logo,
  logo_width,
  fill_colour,
  custom_size,
  custom_msg
) = {
  grid(
  
    columns: (50%,50%), 
    gutter: 5%, 
    [#image(logo, width: logo_width)],
    [#set align(center + bottom)
      #text(size: custom_size, fill: fill_colour)[*#custom_msg*]]
    
  )
}

#let client_info_tbl_en(
  equal_split: true,
  vline: true, 
  client_data,
  client_id,
  font_size,
  school_type,
  envelope_window_height,
  border: true,
) = {
  // Define column widths based on equal_split
  let columns = if equal_split {
    (0.5fr, 0.5fr)
  } else {
    (0.4fr, 0.6fr)
  }

  let vline_stroke = if vline { 1pt + black } else { none }
  let outline_stroke = if border { 1pt + black } else { none }

  let address_to = if client_data.over_16 {
    "To:"
  } else {
    "To Parent/Guardian of:"
  }

  // Content for the first column
  let col1_content = align(left)[
    #address_to #linebreak()
    *#client_data.name* #linebreak()
    *#client_data.address* #linebreak()
    *#client_data.city*, *Ontario* *#client_data.postal_code*
  ]

  // Content for the second column
  let col2_content = align(left)[
    Client ID: #smallcaps[*#client_id*] #linebreak()
    Date of Birth: *#presentation.long-date(client_data.date_of_birth_iso, "en", required: false)* #linebreak()
    #school_type: #smallcaps[*#client_data.school*]
  ]

  // Build the table content
  let table_content = align(center)[
    #table(
      stroke: outline_stroke,
      columns: columns,
      rows: (envelope_window_height),
      inset: font_size,
      col1_content,
      table.vline(stroke: vline_stroke),
      col2_content,
    )
  ]

  // Render table with embedded height measurement for envelope validation
  // Invisible marker will be searchable in PDF but not visible to readers
  context {
    let size = measure(table_content)
    let h_pt = size.height.pt()
    
    // Render the table with embedded measurement marker
    [
      #table_content
      #text(size: 0.1pt, fill: white)[MEASURE_CONTACT_HEIGHT:#str(h_pt)]
    ]
  }
}

#let client_info_tbl_fr(
  equal_split: true,
  vline: true, 
  client_data,
  client_id,
  font_size,
  school_type,
  envelope_window_height,
  border: true,
) = {
  // Define column widths based on equal_split
  let columns = if equal_split {
    (0.5fr, 0.5fr)
  } else {
    (0.4fr, 0.6fr)
  }

  let vline_stroke = if vline { 1pt + black } else { none }
  let outline_stroke = if border { 1pt + black } else { none }

  let address_to = if client_data.over_16 {
    "Au:"
  } else {
    "Au parent ou tuteur de:"
  }

  // Content for the first column
  let col1_content = align(left)[
    #address_to #linebreak()
    *#client_data.name* #linebreak()
    *#client_data.address* #linebreak()
    *#client_data.city*, *Ontario* *#client_data.postal_code*
  ]

  // Content for the second column
  let col2_content = align(left)[
    Identifiant du client: #smallcaps[*#client_id*] #linebreak()
    Date de naissance: *#presentation.long-date(client_data.date_of_birth_iso, "fr", required: false)* #linebreak()
    #school_type: #smallcaps[*#client_data.school*]
  ]

  // Build the table content
  let table_content = align(center)[
    #table(
      stroke: outline_stroke,
      columns: columns,
      rows: (envelope_window_height),
      inset: font_size,
      col1_content,
      table.vline(stroke: vline_stroke),
      col2_content,
    )
  ]

  // Render table with embedded height measurement for envelope validation
  // Invisible marker will be searchable in PDF but not visible to readers
  context {
    let size = measure(table_content)
    let h_pt = size.height.pt()
    
    // Render the table with embedded measurement marker
    [
      #table_content
      #text(size: 0.1pt, fill: white)[MEASURE_CONTACT_HEIGHT:#str(h_pt)]
    ]
  }
}

#let client_immunization_list(
  immunizations_due
) = {

  let list-content = {
    for vaccine in immunizations_due [
      - *#vaccine*
    ]
  }
  
  let num_elements = immunizations_due.len()
  set list(indent: 0.8cm)
  if num_elements > 4 {   
    align(center, block(
      height: 60pt,
      width: 545pt,
      columns(3)[ 
      #align(left + top)[
      #for vaccine in immunizations_due [
        - *#vaccine*
      ]
    ]
    ]
  ))
  } else {
    [#list-content]
  }
  
}

#let signature(
  signature, 
  name, 
  title
) = {

  image(signature, width: 3cm)
  
  text(name)
  linebreak()
  text(title)
  
}

#let immunization-table(
  min_rows, 
  data, 
  diseases,
  font_size,
  lang,
  show_validity_markers,
) = {

  let num_padded = min_rows - data.len()
  let table_rows = ()
  let empty_rows_content = ()
  let dynamic_headers = ()
  let headings = presentation.table-labels(lang)
  let date_given = headings.date
  let vaccine_s = headings.vaccine
  let end_msg = headings.unspecified
  let valid_label = headings.valid
  let invalid_label = headings.invalid

  if data.len() > 0 {
    for record in data {
      let row_cells = ()

      // Date cell: merged across split rows for the same date
      if record.date_rowspan > 1 {
        row_cells.push(table.cell(rowspan: record.date_rowspan)[#record.date_given])
      } else if record.date_rowspan == 1 {
        row_cells.push(record.date_given)
      }
      // date_rowspan == 0 means this is a continuation row; omit the date cell

      // Populate disease columns via direct dict lookup on record.columns
      for disease_name in diseases {
        let cell_content = ""
        if disease_name in record.columns {
          let status = record.columns.at(disease_name)
          cell_content = validity-dot(status, show-validity-markers: show_validity_markers)
        }
        row_cells.push(cell_content)
      }

      // Vaccine(s) column
      let vaccine_content = if type(record.vaccines) == array {
        record.vaccines.join(", ")
      } else {
        record.vaccines
      }
      row_cells.push(vaccine_content)

      table_rows.push(row_cells)
    }
  }

  if num_padded > 0 {
     for _ in range(num_padded) {
  table_rows.push(("", "", "", "", "", "", "", "", "", "", "", "", "", ""," "))
  } 
  }

  dynamic_headers.push([#align(bottom + left)[#text(size: font_size)[#date_given]]])

  for disease in diseases {
    let heading = presentation.disease-label("diseases_chart", disease, lang)
    dynamic_headers.push([#align(bottom)[#text(size: font_size)[#rotate(-90deg, reflow: true)[#heading]]]])
  }

  dynamic_headers.push([#align(bottom + left)[#text(size: font_size)[#vaccine_s]]])
  
  // --- Create the table ---
  align(center)[
    #table(
        columns: (75pt, 16pt, 16pt, 16pt, 16pt, 16pt, 16pt, 16pt, 16pt, 16pt, 16pt, 16pt, 16pt, 16pt, 236pt),
        table.header(
          ..dynamic_headers
        ),
      stroke: 1pt,
      inset: 4pt,
      align: (
        left,
        center,
        center,
        center,
        center,
        center,
        center,
        center,
        center,
        center,
        center,
        center,
        center,
        left
      ), 
      ..table_rows.flatten(), 
      table.cell(stroke:none, align: right, colspan: 15)[#text(size: font_size)[#end_msg]],
      ..if show_validity_markers {
        (
          table.cell(stroke: none, align: left, colspan: 15)[#text(size: font_size)[#vax_valid #h(2pt) #valid_label]],
          table.cell(stroke: none, align: left, colspan: 15)[#text(size: font_size)[#vax_invalid #h(2pt) #invalid_label]]
        )
      } else { () }
    )
  ]

}
