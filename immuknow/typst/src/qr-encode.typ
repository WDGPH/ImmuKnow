#let encoder = plugin("../vendor/qr/qr.wasm")

#let encode-qr(destination, correction) = {
  let encoded = encoder.encode(bytes(destination), bytes(correction))
  let size = encoded.at(0)
  range(size).map(row => range(size).map(column =>
    encoded.at(1 + row * size + column) == 1
  ))
}
