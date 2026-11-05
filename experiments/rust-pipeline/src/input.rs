//! Factual CSV preparation. Typst continues to own wording, layout and QR codes.
use anyhow::{Context, Result, bail, ensure};
use chrono::{Datelike, NaiveDate};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::Path,
};

#[derive(Deserialize, Default)]
#[serde(deny_unknown_fields, default)]
pub struct Config {
    pub date_as_of: String,
    pub date_of_delivery: String,
    pub bundling: Bundling,
    pub encryption: Encryption,
    pub school_validation: School,
    pub pipeline: Pipeline,
    pub typst: Typst,
    pub validation: BTreeMap<String, Value>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields, default)]
pub struct Bundling {
    pub bundle_size: usize,
    pub group_by: Value,
}
impl Default for Bundling {
    fn default() -> Self {
        Self {
            bundle_size: 100,
            group_by: Value::Null,
        }
    }
}
#[derive(Deserialize, Default)]
#[serde(deny_unknown_fields, default)]
pub struct Encryption {
    pub enabled: bool,
    pub password: Password,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields, default)]
pub struct Password {
    pub template: String,
}
impl Default for Password {
    fn default() -> Self {
        Self {
            template: "{date_of_birth_iso_compact}".into(),
        }
    }
}
#[derive(Deserialize, Default)]
#[serde(deny_unknown_fields, default)]
pub struct School {
    pub enabled: bool,
    pub reference_file: Option<String>,
    pub target_phu: String,
    pub column_prefix: String,
}
#[derive(Deserialize, Default)]
#[serde(deny_unknown_fields, default)]
pub struct Pipeline {
    pub after_run: AfterRun,
}
#[derive(Deserialize, Default)]
#[serde(deny_unknown_fields, default)]
pub struct AfterRun {
    pub remove_artifacts: bool,
}
#[derive(Deserialize, Default)]
#[serde(deny_unknown_fields, default)]
pub struct Typst {
    pub bin: Option<String>,
    pub timeouts_seconds: Option<Value>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Assignment {
    client_id: String,
    template: String,
    experiment_id: Option<String>,
    experiment_arm: Option<String>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Catalog {
    schema_version: u32,
    versions: BTreeMap<String, Version>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Version {
    kind: String,
    requires: Option<String>,
}
pub struct Prepared {
    pub source: Value,
    pub notice: Value,
    pub checks: Vec<Value>,
    pub assignment: Value,
}
type Row = BTreeMap<String, String>;
fn get<'a>(r: &'a Row, k: &str) -> &'a str {
    r.get(k).map(String::as_str).unwrap_or("")
}
pub fn check(code: &str, status: &str, message: &str) -> Value {
    json!({"code":code,"stage":"preparation","status":status,"message":message})
}
pub fn config(path: &Path) -> Result<Config> {
    let c: Config = serde_saphyr::from_str(&fs::read_to_string(path)?)?;
    for d in [&c.date_as_of, &c.date_of_delivery] {
        if !d.is_empty() {
            date(d)?;
        }
    }
    ensure!(
        !c.school_validation.enabled,
        "Rust experiment does not yet support school-reference validation"
    );
    ensure!(
        !c.pipeline.after_run.remove_artifacts,
        "Rust experiment retains artifacts; remove_artifacts is unsupported"
    );
    ensure!(
        c.validation.is_empty(),
        "Rust experiment supports default validation policy only"
    );
    ensure!(
        c.typst.timeouts_seconds.is_none(),
        "In-process Rust experiment cannot enforce per-notice hard deadlines"
    );
    ensure!(
        c.bundling.bundle_size > 0,
        "Rust experiment requires a positive bundle_size"
    );
    ensure!(
        c.bundling.group_by.is_null(),
        "Rust experiment supports size-only grouping"
    );
    if c.encryption.enabled {
        ensure!(
            c.encryption.password.template == "{date_of_birth_iso_compact}",
            "Rust experiment currently supports the compact DOB password only"
        );
    }
    Ok(c)
}
fn date(text: &str) -> Result<NaiveDate> {
    let d =
        NaiveDate::parse_from_str(text, "%Y-%m-%d").context("Invalid date; expected YYYY-MM-DD")?;
    ensure!(
        d.format("%Y-%m-%d").to_string() == text,
        "Date must use YYYY-MM-DD"
    );
    Ok(d)
}
fn coverage(known: bool, unknown: bool) -> &'static str {
    match (known, unknown) {
        (true, true) => "mixed",
        (true, false) => "all_present",
        _ => "all_absent",
    }
}
fn history(raw: &str, reference: &BTreeMap<String, Value>) -> Result<(Vec<Value>, bool, bool)> {
    let raw = raw.trim_matches([' ', '\t', '\r', '\n']);
    if raw.is_empty() || matches!(raw, "-;" | "-  -;") {
        return Ok((vec![], false, false));
    }
    ensure!(raw.ends_with(';'), "History must end with ';'");
    let mut doses = vec![];
    let (mut known, mut unknown) = (false, false);
    for (i, fragment) in raw[..raw.len() - 1].split(';').enumerate() {
        let p: Vec<_> = fragment
            .trim_matches([' ', '\t', '\r', '\n'])
            .split(" - ")
            .collect();
        ensure!(
            (2..=3).contains(&p.len()),
            "History fragment {} has invalid fields",
            i + 1
        );
        date(p[0]).with_context(|| format!("Invalid history date in fragment {}", i + 1))?;
        let agent = p[1];
        ensure!(
            !agent.is_empty()
                && agent.trim() == agent
                && !agent.contains(['\t', '\r', '\n'])
                && !agent.contains(" -")
                && !agent.contains("- "),
            "Invalid history agent in fragment {}",
            i + 1
        );
        let validity = if p.len() == 2 {
            unknown = true;
            "unknown"
        } else {
            known = true;
            match p[2] {
                "Valid" => "valid",
                "Invalid" => "invalid",
                _ => bail!("History validity must be exactly Valid or Invalid"),
            }
        };
        doses.push((p[0].to_string(), agent.to_string(), validity));
    }
    doses.sort_by(|a, b| a.0.cmp(&b.0));
    let mut output: Vec<Value> = vec![];
    let mut index = BTreeMap::new();
    for (given, agent, validity) in doses {
        let key = (given.clone(), agent.clone());
        if let Some(&i) = index.get(&key) {
            let item: &mut Value = &mut output[i];
            let old = item["validity"].as_str().unwrap();
            if validity == "unknown" || old == "invalid" {
                item["validity"] = json!(validity);
            }
            continue;
        }
        let mapped = reference.get(&agent);
        let diseases = match mapped {
            Some(Value::String(s)) => json!([s]),
            Some(Value::Array(a)) => {
                let mut seen = BTreeSet::new();
                json!(
                    a.iter()
                        .filter(|x| seen.insert(x.to_string()))
                        .collect::<Vec<_>>()
                )
            }
            None => json!([]),
            _ => bail!("Invalid vaccine reference"),
        };
        let display = agent
            .strip_suffix("-unspecified")
            .or_else(|| agent.strip_suffix(" unspecified"))
            .filter(|s| !s.is_empty())
            .map(|s| format!("{s}*"))
            .unwrap_or(agent.clone());
        index.insert(key, output.len());
        output.push(json!({"date_given":given,"agent":agent,"display_name":display,"diseases":diseases,"mapping_known":mapped.is_some(),"validity":validity}));
    }
    Ok((output, known, unknown))
}
fn tokens(raw: &str) -> Vec<String> {
    raw.split(';')
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(|s| s.replace(['\'', '"'], "").trim().to_string())
        .collect()
}
fn normalize(s: &str, n: &BTreeMap<String, String>) -> String {
    n.get(s.trim()).cloned().unwrap_or_else(|| s.trim().into())
}

