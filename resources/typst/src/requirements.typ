#import "ispa.typ": ispa-overdue-diseases

#let identity(notice) = {
  let value(key) = if type(notice) == dictionary { notice.at(key, default: none) } else { none }
  (row_key: value("row_key"), client_id: value("client_id"), template: value("template"),
    version_id: value("version_id"), language: value("language"))
}

// Do not assert on the authored requirement: invalid selections still need a
// readable notice and a structured failed requirements finding.
#let requirements(notice, eligibility: none, coverage: none) = [
  #metadata((identity: identity(notice), eligibility: eligibility, coverage: coverage)) <immuknow-requirements>
]

#let result(code, status, message, measurements: none) = {
  let value = (code: code, stage: "render", status: status, message: message)
  if measurements != none { value.insert("measurements", measurements) }
  value
}

#let evaluate-requirements(notice, declarations, agents) = {
  let error = none
  if declarations.len() == 0 { error = (code: "missing", count: 0) }
  else if declarations.len() > 1 { error = (code: "duplicate", count: declarations.len()) }
  else {
    let item = declarations.first()
    if type(item) != dictionary or item.keys().sorted() != ("coverage", "eligibility", "identity") or type(item.at("eligibility", default: none)) != str or type(item.at("coverage", default: none)) != str {
      error = (code: "malformed", count: 1)
    } else if item.eligibility not in ("any", "has_overdue", "has_overdue_agents", "no_overdue", "has_ispa_overdue") or item.coverage not in ("agents", "diseases", "neutral") {
      error = (code: "unknown_value", count: 1)
    }
  }
  if error != none {
    return (
      requirements: (state: "invalid", errors: (error,)),
      blocked: ("notice.eligibility", "data.forecast_coverage", "content.agent_display").map(code =>
        (code: code, blocked_by: "notice.requirements", reason: "Invalid notice requirements")),
      checks: (result("notice.requirements", "fail", "Notice requirements are missing or invalid."),),
    )
  }
  let item = declarations.first()
  let declared-identity = item.at("identity", default: none)
  if type(declared-identity) != dictionary { declared-identity = identity(none) }
  let declaration = (..declared-identity, eligibility: item.eligibility, coverage: item.coverage)
  let eligibility = item.eligibility
  let eligible = if eligibility == "any" { none }
    else if eligibility == "has_overdue" { notice.overdue_diseases.len() > 0 }
    else if eligibility == "has_overdue_agents" { notice.overdue_agents.len() > 0 }
    else if eligibility == "no_overdue" { notice.overdue_diseases.len() == 0 }
    else { ispa-overdue-diseases(notice).len() > 0 }
  let eligibility-status = if eligible == none { "not_applicable" } else if eligible { "pass" } else { "fail" }
  let coverage = notice.forecast_coverage
  let no-source = notice.overdue_diseases.len() == 0 and notice.overdue_agents.len() == 0
  let coverage-status = if item.coverage == "neutral" or no-source { "not_applicable" }
    else if coverage.missing_diseases.len() > 0 { if item.coverage == "agents" { "fail" } else { "warn" } }
    else if coverage.extra_diseases.len() > 0 or coverage.unmapped_agents.len() > 0 { "warn" }
    else { "pass" }
  let display-status = if item.coverage != "agents" { "not_applicable" }
    else if agents.len() != 1 { "fail" }
    else {
      let agent = agents.first()
      if type(agent) != dictionary { "fail" } else {
        let replacement = agent.at("replacement", default: none)
        let visible = agent.at("replacement_visible", default: none)
        let source-count = agent.at("source_count", default: none)
        let displayed-count = agent.at("displayed_count", default: none)
        if replacement not in ("none", "no_records", "authored_alternative") or type(visible) != bool or type(source-count) != int or type(displayed-count) != int { "fail" }
        else if replacement != "none" { if visible { "pass" } else { "fail" } }
        else if source-count == 0 { "not_applicable" }
        else if displayed-count == 0 { "fail" }
        else { "pass" }
      }
    }
  (
    requirements: (state: "valid", declaration: declaration),
    blocked: (),
    checks: (
      result("notice.requirements", "pass", "Notice requirements were declared."),
      result("notice.eligibility", eligibility-status, if eligibility-status == "fail" { "The selected notice does not fit the source facts." } else { "Notice eligibility was evaluated." }),
      result("data.forecast_coverage", coverage-status, if coverage-status in ("warn", "fail") { "Forecasted agents do not exactly match the overdue diseases; review the coverage details." } else { "Forecast coverage was evaluated." }, measurements: coverage),
      result("content.agent_display", display-status, if display-status == "fail" { "The agent recommendation is empty or unavailable; review the notice." } else { "Agent recommendation display was evaluated." }),
    ),
  )
}
