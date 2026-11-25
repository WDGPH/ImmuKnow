//! Keep prepared ISPA classification and the Typst fallback in step.
use chrono::NaiveDate;
use immuknow::{
    compiler::{Compiler, Request},
    ispa, resources,
};
use serde_json::{Value, json};
use std::{collections::BTreeMap, fs};

fn probe(compiler: &mut Compiler, notice: &Value) -> Result<Value, String> {
    let compiled = compiler.run(&Request {
        inputs: BTreeMap::from([("immuknow-template-path".into(), "/probe.typ".into())]),
        notice: notice.clone(),
        timestamp: 1_750_000_000,
    })?;
    Ok(compiled.reports?[0].clone())
}

#[test]
fn prepared_classification_matches_typst_fallback() {
    let temp = tempfile::tempdir().unwrap();
    resources::materialize(temp.path()).unwrap();
    fs::write(
        temp.path().join("probe.typ"),
        r#"
#import "typst/src/ispa.typ": ispa-classification, ispa-up-to-date
#let notice = json(sys.inputs.data)
#metadata((classification: ispa-classification(notice), up_to_date: ispa-up-to-date(notice))) <immuknow-report>
"#,
    )
    .unwrap();
    let mut compiler = Compiler::new(temp.path().to_path_buf(), Compiler::fonts());
    let date = |text: &str| NaiveDate::parse_from_str(text, "%Y-%m-%d").ok();
    let lists = [
        json!([{"disease":"Diphtheria","dose":1}, {"disease":"Varicella","dose":2},
            {"disease":"HPV","dose":1}, {"disease":"Meningococcal","dose":null,"dose_raw":"x"}]),
        json!([{"disease":"Varicella","dose":null}, {"disease":"Varicella","dose":1}]),
        json!([{"disease":"HPV","dose":2}]),
        json!([]),
    ];
    let births = [
        "",
        "2015-02-30",
        "1990-06-01",
        "2009-12-31",
        "2010-01-01",
        "2022-12-31",
        "2023-01-01",
    ];
    let as_of = ["", "2026-08-31", "2026-09-01", "2027-09-01"];
    for overdue in &lists {
        for birth in births {
            for as_of in as_of {
                let notice = json!({
                    "client_data": {"date_of_birth_iso": birth},
                    "date_as_of": as_of,
                    "overdue_diseases": overdue,
                });
                let case = format!("{overdue} born {birth:?} as of {as_of:?}");
                let fallback = probe(&mut compiler, &notice).unwrap();
                let prepared =
                    ispa::classify(overdue.as_array().unwrap(), date(birth), date(as_of));
                assert_eq!(
                    fallback["classification"],
                    prepared.notice_value(),
                    "{case}"
                );
                let up_to_date = match prepared.status {
                    "ispa_overdue" => json!(false),
                    "no_ispa_overdue" => json!(true),
                    _ => Value::Null,
                };
                assert_eq!(fallback["up_to_date"], up_to_date, "{case}");
            }
        }
    }
}
