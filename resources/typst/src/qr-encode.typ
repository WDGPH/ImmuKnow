#let encoder = plugin("../vendor/qr/qr.wasm")

#let encode-runs(destination, correction) = encoder.encode_runs(bytes(destination), bytes(correction))

#let encode-qr(destination, correction) = {
  let encoded = encoder.encode(bytes(destination), bytes(correction))
  let size = encoded.at(0)
  array(encoded.slice(1)).chunks(size)
}

#let encode-svg(destination, correction, foreground) = encoder.encode_svg(bytes(destination), bytes(correction), bytes(foreground.to-hex()))
