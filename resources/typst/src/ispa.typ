// Disease/cohort scope only; upstream systems assess whether doses are overdue.
// https://www.ontario.ca/page/vaccines-children-school
// https://www.ontario.ca/laws/regulation/900645 (Table 1)
// ImmuKnow classifies prepared notices (src/ispa.rs); the rules below serve notices without it.

// Parsed (year, month, day) for a valid YYYY-MM-DD text, otherwise none; never fails.
#let iso-date(value) = {
  if type(value) != str or not value.contains(regex("^[0-9]{4}-[0-9]{2}-[0-9]{2}$")) { return none }
  let (year, month, day) = value.split("-").map(int)
  let leap = calc.rem(year, 4) == 0 and (calc.rem(year, 100) != 0 or calc.rem(year, 400) == 0)
  let days = (31, if leap { 29 } else { 28 }, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
  if month < 1 or month > 12 or day < 1 or day > days.at(month - 1) { return none }
  (year, month, day)
}

// The notice's ISPA classification, as prepared by ImmuKnow or derived with the same rules:
// status (ispa_overdue, no_ispa_overdue, ispa_not_applicable or ispa_unknown),
// in-scope overdue_diseases and undetermined_diseases.
#let ispa-classification(notice) = {
  let prepared = notice.at("ispa", default: none)
  if prepared != none { return prepared }
  let always = ("Diphtheria", "Tetanus", "Polio", "Measles", "Mumps", "Rubella", "Pertussis", "Meningococcal")
  let birth = iso-date(notice.client_data.at("date_of_birth_iso", default: none))
  let as-of = iso-date(notice.at("date_as_of", default: none))
  if birth == none or as-of == none {
    let undetermined = ()
    for entry in notice.overdue_diseases {
      if (entry.disease in always or entry.disease == "Varicella") and entry.disease not in undetermined {
        undetermined.push(entry.disease)
      }
    }
    return (status: "ispa_unknown", overdue_diseases: (), undetermined_diseases: undetermined)
  }
  // ISPA applies from the junior kindergarten cohort of the school year containing date_as_of.
  let school-year = if as-of.at(1) < 9 { as-of.at(0) - 1 } else { as-of.at(0) }
  if birth.at(0) > school-year - 4 {
    return (status: "ispa_not_applicable", overdue_diseases: (), undetermined_diseases: ())
  }
  let overdue = notice.overdue_diseases.filter(entry => (
    entry.disease in always or (entry.disease == "Varicella" and birth.at(0) >= 2010)
  ))
  (
    status: if overdue.len() > 0 { "ispa_overdue" } else { "no_ispa_overdue" },
    overdue_diseases: overdue,
    undetermined_diseases: (),
  )
}

// true or false for school-age clients; none for CCEYA ages or when applicability is unknown.
#let ispa-up-to-date(notice) = {
  let status = ispa-classification(notice).status
  if status == "ispa_overdue" { false } else if status == "no_ispa_overdue" { true } else { none }
}

#let ispa-overdue-diseases(notice) = {
  let classified = ispa-classification(notice)
  assert(classified.undetermined_diseases.len() == 0,
    message: "ISPA disease selection requires a valid birth date and date_as_of.")
  classified.overdue_diseases
}
