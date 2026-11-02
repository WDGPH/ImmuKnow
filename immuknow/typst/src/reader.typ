// An explicit source choice takes priority; age supplies the project default.
#let reader(notice) = {
  let selected = notice.at("reader", default: none)
  assert(selected in (none, "student", "guardian"), message: "Reader must be student, guardian or none")
  if selected != none { return selected }
  let over-16 = notice.client_data.over_16
  if over-16 == none { none } else if over-16 { "student" } else { "guardian" }
}
