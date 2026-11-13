use anyhow::Result;
use immuknow::{bundles, input::Config};
use lopdf::{Document, Object, dictionary};
use serde_json::{Value, json};
use std::{fs, path::Path};

fn original(path: &Path) -> Result<()> {
    let mut pdf = Document::with_version("1.7");
    let pages = pdf.new_object_id();
    let row = path.file_stem().unwrap().to_str().unwrap();
    let page = pdf.add_object(
        dictionary! {"Type"=>"Page", "Parent"=>pages, "TestRow"=>Object::string_literal(row)},
    );
    pdf.objects.insert(pages, Object::Dictionary(dictionary! {"Type"=>"Pages", "Kids"=>vec![Object::Reference(page)], "Count"=>1, "MediaBox"=>vec![0.into(),0.into(),100.into(),200.into()]}));
    let catalog = pdf.add_object(dictionary! {"Type"=>"Catalog", "Pages"=>pages});
    pdf.trailer.set("Root", catalog);
    pdf.save(path)?;
    Ok(())
}

fn row(
    key: &str,
    school_id: &str,
    school: &str,
    board_id: &str,
    board: &str,
    last: &str,
    dob: &str,
) -> Value {
    json!({"row_key":key,"client_id":key,"notice":{"school":{"id":school_id,"name":school},"board":{"id":board_id,"name":board},"client_data":{"last_name":last,"date_of_birth_iso":dob}},"assignment":{"version_id":"notice","language":"en"},"original":{"status":"completed","path":format!("originals/{key}.pdf"),"pages":1},"encryption":{"status":"not_requested"},"checks":[],"effective_checks":[],"next_finding_sequence":1})
}

fn fixture(entries: Vec<Value>) -> Result<(tempfile::TempDir, Value)> {
    let dir = tempfile::tempdir()?;
    fs::create_dir(dir.path().join("originals"))?;
    for entry in &entries {
        original(&dir.path().join(entry["original"]["path"].as_str().unwrap()))?;
    }
    Ok((dir, json!({"entries":entries,"checks":[],"bundles":[]})))
}

fn members(record: &Value, route: &str) -> Vec<Vec<String>> {
    record["bundles"]
        .as_array()
        .unwrap()
        .iter()
        .filter(|b| b["route"] == route)
        .map(|b| {
            b["members"]
                .as_array()
                .unwrap()
                .iter()
                .map(|v| v.as_str().unwrap().to_owned())
                .collect()
        })
        .collect()
}

#[test]
fn missing_and_conflicting_institutions_route_safely_and_recompute() -> Result<()> {
    let (dir, mut record) = fixture(vec![
        row("r1", "", "Alpha  School", "b1", "Board", "A", "2010-01-01"),
        row("r2", "", "alpha school", "b1", "Board", "B", "2010-01-01"),
        row("r3", "", "Beta School", "b1", "Board", "C", "2010-01-01"),
        row("r4", "", "", "b1", "Board", "D", "2010-01-01"),
        row("r5", "", "", "b1", "Board", "E", "2010-01-01"),
        row("r6", "id1", "One", "b1", "Board", "F", "2010-01-01"),
        row("r7", "id1", "Two", "b1", "Board", "G", "2010-01-01"),
        row("r8", "id2", "One", "b1", "Board", "H", "2010-01-01"),
    ])?;
    let mut config = Config::default();
    config.bundling.bundle_size = 100;
    config.bundling.group_by = json!("school");
    bundles::bundle(dir.path(), &mut record, &config, 2)?;
    let normal = members(&record, "deliverable");
    assert!(normal.contains(&vec!["r1".into(), "r2".into()]));
    assert!(normal.contains(&vec!["r3".into()]));
    assert!(normal.contains(&vec!["r8".into()]));
    let review = members(&record, "review");
    for row in ["r4", "r5", "r6", "r7"] {
        assert!(review.contains(&vec![row.into()]));
    }
    assert_eq!(record["entries"][0]["checks"][0]["status"], "warn");
    assert_eq!(record["entries"][5]["checks"][0]["status"], "fail");
    let first_path = record["bundles"][0]["path"].as_str().unwrap().to_owned();
    bundles::bundle(dir.path(), &mut record, &config, 2)?;
    assert!(dir.path().join(first_path).is_file());
    assert!(
        record["bundles"][0]["path"]
            .as_str()
            .unwrap()
            .starts_with("bundles-0002/")
    );
    assert_eq!(record["entries"][0]["checks"].as_array().unwrap().len(), 1);
    config.bundling.group_by = json!("language");
    bundles::bundle(dir.path(), &mut record, &config, 2)?;
    assert_eq!(members(&record, "review").len(), 0);
    assert!(
        record["entries"]
            .as_array()
            .unwrap()
            .iter()
            .all(|e| e["checks"].as_array().unwrap().is_empty())
    );
    Ok(())
}

