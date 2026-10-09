// Shared presentation for the two supported notice languages. Disease identifiers stay the same in both languages.
#let month-names = (
  en: ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"),
  fr: ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"),
)

#let long-date(iso, lang, required: true) = {
  assert(lang == "en" or lang == "fr", message: "Unsupported notice language: " + lang)
  if iso == none or iso == "" {
    assert(not required, message: "Required notice date is missing")
    return ""
  }
  let parts = iso.split("-")
  assert(iso.len() == 10 and parts.len() == 3 and parts.at(0).len() == 4 and parts.at(1).len() == 2 and parts.at(2).len() == 2,
    message: "Invalid ISO notice date: " + iso)
  let parsed = datetime(year: int(parts.at(0)), month: int(parts.at(1)), day: int(parts.at(2)))
  let month = month-names.at(lang).at(parsed.month() - 1)
  if lang == "fr" {
    str(parsed.day()) + " " + month + " " + str(parsed.year())
  } else {
    month + " " + str(parsed.day()) + ", " + str(parsed.year())
  }
}

#let disease-label(domain, key, lang, labels: none) = {
  assert(labels == none or type(labels) == dictionary, message: "labels must be a dictionary or none")
  assert(lang in ("en", "fr"), message: "Unsupported notice language")
  assert(domain in ("diseases_chart", "diseases_overdue"), message: "Unsupported disease label domain")
  let domain-labels(language) = {
    let name = language + "_" + domain
    if labels != none and name in labels { labels.at(name) }
    else { json("../locales/" + name + ".json") }
  }
  let selected = domain-labels(lang)
  assert(type(selected) == dictionary, message: "Disease labels must be a dictionary")
  if key in selected {
    assert(type(selected.at(key)) == str and selected.at(key) != "", message: "Disease label must be a nonempty string: " + key)
    return selected.at(key)
  }
  let known = json("../locales/en_" + domain + ".json").keys() + json("../locales/fr_" + domain + ".json").keys()
  assert(key not in known and key not in domain-labels(if lang == "en" { "fr" } else { "en" }),
    message: "Missing " + lang + " " + domain + " label for " + key)
  key
}

#let overdue-label(entry, include-dose, lang, labels: none) = {
  let disease = disease-label("diseases_overdue", entry.disease, lang, labels: labels)
  if not include-dose or entry.dose == none { return disease }
  let dose = entry.dose
  assert(type(dose) == int and dose > 0, message: "Invalid overdue dose for " + entry.disease)
  if lang == "fr" {
    disease + " (" + str(dose) + (if dose == 1 { "re" } else { "e" }) + " dose)"
  } else {
    let last-two = calc.rem(dose, 100)
    let last = calc.rem(dose, 10)
    let suffix = if last-two >= 11 and last-two <= 13 { "th" }
      else if last == 1 { "st" }
      else if last == 2 { "nd" }
      else if last == 3 { "rd" }
      else { "th" }
    disease + " (" + str(dose) + suffix + " dose)"
  }
}

#let table-labels(lang) = {
  assert(lang == "en" or lang == "fr", message: "Unsupported notice language: " + lang)
  if lang == "fr" {
    (
      date: "Date de l'administration",
      vaccine: "Vaccin(s)",
      unspecified: "*indique un agent vaccinal non spécifié",
      valid: "Dose valide",
      invalid: "Dose non valide",
      unknown: "Validité inconnue",
      recorded: "Administration consignée",
    )
  } else {
    (
      date: "Date Given",
      vaccine: "Vaccine(s)",
      unspecified: "*indicates unspecified vaccine agent",
      valid: "Valid dose",
      invalid: "Invalid dose",
      unknown: "Validity unknown",
      recorded: "Administration recorded",
    )
  }
}
