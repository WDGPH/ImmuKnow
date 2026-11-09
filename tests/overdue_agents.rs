//! Exercise agent presentation using the shipped Typst component.
use immuknow::{
    compiler::{Compiler, Request},
    resources,
};
use serde_json::json;
use std::{collections::BTreeMap, fs};

#[test]
fn repeated_agents_are_displayed_once_in_first_occurrence_order() {
    let temp = tempfile::tempdir().unwrap();
    resources::materialize(temp.path()).unwrap();
    // A combined agent occurs once per disease in the supplied source facts.
    // A different agent interleaved between repeats checks stable ordering.
    let notice = json!({
        "row_key": "row-000001", "client_id": "0000000001", "language": "en",
        "overdue_diseases": [
            {"disease": "Measles", "dose": 1},
            {"disease": "Mumps", "dose": 1},
            {"disease": "Rubella", "dose": 1},
            {"disease": "Tetanus", "dose": 1}
        ],
        "overdue_agents": ["MMR", "DTaP", "MMR", "MMR"],
        "has_immunization_records": true
    });
    fs::write(
        temp.path().join("probe.typ"),
        r#"
#import "typst/src/overdue.typ": overdue-agents
#let notice = json(sys.inputs.data)
#show text: it => [#metadata(it.text) <seen>#it]
#overdue-agents(notice, style: "comma-separated")
#overdue-agents(notice, style: "bullets", columns: 1)
#context {
  [#metadata((texts: query(<seen>).map(it => it.value),
    components: query(<immuknow-component>).map(it => it.value))) <immuknow-report>]
}
"#,
    )
    .unwrap();
    let mut compiler = Compiler::new(temp.path().to_path_buf(), Compiler::fonts());
    let compiled = compiler
        .run(&Request {
            inputs: BTreeMap::from([("immuknow-template-path".into(), "/probe.typ".into())]),
            notice: notice.clone(),
            timestamp: 1_750_000_000,
        })
        .expect("agent component must compile");
    let report = &compiled.reports.unwrap()[0];
    assert_eq!(
        report["texts"],
        json!(["MMR, DTaP", "•", "MMR", "•", "DTaP"])
    );
    let components = report["components"].as_array().unwrap();
    assert_eq!(components.len(), 2);
    for component in components {
        assert_eq!(component["name"], "overdue_agents");
        assert_eq!(component["notice"], notice);
        assert_eq!(component["measurements"]["page"], 1);
        assert_eq!(
            component["measurements"]["source_agents"],
            json!(["MMR", "DTaP", "MMR", "MMR"])
        );
        assert_eq!(component["measurements"]["source_count"], 4);
        assert_eq!(
            component["measurements"]["displayed_agents"],
            json!(["MMR", "DTaP"])
        );
        assert_eq!(component["measurements"]["displayed_count"], 2);
        assert_eq!(component["measurements"]["replacement"], "none");
        assert_eq!(component["measurements"]["replacement_visible"], false);
    }
}

#[test]
fn exclusions_are_exact_and_leave_facts_and_no_records_behavior_intact() {
    let temp = tempfile::tempdir().unwrap();
    resources::materialize(temp.path()).unwrap();
    let notice = json!({
        "row_key": "row-000001", "client_id": "0000000001", "language": "en",
        "overdue_agents": ["Flu", "MMR", "Flu", "flu", "MMR"],
        "has_immunization_records": true
    });
    fs::write(temp.path().join("probe.typ"), r#"
#import "typst/src/overdue.typ": overdue-agents
#let notice = json(sys.inputs.data)
#let no-records = (..notice, has_immunization_records: false)
#show text: it => [#metadata(it.text) <seen>#it]
#overdue-agents(notice, style: "comma-separated", ignore-agents: ("Flu",))
#overdue-agents(notice, ignore-agents: ("Flu", "MMR", "flu"), empty: "Nothing overdue")
#overdue-agents(no-records, ignore-agents: ("Flu", "MMR", "flu"), empty: "Nothing overdue", no-records: "Send records")
#context [#metadata((texts: query(<seen>).map(it => it.value),
  components: query(<immuknow-component>).map(it => it.value))) <immuknow-report>]
"#).unwrap();
    let mut compiler = Compiler::new(temp.path().to_path_buf(), Compiler::fonts());
    let request = Request {
        inputs: BTreeMap::from([("immuknow-template-path".into(), "/probe.typ".into())]),
        notice: notice.clone(),
        timestamp: 1_750_000_000,
    };
    let compiled = compiler
        .run(&request)
        .expect("exclusion probe must compile");
    let report = &compiled.reports.unwrap()[0];
    assert_eq!(
        report["texts"],
        json!(["MMR, flu", "Nothing overdue", "Send records"])
    );
    let components = report["components"].as_array().unwrap();
    assert_eq!(components.len(), 3);
    assert_eq!(components[0]["notice"], notice);
    assert_eq!(components[1]["notice"], notice);
    assert_eq!(
        components[0]["measurements"]["excluded_agents"],
        json!(["Flu"])
    );
    assert_eq!(
        components[0]["measurements"]["displayed_agents"],
        json!(["MMR", "flu"])
    );
    assert_eq!(components[1]["measurements"]["displayed_count"], 0);
    assert_eq!(
        components[2]["measurements"]["excluded_agents"],
        json!(["Flu", "MMR", "flu"])
    );
    assert_eq!(components[2]["measurements"]["displayed_agents"], json!([]));
    assert_eq!(components[2]["measurements"]["replacement"], "no_records");
    assert_eq!(components[2]["measurements"]["replacement_visible"], true);
    assert_eq!(
        components[2]["notice"]["overdue_agents"],
        notice["overdue_agents"]
    );

    for invalid in ["\"Flu\"", "(\"\",)", "(42,)"] {
        fs::write(
            temp.path().join("probe.typ"),
            format!(
                r#"
#import "typst/src/overdue.typ": overdue-agents
#overdue-agents(json(sys.inputs.data), ignore-agents: {invalid})
"#
            ),
        )
        .unwrap();
        let error = compiler
            .run(&request)
            .err()
            .expect("invalid exclusions must fail");
        assert!(
            error.contains("ignore-agents must contain nonempty strings"),
            "{error}"
        );
    }
}
