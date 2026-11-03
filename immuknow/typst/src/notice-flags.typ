#import "reader.typ": reader
#import "ispa.typ": ispa-overdue-diseases

// Presentation choices from source facts; no vaccination assessment is performed.
#let notice-flags(notice, include-ispa: false) = {
  assert(type(include-ispa) == bool, message: "include-ispa must be a boolean")
  let selected-reader = reader(notice)
  assert(type(notice.has_immunization_records) == bool, message: "has_immunization_records must be a boolean")
  let flags = (
    to_student: selected-reader == "student",
    to_guardian: selected-reader == "guardian",
    no_records: not notice.has_immunization_records,
    up_to_date: notice.overdue_diseases.len() == 0,
  )
  if include-ispa { flags.insert("ispa_up_to_date", ispa-overdue-diseases(notice).len() == 0) }
  flags
}
