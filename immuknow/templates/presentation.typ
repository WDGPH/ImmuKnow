// Legacy composition helpers delegate to the canonical package localization.
#import "lib/immuknow/lib.typ": localization
#let long-date = localization.long-date
#let table-labels = localization.table-labels

#let selected-labels() = {
  let result = (:)
  for lang in ("en", "fr") {
    for domain in ("diseases_chart", "diseases_overdue") {
      let name = lang + "_" + domain
      result.insert(name, json("/translations/" + name + ".json"))
    }
  }
  result
}

#let disease-label(domain, key, lang) = localization.disease-label(domain, key, lang, labels: selected-labels())
#let overdue-label(entry, include-dose, lang) = localization.overdue-label(entry, include-dose, lang, labels: selected-labels())
