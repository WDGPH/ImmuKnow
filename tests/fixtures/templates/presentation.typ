// Authored project labels may be edited independently of normalized disease names.

#let selected-labels() = {
  let result = (:)
  for lang in ("en", "fr") {
    for domain in ("diseases_chart", "diseases_overdue") {
      let name = lang + "_" + domain
      result.insert(name, json("translations/" + name + ".json"))
    }
  }
  result
}