#[test]
fn sorting_occurs_before_chunking_without_reordering_saved_rows() -> Result<()> {
    let (dir, mut record) = fixture(vec![
        row("r3", "", "", "", "", "smith", "2012-01-01"),
        row("r2", "", "", "", "", "Smith", "2010-01-01"),
        row("r1", "", "", "", "", "smith", "2010-01-01"),
        row("r4", "", "", "", "", "Adams", "bad"),
        row("r5", "", "", "", "", "", "2000-01-01"),
    ])?;
    for entry in record["entries"].as_array_mut().unwrap() {
        entry["checks"] = json!([{"finding_key":"check-000001","code":"test.ok","stage":"prepare","status":"pass","message":"ok"}]);
        entry["effective_checks"] = json!([{"finding_key":"check-000001","status":"pass","disabled":false,"policy_reason":null}]);
        entry["next_finding_sequence"] = json!(2);
    }
    let mut config = Config::default();
    config.bundling.bundle_size = 2;
    bundles::bundle(dir.path(), &mut record, &config, 1)?;
    assert_eq!(
        members(&record, "deliverable"),
        vec![vec!["r3", "r2"], vec!["r1", "r4"], vec!["r5"]]
    );
    config.bundling.sort_by = "last_name_dob".into();
    bundles::bundle(dir.path(), &mut record, &config, 2)?;
    assert_eq!(
        members(&record, "deliverable"),
        vec![vec!["r4", "r1"], vec!["r2", "r3"], vec!["r5"]]
    );
    assert_eq!(
        record["entries"]
            .as_array()
            .unwrap()
            .iter()
            .map(|e| e["row_key"].as_str().unwrap())
            .collect::<Vec<_>>(),
        vec!["r3", "r2", "r1", "r4", "r5"]
    );
    for bundle in record["bundles"].as_array().unwrap() {
        assert!(bundle.get("csv").is_none());
        let bundle_members: Vec<_> = bundle["members"]
            .as_array()
            .unwrap()
            .iter()
            .map(|value| value.as_str().unwrap().to_owned())
            .collect();
        let pdf = Document::load(dir.path().join(bundle["path"].as_str().unwrap()))?;
        let pdf_members: Vec<_> = pdf
            .get_pages()
            .values()
            .map(|id| {
                String::from_utf8(
                    pdf.get_object(*id)
                        .unwrap()
                        .as_dict()
                        .unwrap()
                        .get(b"TestRow")
                        .unwrap()
                        .as_str()
                        .unwrap()
                        .to_vec(),
                )
                .unwrap()
            })
            .collect();
        assert_eq!(pdf_members, bundle_members);
        for (page, key) in bundle["members"].as_array().unwrap().iter().enumerate() {
            let entry = record["entries"]
                .as_array()
                .unwrap()
                .iter()
                .find(|e| e["row_key"] == *key)
                .unwrap();
            assert_eq!(entry["bundle"]["notice_start_page"], (page + 1) as u64);
            assert_eq!(entry["bundle"]["notice_end_page"], (page + 1) as u64);
        }
    }
    Ok(())
}

#[test]
fn board_conflicts_are_scoped_to_selected_dimension_and_disabled_bundles() -> Result<()> {
    let (dir, mut record) = fixture(vec![
        row("r1", "s1", "School", "b1", "North", "A", "2010-01-01"),
        row("r2", "s2", "School", "b1", "South", "B", "2010-01-01"),
        row("r3", "s3", "School", "", "", "C", "2010-01-01"),
        row("r4", "s4", "School", "", "Example Board", "D", "2010-01-01"),
    ])?;
    let mut config = Config::default();
    config.bundling.group_by = json!("board");
    bundles::bundle(dir.path(), &mut record, &config, 1)?;
    assert!(
        record["entries"]
            .as_array()
            .unwrap()
            .iter()
            .all(|e| e["checks"].as_array().unwrap().is_empty())
    );
    config.bundling.bundle_size = 100;
    bundles::bundle(dir.path(), &mut record, &config, 1)?;
    assert_eq!(members(&record, "review").len(), 3);
    assert_eq!(
        record["entries"][3]["checks"][0]["code"],
        "delivery.board_identity_fallback"
    );
    assert_eq!(record["entries"][3]["routing"], "deliverable");
    Ok(())
}

#[test]
fn school_name_fallback_separates_boards_including_ambiguous_ids() -> Result<()> {
    let (dir, mut record) = fixture(vec![
        row("r1", "", "Central", "b1", "North", "A", "2010-01-01"),
        row("r2", "", "Central", "b2", "South", "B", "2010-01-01"),
        row("r3", "", "Central", "b3", "North", "C", "2010-01-01"),
        row("r4", "", "Central", "b3", "South", "D", "2010-01-01"),
        row("r5", "", "Central", "b4", "North", "E", "2010-01-01"),
        row("r6", "", "Central", "b4", "South", "F", "2010-01-01"),
        row("r7", "", "Central", "b5", "North", "G", "2010-01-01"),
        row("r8", "", "Central", "b5", "South", "H", "2010-01-01"),
        row("r9", "", "Central", "b4", "", "I", "2010-01-01"),
        row("r10", "", "Central", "b5", "", "J", "2010-01-01"),
    ])?;
    record["entries"][5]["hold"] = json!({"reason":"review"});
    record["entries"][7]["original"]["status"] = json!("failed");
    let mut config = Config::default();
    config.bundling.bundle_size = 100;
    config.bundling.group_by = json!("school");
    bundles::bundle(dir.path(), &mut record, &config, 2)?;
    let normal = members(&record, "deliverable");
    for key in ["r1", "r2", "r3", "r4", "r5", "r7", "r9", "r10"] {
        assert!(normal.contains(&vec![key.into()]));
    }
    assert_eq!(record["entries"][5]["routing"], "withheld");
    assert_eq!(record["entries"][7]["routing"], "failed");
    assert!(
        record["entries"][2]["checks"]
            .as_array()
            .unwrap()
            .iter()
            .all(|check| check["code"] != "delivery.board_identity_conflict")
    );
    Ok(())
}
