// An explicit source choice takes priority; age supplies the project default.
#let intended-reader(notice) = {
  let selected = notice.at("intended_reader", default: none)
  assert(selected in (none, "student", "guardian"), message: "Intended reader must be student, guardian or none")
  if selected != none { return selected }
  let age = notice.client_data.age
  if age == none { none } else if age >= 16 { "student" } else { "guardian" }
}