pub fn prepare(
    csv_path: &Path,
    assignments: &Path,
    config_dir: &Path,
    templates: &Path,
    core: &Path,
    c: &Config,
) -> Result<Vec<Prepared>> {
    let schema: Value = crate::read_json(&core.join("immuknow/schemas/input_schema.json"))?;
    let fields = schema["fields"]
        .as_array()
        .context("Invalid input schema")?;
    let content = fs::read_to_string(csv_path).context("Rust experiment requires UTF-8 CSV")?;
    ensure!(
        !content
            .chars()
            .any(|c| (c < ' ' && !matches!(c, '\t' | '\r' | '\n'))
                || ('\u{7f}'..='\u{9f}').contains(&c)),
        "CSV contains control characters"
    );
    let mut reader =
        csv::ReaderBuilder::new().from_reader(content.trim_start_matches('\u{feff}').as_bytes());
    let headers = reader.headers()?.clone();
    let mut seen = BTreeSet::new();
    for h in &headers {
        ensure!(
            !h.is_empty()
                && h.trim() == h
                && !h.contains(['\r', '\n'])
                && seen.insert(h.to_string()),
            "CSV has invalid/repeated headers"
        );
    }
    ensure!(!seen.contains("reader"), "Rename reader to intended_reader");
    for f in fields {
        if f["constraints"]["required"] == true {
            ensure!(
                seen.contains(f["name"].as_str().unwrap()),
                "Missing required column {}",
                f["name"]
            );
        }
    }
    let mut rows = vec![];
    let mut sources = vec![];
    for r in reader.records() {
        let r = r?;
        let source: Row = headers
            .iter()
            .zip(r.iter())
            .map(|(k, v)| (k.into(), v.into()))
            .collect();
        let row: Row = source
            .iter()
            .map(|(k, v)| (k.clone(), v.trim().into()))
            .collect();
        sources.push(json!(source));
        rows.push(row);
    }
    ensure!(!rows.is_empty(), "CSV contains no clients");
    let mut ids = BTreeSet::new();
    for r in &rows {
        let id = get(r, "client_id");
        ensure!(
            id.is_empty() || ids.insert(id.to_string()),
            "Duplicate nonblank client_id"
        );
        ensure!(
            matches!(get(r, "intended_reader"), "" | "student" | "guardian"),
            "Invalid intended_reader"
        );
    }
    let assignments: Vec<Assignment> = crate::read_json(assignments)?;
    let mut by_id = BTreeMap::new();
    for a in assignments {
        ensure!(
            !a.client_id.is_empty() && by_id.insert(a.client_id.clone(), a).is_none(),
            "Blank or ambiguous assignment client_id"
        );
    }
    let catalog: Catalog = serde_saphyr::from_str(&fs::read_to_string(
        config_dir.join("notice_versions.yaml"),
    )?)?;
    ensure!(
        catalog.schema_version == 1 && !catalog.versions.is_empty(),
        "Unsupported notice catalog"
    );
    let normalization: BTreeMap<String, String> =
        crate::read_json(&config_dir.join("disease_normalization.json"))?;
    let reference: BTreeMap<String, Value> =
        crate::read_json(&config_dir.join("vaccine_reference.json"))?;
    for (k, v) in &reference {
        ensure!(
            !k.is_empty()
                && (v.as_str().is_some_and(|s| !s.is_empty())
                    || v.as_array().is_some_and(|a| a
                        .iter()
                        .all(|x| x.as_str().is_some_and(|s| !s.is_empty())))),
            "Invalid vaccine reference"
        );
    }
    let mut histories = vec![];
    let (mut known, mut unknown) = (false, false);
    for (i, r) in rows.iter().enumerate() {
        let (h, k, u) = history(get(r, "imms_given"), &reference)
            .with_context(|| format!("Source row {}", i + 1))?;
        histories.push((h, k, u));
        known |= k;
        unknown |= u;
    }
    let dataset_coverage = coverage(known, unknown);
    let oiid_coverage = coverage(
        rows.iter().any(|r| !get(r, "oiid").is_empty()),
        rows.iter().any(|r| get(r, "oiid").is_empty()),
    );
    let mut result = vec![];
    for (i, ((r, source), (history, hk, hu))) in rows.iter().zip(sources).zip(histories).enumerate()
    {
        let id = get(r, "client_id");
        let row_key = format!("row-{:06}", i + 1);
        let a = by_id
            .get(id)
            .with_context(|| format!("Missing assignment for {row_key}"))?;
        ensure!(
            Path::new(&a.template).file_name().and_then(|n| n.to_str()) == Some(&a.template),
            "Assignment template must be a basename"
        );
        let parts: Vec<_> = a.template.rsplitn(3, '.').collect();
        ensure!(
            parts.len() == 3
                && parts[0] == "typ"
                && matches!(parts[1], "en" | "fr")
                && !parts[2].is_empty()
                && parts[2]
                    .bytes()
                    .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'-'))
                && parts[2].as_bytes()[0].is_ascii_alphanumeric(),
            "Invalid template identity"
        );
        let (version, language) = (parts[2], parts[1]);
        ensure!(
            templates.join(&a.template).is_file(),
            "Assigned template is missing"
        );
        let version_info = catalog
            .versions
            .get(version)
            .context("Assigned version absent from catalog")?;
        ensure!(
            matches!(
                version_info.kind.as_str(),
                "overdue" | "affirmative" | "informational"
            ),
            "Unknown notice kind"
        );
        let mut checks = vec![];
        for field in [
            "client_id",
            "first_name",
            "last_name",
            "school_name",
            "board_name",
        ] {
            if get(r, field).is_empty() {
                checks.push(check(
                    &format!("source.{field}_missing"),
                    "warn",
                    &format!("Source {} is missing", field.replace('_', " ")),
                ));
            }
        }
        if !id.is_empty() && (id.len() != 10 || !id.bytes().all(|b| b.is_ascii_digit())) {
            checks.push(check(
                "source.client_id_format",
                "fail",
                "Source Panorama client ID must contain ten digits (0–9)",
            ));
        }
        let street = [
            get(r, "street_address_line_1"),
            get(r, "street_address_line_2"),
        ]
        .into_iter()
        .filter(|s| !s.is_empty())
        .collect::<Vec<_>>()
        .join(" ");
        if [
            &street,
            get(r, "city"),
            get(r, "province"),
            get(r, "postal_code"),
        ]
        .contains(&"")
        {
            let mut c = check(
                "source.address_incomplete",
                "warn",
                "Source mailing address is incomplete",
            );
            c["component"] = json!("address");
            checks.push(c);
        }
        let birth = date(get(r, "date_of_birth")).ok();
        let dob = birth.map(|d| d.to_string()).unwrap_or_default();
        let age = birth
            .zip(date(&c.date_of_delivery).ok())
            .map(|(b, d)| {
                d.year() - b.year() - i32::from((d.month(), d.day()) < (b.month(), b.day()))
            })
            .filter(|a| *a >= 0);
        if age.is_none() {
            checks.push(check(
                "source.age_unknown",
                "warn",
                "Age is unknown; source birth date or delivery date is absent or unusable",
            ));
        }
        let mut overdue = vec![];
        for token in tokens(get(r, "overdue_disease")) {
            ensure!(
                !token.is_empty(),
                "Rust experiment rejects unusable overdue fragments"
            );
            if let Some((d, dose)) = token.rsplit_once(" -") {
                let d = normalize(d, &normalization);
                ensure!(!d.is_empty(), "Missing overdue disease");
                if let Ok(n) = dose.trim().parse::<u64>() {
                    if n > 0 {
                        overdue.push(json!({"disease":d,"dose":n}));
                        continue;
                    }
                }
                checks.push(check(
                    "source.overdue_unusable",
                    "warn",
                    "Invalid overdue dose; displaying disease without a dose number.",
                ));
                overdue.push(json!({"disease":d,"dose":null,"dose_raw":dose.trim()}));
            } else {
                overdue.push(json!({"disease":normalize(&token,&normalization),"dose":null}));
            }
        }
        let agents = tokens(get(r, "overdue_agent"));
        ensure!(
            agents.iter().all(|a| !a.is_empty()),
            "Rust experiment rejects unusable overdue agent fragments"
        );
        let required: BTreeSet<_> = overdue
            .iter()
            .map(|d| d["disease"].as_str().unwrap().to_string())
            .collect();
        let mut covered = BTreeSet::new();
        let mut unmapped = BTreeSet::new();
        for agent in &agents {
            match reference.get(agent) {
                Some(Value::String(s)) => {
                    covered.insert(normalize(s, &normalization));
                }
                Some(Value::Array(a)) => {
                    covered.extend(
                        a.iter()
                            .map(|x| normalize(x.as_str().unwrap(), &normalization)),
                    );
                }
                _ => {
                    unmapped.insert(agent.clone());
                }
            }
        }
        let missing: Vec<_> = required.difference(&covered).cloned().collect();
        let extra: Vec<_> = covered.difference(&required).cloned().collect();
        ensure!(
            missing.is_empty(),
            "Forecasted agents do not cover all overdue diseases for {row_key}"
        );
        let (status, message) = if !extra.is_empty() || !unmapped.is_empty() {
            (
                "warn",
                "Forecasted agents cover the overdue diseases, but add other diseases or include an agent absent from the lookup.",
            )
        } else if !required.is_empty() || !agents.is_empty() {
            ("pass", "Forecasted agents cover all overdue diseases.")
        } else {
            (
                "not_applicable",
                "No overdue diseases or forecasted agents were supplied.",
            )
        };
        let mut forecast = check("data.forecast_coverage", status, message);
        forecast["measurements"] =
            json!({"missing_diseases":missing,"extra_diseases":extra,"unmapped_agents":unmapped});
        checks.push(forecast);
        let rule = version_info
            .requires
            .as_deref()
            .unwrap_or(match version_info.kind.as_str() {
                "overdue" => "has_overdue",
                "affirmative" => "no_overdue",
                _ => "any",
            });
        let applicable = match rule {
            "has_overdue" => !overdue.is_empty(),
            "has_overdue_agents" => !agents.is_empty(),
            "no_overdue" => overdue.is_empty(),
            "any" => true,
            _ => bail!("Unknown catalog applicability rule"),
        };
        checks.push(check(
            "assignment.applicable",
            if applicable { "pass" } else { "fail" },
            if applicable {
                "Selected notice is applicable."
            } else {
                "Selected notice is not applicable to this client."
            },
        ));
        let first = get(r, "first_name");
        let last = get(r, "last_name");
        let full_name = [first, last]
            .into_iter()
            .filter(|s| !s.is_empty())
            .collect::<Vec<_>>()
            .join(" ");
        let notice = json!({"schema_version":1,"row_key":row_key,"client_id":id,"oiid":get(r,"oiid"),"oiid_coverage":oiid_coverage,"template":a.template,"version_id":version,"language":language,"intended_reader":if get(r,"intended_reader").is_empty(){None}else{Some(get(r,"intended_reader"))},"client_data":{"name":full_name,"first_name":first,"last_name":last,"first_initial":first.chars().take(1).collect::<String>(),"last_initial":last.chars().take(1).collect::<String>(),"address":street,"city":get(r,"city"),"province":get(r,"province"),"postal_code":get(r,"postal_code"),"date_of_birth_iso":dob,"age":age,"school":get(r,"school_name")},"school":{"name":get(r,"school_name"),"id":get(r,"school_id")},"board":{"name":get(r,"board_name"),"id":get(r,"board_id")},"date_of_delivery":c.date_of_delivery,"date_as_of":c.date_as_of,"overdue_diseases":overdue,"overdue_agents":agents,"history":history,"has_immunization_records":!history.is_empty(),"validity_coverage":dataset_coverage,"history_validity_coverage":coverage(hk,hu)});
        result.push(Prepared{source,notice,checks,assignment:json!({"template":a.template,"version_id":version,"language":language,"notice_kind":version_info.kind,"experiment_id":a.experiment_id,"experiment_arm":a.experiment_arm})});
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn history_syntax_and_dedup() {
        let r = BTreeMap::new();
        for s in [
            "2020-01-01 - MMR",
            "2020-01-01 - MMR - valid;",
            "2020-02-30 - MMR;",
            ";2020-01-01 - MMR;",
        ] {
            assert!(history(s, &r).is_err(), "{s}");
        }
        let (h, k, u) = history(
            "2020-01-01 - MMR - Invalid;2020-01-01 - MMR - Valid;2020-01-01 - MMR;",
            &r,
        )
        .unwrap();
        assert_eq!(h.len(), 1);
        assert_eq!(h[0]["validity"], "unknown");
        assert!(k && u);
    }
}
