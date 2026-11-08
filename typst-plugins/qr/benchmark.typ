#import "../../resources/typst/src/qr.typ": qr-code
#let encoder = plugin("../../resources/typst/vendor/qr/qr.wasm")
#let mode = sys.inputs.at("mode", default: "square")
#let count = int(sys.inputs.at("count", default: "100"))
#set page(width: 8cm, height: 8cm, margin: 1cm)
#for i in range(count) {
  let url = "https://example.org/update?client=" + str(6771976100 + i) + "&initials=VI"
  if mode == "off" {
    box(width: 3cm, height: 3cm)
  } else if mode == "encode" {
    let encoded = encoder.encode_runs(bytes(url), bytes("l"))
    text(str(encoded.at(0)))
  } else {
    qr-code(none, url: url, module-shape: mode)
  }
  if i + 1 < count { pagebreak() }
}
