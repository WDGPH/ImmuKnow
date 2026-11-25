#import "intended-reader.typ": intended-reader
#import "ispa.typ": ispa-up-to-date

// Presentation choices from source facts; no vaccination assessment is performed.
// include-ispa is retained for earlier templates; ispa_up_to_date is included by default.
#let notice-flags(notice, include-ispa: true) = {
  assert(type(include-ispa) == bool, message: "include-ispa must be a boolean")
  let selected-reader = intended-reader(notice)
  assert(type(notice.has_immunization_records) == bool, message: "has_immunization_records must be a boolean")
  let flags = (
    to_student: selected-reader == "student",
    to_guardian: selected-reader == "guardian",
    no_records: not notice.has_immunization_records,
    up_to_date: notice.overdue_diseases.len() == 0,
  )
  if include-ispa { flags.insert("ispa_up_to_date", ispa-up-to-date(notice)) }
  flags
}
