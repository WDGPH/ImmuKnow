#let vax = ("⬤")

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
    Client ID: #smallcaps[*#client_id.at(0)*] #linebreak()
    Date of Birth: *#client_data.date_of_birth* #linebreak()
    #school_type: #smallcaps[*#client_data.school*]
  ]

  // Build the table content
  let table_content = align(center)[
    #table(
      stroke: outline_stroke,
      columns: columns,
      rows: auto,
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
    Identifiant du client: #smallcaps[*#client_id.at(0)*] #linebreak()
    Date de naissance: *#client_data.date_of_birth* #linebreak()
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
  num_rows, 
  data, 
  diseases,
  font_size,
  lang
) = {

  let num_padded = min_rows - num_rows
  let table_rows = ()
  let empty_rows_content = ()
  let dynamic_headers = ()
  let date_given = if lang == "en" { "Date Given" } else { "Date de l'administration" }
  let vaccine_s = if lang == "en" { "Vaccine(s)" } else { "Vaccin(s)" }
  let end_msg = if lang == "en" { "*indicates unspecified vaccine agent" } else { "*indique un agent vaccinal non spécifié" }

  if num_rows > 0 {
      for record in data {
    // Start row with Date Given and At Age
    let row_cells = (
      record.date_given,
    )

    // Populate disease columns with #vax or empty
    for disease_name in diseases {

      let cell_content = ""
      for record_disease in record.diseases {
        if record_disease == disease_name { 
          cell_content = vax
          // Found a match, no need to check other diseases for this cell
          break 
        }
      }
      row_cells.push(cell_content)
    }
        // Add the Vaccine(s) column content
    let vaccine_content = if type(record.vaccine) == array {
      record.vaccine.join(", ") 
    } else {
      record.vaccine
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
    dynamic_headers.push([#align(bottom)[#text(size: font_size)[#rotate(-90deg, reflow: true)[#disease]]]])
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
      table.cell(stroke:none, align: right, colspan: 15)[#text(size: font_size)[#end_msg]]
    )
  ]

}