//! Schema and fixture checks for the proposed R2 requirements contract.
//! Active production schemas remain unchanged until the shared evaluator lands.
use serde_json::Value;
use std::{fs, path::Path};

fn fixture(name: &str) -> Value {
    let path = Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures")
        .join(name);
    serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
}

#[test]
fn proposed_contract_cases_are_well_formed() {
    let corpus = fixture("requirements-contract.json");
    let payload_schema = fixture("requirements-rendering.schema.json");
    let report_schema = fixture("requirements-report.schema.json");
    let payload_validator = jsonschema::validator_for(&payload_schema).unwrap();
    let report_validator = jsonschema::validator_for(&report_schema).unwrap();
    for case in corpus["cases"].as_array().unwrap() {
        let name = case["name"].as_str().unwrap();
        payload_validator
            .validate(&case["payload"])
            .unwrap_or_else(|err| panic!("{name}: {err}"));
        if case["expect"]["evidence_valid"] == true {
            report_validator
                .validate(&case["report"])
                .unwrap_or_else(|err| panic!("{name}: {err}"));
        }
        if matches!(
            name,
            "missing_required_check" | "duplicate_required_check" | "invalid_status"
        ) {
            assert!(
                report_validator.validate(&case["report"]).is_err(),
                "{name} must fail the proposed schema"
            );
        }
    }
}
