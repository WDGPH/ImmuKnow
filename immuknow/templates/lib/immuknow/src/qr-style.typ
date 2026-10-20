#import "../vendor/codetastic/qrutil.typ" as qrutil
#import "../vendor/codetastic/bitfield.typ" as bitfield

// Style only data cells; retain timing, alignment, format and version information.
#let draw-qr(field, version, unit, quiet, bg, fg, module-shape: "square", corner-style: "square", logo: none, logo-size: 30%, logo-padding: 0.3mm, logo-mask: none) = {
  let n = field.len()
  let reserved = qrutil.reserve-bits(bitfield.new(n, n), version)
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
  let in-finder(i, j) = finders.any(p => j >= p.at(0) and j < p.at(0) + 7 and i >= p.at(1) and i < p.at(1) + 7)
  box(width: total, height: total, baseline: quiet * unit, {
    place(top + left, rect(width: total, height: total, fill: bg, stroke: none))
    for (i, row) in field.enumerate() {
      for (j, dark) in row.enumerate() {
        if dark and not (corner-style == "rounded" and in-finder(i, j)) {
          let shape = if reserved.at(i).at(j) { "square" } else { module-shape }
          place(top + left, dx: (j + quiet) * unit, dy: (i + quiet) * unit, {
            if shape == "dots" { circle(radius: unit / 2, fill: fg, stroke: none) }
            else { rect(width: unit, height: unit, radius: if shape == "rounded" { unit * 0.25 } else { 0pt }, fill: fg, stroke: none) }
          })
        }
      }
    }
    if corner-style == "rounded" {
      for (x, y) in finders {
        for (inset, size, fill, radius) in ((0, 7, fg, 1), (1, 5, bg, 0.65), (2, 3, fg, 0.4)) {
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
