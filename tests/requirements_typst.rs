//! Compile the same placed requirements and component evidence used by native and browser notices.
use immuknow::{
    compiler::{Compiler, Request},
    resources,
    validation::Validator,
};
use serde_json::Value;
use std::{collections::BTreeMap, fs, path::Path};

fn fixture(name: &str) -> Value {
    let root = Path::new(env!("CARGO_MANIFEST_DIR"));
    let data: Value =
        immuknow::read_json(&root.join("tests/fixtures/requirements-contract.json")).unwrap();
    data["cases"]
        .as_array()
        .unwrap()
        .iter()
        .find(|case| case["name"] == name)
        .unwrap()
        .clone()
}

fn compile(name: &str, requirements: &str, body: &str) -> (Value, bool) {
    let case = fixture(name);
    let temp = tempfile::tempdir().unwrap();
    resources::materialize(temp.path()).unwrap();
    let source = format!(
        r#"
#import "typst/src/findings.typ": report, component
#import "typst/src/requirements.typ": requirements, identity
#import "typst/src/overdue.typ": overdue-agents, agent-alternative
#let notice = json(sys.inputs.data)
{requirements}
{body}
#report(notice)
"#
    );
    fs::write(temp.path().join("probe.typ"), source).unwrap();
    let notice = case["payload"].clone();
    let mut compiler = Compiler::new(temp.path().to_path_buf(), Compiler::fonts());
    let compiled = compiler
        .run(&Request {
            inputs: BTreeMap::from([("immuknow-template-path".into(), "/probe.typ".into())]),
            notice: notice.clone(),
            timestamp: 1_750_000_000,
        })
        .expect("probe produces a readable PDF");
    assert!(!compiled.pdf.is_empty());
    let report = compiled.reports.unwrap();
    let validator = Validator::new(temp.path()).unwrap();
    let valid = validator.report(&report, &notice, 1).is_ok();
    (report[0].clone(), valid)
}

fn checks(report: &Value) -> BTreeMap<String, String> {
    report["checks"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|check| {
            [
                "notice.requirements",
                "notice.eligibility",
                "data.forecast_coverage",
                "content.agent_display",
            ]
            .contains(&check["code"].as_str().unwrap_or(""))
        })
        .map(|check| {
            (
                check["code"].as_str().unwrap().into(),
                check["status"].as_str().unwrap().into(),
            )
        })
        .collect()
}

#[test]
fn evaluator_matches_frozen_requirements_outcomes() {
    let scenarios = [
        (
            "disease_extra_warn",
            "#requirements(notice, eligibility: \"has_overdue\", coverage: \"diseases\")",
            "",
        ),
        (
            "agents_missing_coverage",
            "#requirements(notice, eligibility: \"has_overdue_agents\", coverage: \"agents\")",
            "#overdue-agents(notice)",
        ),
        (
            "all_excluded_duplicate",
            "#requirements(notice, eligibility: \"has_overdue_agents\", coverage: \"agents\")",
            "#overdue-agents(notice, ignore-agents: notice.overdue_agents)",
        ),
        (
            "no_records_replacement",
            "#requirements(notice, eligibility: \"has_overdue_agents\", coverage: \"agents\")",
            "#overdue-agents(notice, no-records: \"Send records\")",
        ),
        (
            "intentional_alternative",
            "#requirements(notice, eligibility: \"has_overdue_agents\", coverage: \"agents\")",
            "#agent-alternative(notice)[Contact the clinic.]",
        ),
        (
            "affirmative_failure",
            "#requirements(notice, eligibility: \"no_overdue\", coverage: \"neutral\")",
            "",
        ),
        (
            "explicit_neutral",
            "#requirements(notice, eligibility: \"any\", coverage: \"neutral\")",
            "",
        ),
        (
            "suspension_ispa_eligible",
            "#requirements(notice, eligibility: \"has_ispa_overdue\", coverage: \"diseases\")",
            "",
        ),
    ];
    for (name, declaration, body) in scenarios {
        let case = fixture(name);
        let (report, valid) = compile(name, declaration, body);
        assert!(valid, "{name}: {report}");
        let expected: BTreeMap<String, String> =
            serde_json::from_value(case["expect"]["observations"].clone()).unwrap();
        assert_eq!(checks(&report), expected, "{name}");
        assert_eq!(
            report["blocked_checks"], case["expect"]["blocked_checks"],
            "{name}"
        );
        assert_eq!(report["requirements"]["state"], "valid");
    }
}

