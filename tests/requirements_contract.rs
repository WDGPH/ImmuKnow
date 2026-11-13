//! Shared requirements evidence cases, shared with browser contract consumers.
use immuknow::validation::Validator;
use serde_json::{Value, json};
use std::{fs, path::Path};

fn fixture(name: &str) -> Value {
    let path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures")
        .join(name);
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}

#[test]
fn requirements_evidence_matches_frozen_cases() {
    let corpus = fixture("requirements-contract.json");
    let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("resources");
    let validator = Validator::new(&root).unwrap();
    for case in corpus["cases"].as_array().unwrap() {
        let name = case["name"].as_str().unwrap();
        let result = validator.payload(&case["payload"]).and_then(|()| {
            validator.report(
                &json!([case["report"]]),
                &case["payload"],
                case["report"]["page_count"].as_u64().unwrap() as usize,
            )
        });
        assert_eq!(
            result.is_ok(),
            case["expect"]["evidence_valid"] == true,
            "{name}: {:?}",
            result.err()
        );
    }
}
