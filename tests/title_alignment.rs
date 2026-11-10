//! Test title positioning through the shipped Typst layout components.
use immuknow::{
    compiler::{Compiler, Request},
    resources,
};
use serde_json::json;
use std::{collections::BTreeMap, fs};

#[test]
fn title_alignment_moves_only_the_title_and_preserves_header_evidence() {
    let temp = tempfile::tempdir().unwrap();
    resources::materialize(temp.path()).unwrap();
    fs::write(temp.path().join("probe.typ"), r#"
#import "typst/src/layout.typ": notice-header, notice-section
#set page(width: 500pt, height: 800pt, margin: 40pt)
#show text: it => box([#metadata(it.text) <visible-text>#it])
#let logo = [Brand]
#let heading = "Title"
#notice-header(logo: logo, logo-width: 100pt, title: heading, title-align: left)
#notice-header(logo: logo, logo-width: 100pt, title: heading)
#notice-header(logo: logo, logo-width: 100pt, title: heading, title-align: right)
#notice-section(heading, [Body], logo: logo, logo-width: 100pt, title-align: right)
#notice-header(title: [First#linebreak()Second#linebreak()Third#linebreak()Fourth], title-align: left)
#context [#metadata((
  titles: query(<visible-text>).filter(it => it.value == "Title").map(it => it.location().position().x.pt()),
  logos: query(<visible-text>).filter(it => it.value == "Brand").map(it => it.location().position().x.pt()),
  headers: query(<immuknow-component>).map(it => it.value).filter(it => it.name == "header"),
  checks: query(<immuknow-check>).map(it => it.value).filter(it => it.code == "layout.header_title_lines"),
)) <immuknow-report>]
"#).unwrap();
    let mut compiler = Compiler::new(temp.path().to_path_buf(), Compiler::fonts());
    let compiled = compiler
        .run(&Request {
            inputs: BTreeMap::from([("immuknow-template-path".into(), "/probe.typ".into())]),
            notice: json!({}),
            timestamp: 1_750_000_000,
        })
        .expect("title alignment probe must compile");
    let report = &compiled.reports.unwrap()[0];
    let titles: Vec<f64> = report["titles"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_f64().unwrap())
        .collect();
    let logos: Vec<f64> = report["logos"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_f64().unwrap())
        .collect();
    assert_eq!(titles.len(), 4);
    assert!(titles[0] < titles[1] && titles[1] < titles[2], "{titles:?}");
    assert!(
        (titles[2] - titles[3]).abs() < 0.1,
        "section forwards alignment: {titles:?}"
    );
    assert!(
        logos.iter().all(|x| (x - logos[0]).abs() < 0.1),
        "{logos:?}"
    );
    let headers = report["headers"].as_array().unwrap();
    let checks = report["checks"].as_array().unwrap();
    assert_eq!(headers.len(), 5);
    assert_eq!(checks.len(), 5);
    assert!(checks[..4].iter().all(|check| check["status"] == "pass"));
    assert_eq!(checks[4]["status"], "warn");
    assert!(checks[..4]
        .iter()
        .all(|check| check.get("measurements").is_none()));
    assert!(
        checks[4]["measurements"]["title_height_pt"]
            .as_f64()
            .unwrap()
            > checks[4]["measurements"]["three_line_height_pt"]
                .as_f64()
                .unwrap()
    );
    assert!(headers
        .iter()
        .all(|header| header["measurements"] == json!({})));
    assert!(headers[..4]
        .iter()
        .all(|header| header["measurements"] == headers[0]["measurements"]));
}
