#let encoder = plugin("../vendor/qr/qr.wasm")

#let encode-runs(destination, correction) = encoder.encode_runs(bytes(destination), bytes(correction))

#let encode-qr(destination, correction) = {
  let encoded = encoder.encode(bytes(destination), bytes(correction))
  let size = encoded.at(0)
  range(size).map(row => range(size).map(column =>
    encoded.at(1 + row * size + column) == 1
  ))
}

#let encode-svg(destination, correction, foreground) = encoder.encode_svg(bytes(destination), bytes(correction), bytes(foreground.to-hex()))
