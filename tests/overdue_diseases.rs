//! Verify disease display against prepared facts using the shipped component.
use immuknow::{
    compiler::{Compiler, Request},
    resources,
};
use serde_json::json;
use std::{collections::BTreeMap, fs};

#[test]
fn duplicate_diseases_preserve_order_and_distinct_displayed_doses() {
    let temp = tempfile::tempdir().unwrap();
    resources::materialize(temp.path()).unwrap();
    // Poliomyelitis and Polio normalize to Polio before these facts reach Typst.
    let notice = json!({
        "row_key": "row-000001", "client_id": "0000000001", "language": "en",
        "client_data": {"date_of_birth_iso": "2015-01-02"},
        "date_as_of": "2025-08-31", "has_immunization_records": true,
        "overdue_diseases": [
            {"disease":"Polio", "dose":1}, {"disease":"Measles", "dose":2},
            {"disease":"Polio", "dose":1}, {"disease":"Polio", "dose":2},
            {"disease":"HPV", "dose":1}
        ]
    });
    fs::write(
        temp.path().join("probe.typ"),
        r#"
#import "typst/src/overdue.typ": overdue-diseases
#let notice = json(sys.inputs.data)
#show text: it => [#metadata(it.text) <seen>#it]
#overdue-diseases(notice, style: "comma-separated")
#overdue-diseases(notice, style: "comma-separated", include-dose: true)
#overdue-diseases(notice, style: "comma-separated", ispa-only: true)
#context [#metadata((texts: query(<seen>).map(it => it.value),
  components: query(<immuknow-component>).map(it => it.value))) <immuknow-report>]
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
        .expect("disease probe compiles");
    let report = &compiled.reports.unwrap()[0];
    assert_eq!(
        report["texts"],
        json!([
            "Polio, Measles, Human Papillomavirus (HPV)",
            "Polio",
            " (1st dose)",
            ", ",
            "Measles",
            " (2nd dose)",
            ", ",
            "Polio",
            " (2nd dose)",
            ", ",
            "Human Papillomavirus (HPV)",
            " (1st dose)",
            "Polio, Measles"
        ])
    );
    let components = report["components"].as_array().unwrap();
    assert_eq!(components.len(), 3);
    for component in components {
        assert_eq!(component["notice"], notice);
    }
}
