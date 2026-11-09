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
    }
}
