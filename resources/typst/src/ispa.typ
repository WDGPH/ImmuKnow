// Disease/cohort scope only; upstream systems assess whether doses are overdue.
// https://www.ontario.ca/page/vaccines-children-school
// https://www.ontario.ca/laws/regulation/900645 (Table 1)
#let ispa-overdue-diseases(notice) = {
  let always = ("Diphtheria", "Tetanus", "Polio", "Measles", "Mumps", "Rubella", "Pertussis")
  let birth() = {
    let value = notice.client_data.date_of_birth_iso
    assert(type(value) == str and value.contains(regex("^[0-9]{4}-[0-9]{2}-[0-9]{2}$")),
      message: "ISPA disease selection requires a valid birth date for Varicella or Meningococcal disease.")
    let parts = value.split("-").map(int)
    let _ = datetime(year: parts.at(0), month: parts.at(1), day: parts.at(2))
    value
  }
  notice.overdue_diseases.filter(entry => {
    if entry.disease in always { return true }
    if entry.disease == "Varicella" { return birth() >= "2010-01-01" }
    if entry.disease == "Meningococcal" {
      let born = birth()
      if born >= "2004-09-01" { return true }
      if born < "1997-01-01" { return false }
      // Earlier eligible cohorts enter the requirement at age 12.
      let as-of = notice.date_as_of
      assert(type(as-of) == str and as-of.contains(regex("^[0-9]{4}-[0-9]{2}-[0-9]{2}$")),
        message: "ISPA meningococcal disease selection requires date_as_of for this birth cohort.")
      let parts = as-of.split("-").map(int)
      let _ = datetime(year: parts.at(0), month: parts.at(1), day: parts.at(2))
      let twelfth-birthday = str(int(born.slice(0, 4)) + 12) + born.slice(4)
      return as-of >= twelfth-birthday
    }
    false
  })
}
