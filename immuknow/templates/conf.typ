#import "/templates/presentation.typ" as presentation

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
