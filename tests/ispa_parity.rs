//! Keep prepared ISPA classification and the Typst fallback in step.
use chrono::NaiveDate;
use immuknow::{
    compiler::{Compiler, Request},
    ispa, resources,
};
use serde_json::{Value, json};
use std::{collections::BTreeMap, fs};

fn select(compiler: &mut Compiler, notice: &Value) -> Result<Value, String> {
    let compiled = compiler.run(&Request {
        inputs: BTreeMap::from([("immuknow-template-path".into(), "/probe.typ".into())]),
        notice: notice.clone(),
        timestamp: 1_750_000_000,
    })?;
    Ok(compiled.reports?[0]["diseases"].clone())
}

#[test]
fn prepared_classification_matches_typst_fallback() {
    let temp = tempfile::tempdir().unwrap();
    resources::materialize(temp.path()).unwrap();
    fs::write(
        temp.path().join("probe.typ"),
        r#"
#import "typst/src/ispa.typ": ispa-overdue-diseases
#let notice = json(sys.inputs.data)
#metadata((diseases: ispa-overdue-diseases(notice))) <immuknow-report>
"#,
    )
    .unwrap();
    let mut compiler = Compiler::new(temp.path().to_path_buf(), Compiler::fonts());
    let date = |text: &str| NaiveDate::parse_from_str(text, "%Y-%m-%d").ok();
    let lists = [
        json!([{"disease":"Diphtheria","dose":1}, {"disease":"Varicella","dose":2},
            {"disease":"HPV","dose":1}, {"disease":"Meningococcal","dose":null,"dose_raw":"x"}]),
        json!([{"disease":"Meningococcal","dose":1}, {"disease":"HPV","dose":2}]),
        json!([{"disease":"Varicella","dose":null}]),
    ];
    let births = [
        "",
        "1996-12-31",
        "1997-01-01",
        "2000-02-29",
        "2004-08-31",
        "2004-09-01",
        "2009-12-31",
        "2010-01-01",
    ];
    let as_of = ["", "2012-02-28", "2012-02-29", "2016-08-30", "2016-08-31"];
    for overdue in &lists {
        for birth in births {
            for as_of in as_of {
                let mut notice = json!({
                    "client_data": {"date_of_birth_iso": birth},
                    "date_as_of": as_of,
                    "overdue_diseases": overdue,
                });
                let fallback = select(&mut compiler, &notice);
                let prepared =
                    ispa::classify(overdue.as_array().unwrap(), date(birth), date(as_of));
                notice["ispa"] = prepared.notice_value();
                let case = format!("{overdue} born {birth:?} as of {as_of:?}");
                match (fallback, select(&mut compiler, &notice)) {
                    (Ok(expected), Ok(actual)) => {
                        assert_eq!(actual, expected, "{case}");
                        assert!(prepared.undetermined.is_empty(), "{case}");
                    }
                    (Err(expected), Err(actual)) => {
                        // Diagnostics quote different source excerpts; compare the stated reason.
                        let reason = |error: &str| {
                            let message = error.lines().next().unwrap_or("");
                            ["requires a valid birth date", "requires date_as_of"]
                                .into_iter()
                                .find(|r| message.contains(r))
                                .unwrap_or_else(|| panic!("{case}: unexpected error {error}"))
                        };
                        assert_eq!(reason(&actual), reason(&expected), "{case}");
                        assert!(!prepared.undetermined.is_empty(), "{case}");
                    }
                    (expected, actual) => panic!("{case}: {expected:?} != {actual:?}"),
                }
            }
        }
    }
}
