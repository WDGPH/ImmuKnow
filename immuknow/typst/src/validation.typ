// Python checks the factual schema; the authored project checks its filename identity.
#let check-notice(notice, version: none, language: none) = {
  assert(notice.schema_version == 1, message: "Unsupported rendering schema_version")
  assert(language in ("en", "fr"), message: "Unsupported notice language")
  assert(notice.version_id == version, message: "Notice version does not match this template")
  assert(notice.language == language, message: "Notice language does not match this template")
}
#let strings(value, label, unique: false) = {
  assert(type(value) == array and value.all(item => type(item) == str and item != ""), message: label + " must contain nonempty strings")
  if unique { assert(value.dedup().len() == value.len(), message: label + " contains duplicate values") }
}