#[test]
fn missing_duplicate_and_malformed_declarations_remain_readable_failed_reports() {
    let scenarios = [
        ("declaration_missing", "", "missing"),
        (
            "declaration_duplicate",
            "#requirements(notice, eligibility: \"any\", coverage: \"neutral\") #requirements(notice, eligibility: \"any\", coverage: \"neutral\")",
            "duplicate",
        ),
        (
            "declaration_malformed",
            "#requirements(notice, eligibility: 42, coverage: \"neutral\")",
            "malformed",
        ),
        (
            "declaration_unknown_value",
            "#requirements(notice, eligibility: \"other\", coverage: \"neutral\")",
            "unknown_value",
        ),
    ];
    for (name, declaration, error) in scenarios {
        let (report, valid) = compile(name, declaration, "Visible notice");
        assert!(valid, "{name}: {report}");
        assert_eq!(report["requirements"]["errors"][0]["code"], error);
        assert_eq!(
            checks(&report),
            BTreeMap::from([("notice.requirements".into(), "fail".into())])
        );
        assert_eq!(report["blocked_checks"].as_array().unwrap().len(), 3);
    }
}

#[test]
fn wrong_source_and_invisible_alternatives_are_corrupt_but_readable() {
    let declaration =
        "#requirements(notice, eligibility: \"has_overdue_agents\", coverage: \"agents\")";
    for body in [
        "#agent-alternative(notice)[]",
        "#agent-alternative(notice)[   ]",
        "#agent-alternative(notice)[#metadata(1)]",
        "#agent-alternative(notice)[#hide[Text]]",
        "#agent-alternative(notice)[#pagebreak()]",
        "#agent-alternative(notice)[#context [Text]]",
    ] {
        let (report, valid) = compile("intentional_alternative", declaration, body);
        assert!(!valid, "{report}");
        assert_eq!(
            report["measurements"]["overdue_agents"][0]["replacement_visible"],
            false
        );
    }
    for body in [
        "#agent-alternative(notice)[Visible text]",
        "#agent-alternative(notice)[#rect(width: 1pt, height: 1pt)]",
        "#agent-alternative(notice)[#text(weight: \"bold\")[Visible text]]",
    ] {
        let (report, valid) = compile("intentional_alternative", declaration, body);
        assert!(valid, "{report}");
        assert_eq!(
            report["measurements"]["overdue_agents"][0]["replacement_visible"],
            true
        );
    }
    for replacement in ["[]", "[   ]", "[#metadata(1)]"] {
        let body = format!("#overdue-agents(notice, no-records: {replacement})");
        let (report, valid) = compile("no_records_replacement", declaration, &body);
        assert!(!valid, "{report}");
        assert_eq!(
            report["measurements"]["overdue_agents"][0]["replacement"],
            "no_records"
        );
        assert_eq!(
            report["measurements"]["overdue_agents"][0]["replacement_visible"],
            false
        );
    }
    let (report, valid) = compile(
        "intentional_alternative",
        declaration,
        "#context [#component(\"overdue_agents\", measurements: (page: here().page()), notice: notice)]",
    );
    assert!(!valid, "{report}");
    assert_eq!(checks(&report)["content.agent_display"], "fail");
    let (report, valid) = compile(
        "declaration_malformed",
        "#metadata((identity: identity(notice), eligibility: \"any\", coverage: \"neutral\", extra: true)) <immuknow-requirements>",
        "Visible notice",
    );
    assert!(valid, "{report}");
    assert_eq!(report["requirements"]["errors"][0]["code"], "malformed");
    let (report, valid) = compile(
        "wrong_declaration_row",
        "#requirements((..notice, row_key: \"other-row\"), eligibility: \"has_overdue\", coverage: \"diseases\")",
        "Visible notice",
    );
    assert!(!valid, "{report}");
}
