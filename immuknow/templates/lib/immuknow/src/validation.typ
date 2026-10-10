// The rendering schema is independent of the package and authored notice IDs.
#let require-fields(value, names, label) = {
  assert(type(value) == dictionary, message: label + " must be a dictionary")
  for name in names {
    assert(name in value, message: label + " is missing required field: " + name)
  }
}

#let strings(value, label, unique: false) = {
  assert(type(value) == array, message: label + " must be an array")
  assert(value.all(item => type(item) == str and item != ""), message: label + " must contain nonempty strings")
  if unique {
    assert(value.dedup().len() == value.len(), message: label + " contains duplicate values")
  }
}

#let iso-date(value, label, optional: false) = {
  assert(type(value) == str, message: label + " must be an ISO date string")
  if optional and value == "" { return }
  assert(value.match(regex("^\\d{4}-\\d{2}-\\d{2}$")) != none, message: label + " must be YYYY-MM-DD")
  let parts = value.split("-").map(int)
  let parsed = datetime(year: parts.at(0), month: parts.at(1), day: parts.at(2))
}

#let check-notice(notice, version: none, language: none) = {
  require-fields(notice, ("schema_version",), "notice")
  assert(type(notice.schema_version) == int and notice.schema_version == 1,
    message: "Unsupported rendering schema_version; expected 1")
  require-fields(notice, (
    "version_id", "language", "client_id", "client_data", "date_as_of",
    "overdue_diseases", "overdue_agents", "history", "validity_coverage", "rendering_defaults",
  ), "notice")
  assert(language in ("en", "fr"), message: "Unsupported notice language")
  assert(notice.version_id == version, message: "Notice version does not match this template")
  assert(notice.language == language, message: "Notice language does not match this template")
  assert(type(notice.client_id) == str and notice.client_id != "", message: "client_id must be a nonempty string")
  require-fields(notice.client_data, ("name", "address", "city", "postal_code", "date_of_birth_iso", "school", "over_16"), "client_data")
  for key in ("name", "address", "city", "postal_code", "school") {
    assert(type(notice.client_data.at(key)) == str, message: "client_data." + key + " must be a string")
  }
  assert(type(notice.client_data.over_16) == bool, message: "client_data.over_16 must be a boolean")
  iso-date(notice.client_data.date_of_birth_iso, "date_of_birth_iso", optional: true)
  iso-date(notice.date_as_of, "date_as_of", optional: true)
  strings(notice.overdue_agents, "overdue_agents")
  assert(type(notice.overdue_diseases) == array, message: "overdue_diseases must be an array")
  for entry in notice.overdue_diseases {
    require-fields(entry, ("disease", "dose"), "overdue disease")
    assert(type(entry.disease) == str and entry.disease != "", message: "overdue disease must be a nonempty string")
    assert(entry.dose == none or (type(entry.dose) == int and entry.dose > 0), message: "overdue dose must be a positive integer or none")
  }
  assert(notice.validity_coverage in ("all_present", "all_absent", "mixed"), message: "Invalid validity_coverage")
  assert(type(notice.history) == array, message: "history must be an array")
  for item in notice.history {
    require-fields(item, ("date_given", "agent", "display_name", "diseases", "validity"), "history item")
    iso-date(item.date_given, "history date_given")
    assert(type(item.agent) == str and item.agent != "", message: "history agent must be a nonempty string")
    assert(type(item.display_name) == str and item.display_name != "", message: "history display_name must be a nonempty string")
    strings(item.diseases, "history diseases", unique: true)
    assert(item.validity in ("valid", "invalid", "unknown"), message: "Invalid history validity")
  }
  let defaults = notice.rendering_defaults
  require-fields(defaults, ("diseases", "include_other", "ignore_agents", "include_dose", "show_validity"), "rendering_defaults")
  strings(defaults.diseases, "rendering_defaults.diseases", unique: true)
  strings(defaults.ignore_agents, "rendering_defaults.ignore_agents")
  for key in ("include_other", "include_dose", "show_validity") {
    assert(type(defaults.at(key)) == bool, message: "rendering_defaults." + key + " must be a boolean")
  }
}
