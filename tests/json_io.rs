//! Recursive JSON reads preserve array values and reject duplicate object fields.
use immuknow::read_json;
use serde::Deserialize;
use serde_json::{Value, json};
use std::fs;
use tempfile::tempdir;

#[derive(Debug, Deserialize, PartialEq)]
struct Envelope {
    groups: Vec<Vec<Item>>,
    empty: Vec<Value>,
}
#[derive(Debug, Deserialize, PartialEq)]
struct Item {
    name: String,
    values: Vec<Option<i64>>,
}

#[test]
fn nested_arrays_keep_values_and_reject_duplicate_object_fields() {
    let scratch = tempdir().unwrap();
    let path = scratch.path().join("fictional.json");
    let input = r#"{
        "groups": [[{"name": "Élodie, \"Camille\"", "values": [0, -2, null]}], []],
        "empty": []
    }"#;
    fs::write(&path, input).unwrap();
    let expected: Value = serde_json::from_str(input).unwrap();
    assert_eq!(read_json::<Value>(&path).unwrap(), expected);
    assert_eq!(
        read_json::<Envelope>(&path).unwrap(),
        Envelope {
            groups: vec![
                vec![Item {
                    name: "Élodie, \"Camille\"".into(),
                    values: vec![Some(0), Some(-2), None],
                }],
                vec![]
            ],
            empty: vec![],
        }
    );
    // Arrays can contain every JSON value, including arrays and objects.
    let array = json!([null, true, false, 1, -2, 1.25, "Zoé", [], {},
        [[{"children":[{"value":"保留"}]}]]]);
    fs::write(&path, serde_json::to_vec(&array).unwrap()).unwrap();
    assert_eq!(read_json::<Value>(&path).unwrap(), array);
    for malformed in [
        r#"{"name":"first","name":"second"}"#,
        r#"[{"name":"first","name":"second"}]"#,
        r#"{"groups":[[null,{"values":[{"name":"first","name":"second"}]}]]}"#,
        r#"[{"name":"first","\u006eame":"second"}]"#,
    ] {
        fs::write(&path, malformed).unwrap();
        let error = read_json::<Value>(&path).unwrap_err().to_string();
        assert!(error.contains("Repeated JSON field: name"), "{error}");
    }
}
