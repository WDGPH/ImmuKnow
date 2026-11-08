// Structural marker geometry follows Codetastic; see vendor/qr/LICENSE.codetastic.
#let alignment-centres(n) = {
  let version = calc.quo(n - 17, 4)
  if version == 1 { return () }
  let count = calc.quo(version, 7) + 2
  let step = if version == 32 { 26 } else {
    calc.quo(4 * version + 2 * count + 1, 2 * count - 2) * 2
  }
  let positions = (6,) + range(count - 1).map(i => n - 7 - i * step).rev()
  let centres = ()
  for x in positions {
    for y in positions {
      if not ((x == 6 and y == 6) or (x == 6 and y == n - 7) or (x == n - 7 and y == 6)) {
        centres.push((x, y))
      }
    }
  }
  centres
}

#let reserved-grid(n) = {
  let version = calc.quo(n - 17, 4)
  let field = range(n).map(row => range(n).map(column => row == 6 or column == 6))
  let areas = ((0, 0, 9, 9), (n - 8, 0, 8, 9), (0, n - 8, 9, 8))
  if version >= 7 {
    areas += ((n - 11, 0, 3, 6), (0, n - 11, 6, 3))
  }
  for (x, y) in alignment-centres(n) { areas.push((x - 2, y - 2, 5, 5)) }
  for (x, y, width, height) in areas {
    for row in range(y, y + height) {
      for column in range(x, x + width) { field.at(row).at(column) = true }
    }
  }
  field
}

// Fill touching default modules together using horizontal runs prepared in Rust.
#let draw-runs(runs, n, unit, quiet, bg, fg) = {
  let total = (n + 2 * quiet) * unit
  box(width: total, height: total, baseline: quiet * unit, {
    place(top + left, rect(width: total, height: total, fill: bg, stroke: none))
    let squares = ()
    for (row, start, end) in runs {
      let x = (start + quiet) * unit
      let y = (row + quiet) * unit
      let right = (end + quiet) * unit
      let bottom = (row + quiet + 1) * unit
      squares += (
        curve.move((x, y)), curve.line((right, y)),
        curve.line((right, bottom)), curve.line((x, bottom)), curve.close(),
      )
    }
    place(top + left, curve(..squares, fill: fg, stroke: none, fill-rule: "non-zero"))
  })
}

// Style only data cells; retain timing, alignment, format and version information.
#let draw-qr(field, unit, quiet, bg, fg, module-shape: "square", corner-style: "square", corner-foreground: auto, alignment-foreground: auto, logo: none, logo-size: 30%, logo-padding: 0.3mm, logo-mask: none) = {
  let n = field.len()
  let reserved = reserved-grid(n)
  let alignment = alignment-centres(n)
  let corner-fg = if corner-foreground == auto { fg } else { corner-foreground }
  let alignment-fg = if alignment-foreground == auto { fg } else { alignment-foreground }
  let total = (n + 2 * quiet) * unit
  let logo-cells = n * (logo-size / 100%)
  let start = (n - logo-cells) / 2
  let padding = logo-padding / unit
  let areas = if logo-mask == none {
    ((start - padding, start - padding, logo-cells + 2 * padding, logo-cells + 2 * padding),)
  } else {
    logo-mask.runs.map(run => {
      let (y, left, right) = run
      let pixel = logo-cells / logo-mask.size
      (start + left * pixel - padding, start + y * pixel - padding,
       (right - left) * pixel + 2 * padding, pixel + 2 * padding)
    })
  }
  if logo != none {
    for (x, y, w, h) in areas {
      for i in range(calc.max(0, calc.floor(y)), calc.min(n, calc.ceil(y + h))) {
        for j in range(calc.max(0, calc.floor(x)), calc.min(n, calc.ceil(x + w))) {
          assert(not reserved.at(i).at(j), message: "QR centre image overlaps a structural marker. Reduce the image size or border, change the URL, or remove the image.")
        }
      }
    }
  }
  let finders = ((0, 0), (n - 7, 0), (0, n - 7))
  let in-alignment(i, j) = alignment.any(p => calc.abs(j - p.at(0)) <= 2 and calc.abs(i - p.at(1)) <= 2)
  let in-finder(i, j) = finders.any(p => j >= p.at(0) and j < p.at(0) + 7 and i >= p.at(1) and i < p.at(1) + 7)
  box(width: total, height: total, baseline: quiet * unit, {
    place(top + left, rect(width: total, height: total, fill: bg, stroke: none))
    let squares = ((), (), ())
    for (i, row) in field.enumerate() {
      for (j, dark) in row.enumerate() {
        if dark and not (corner-style == "rounded" and in-finder(i, j)) {
          let shape = if reserved.at(i).at(j) { "square" } else { module-shape }
          if shape in ("square", "separated") {
            let inset = if shape == "separated" { 0.1 } else { 0 }
            let x = (j + quiet + inset) * unit
            let y = (i + quiet + inset) * unit
            let right = (j + quiet + 1 - inset) * unit
            let bottom = (i + quiet + 1 - inset) * unit
            let group = (if corner-fg != fg and in-finder(i, j) { 1 }
              else if alignment-fg != fg and in-alignment(i, j) { 2 } else { 0 })
            squares.at(group) += (
              curve.move((x, y)), curve.line((right, y)),
              curve.line((right, bottom)), curve.line((x, bottom)), curve.close(),
            )
          } else {
            place(top + left, dx: (j + quiet) * unit, dy: (i + quiet) * unit, {
              if shape == "dots" { circle(radius: unit / 2, fill: fg, stroke: none) }
              else { rect(width: unit, height: unit, radius: unit * 0.25, fill: fg, stroke: none) }
            })
          }
        }
      }
    }
    // Fill touching squares together so antialiasing cannot expose their shared edges.
    for (paths, fill) in squares.zip((fg, corner-fg, alignment-fg)) {
      if paths.len() > 0 {
        place(top + left, curve(..paths, fill: fill, stroke: none, fill-rule: "non-zero"))
      }
    }
    if corner-style == "rounded" {
      for (x, y) in finders {
        for (inset, size, fill, radius) in ((0, 7, corner-fg, 1), (1, 5, bg, 0.65), (2, 3, corner-fg, 0.4)) {
          place(top + left, dx: (x + quiet + inset) * unit, dy: (y + quiet + inset) * unit,
            rect(width: size * unit, height: size * unit, radius: radius * unit, fill: fill, stroke: none))
        }
      }
    }
    if logo != none {
      for (x, y, w, h) in areas {
        place(top + left, dx: (x + quiet) * unit, dy: (y + quiet) * unit,
          rect(width: w * unit, height: h * unit, radius: logo-padding, fill: bg, stroke: none))
      }
      place(top + left, dx: (start + quiet) * unit, dy: (start + quiet) * unit,
        box(width: logo-cells * unit, height: logo-cells * unit, clip: true, logo))
    }
  })
}
