//! Factual CSV preparation. Typst continues to own wording, layout and QR codes.
use anyhow::{Context, Result, bail, ensure};
use chrono::{Datelike, NaiveDate};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    path::{Path, PathBuf},
};

#[derive(Deserialize, Serialize, Default)]
#[serde(deny_unknown_fields, default)]
pub struct Config {
    pub date_as_of: String,
    pub date_of_delivery: String,
    pub date_due: Option<String>,
    pub date_of_suspension: Option<String>,
    pub allowed_duplicate_client_ids: Vec<String>,
    pub bundling: Bundling,
    pub filenames: crate::filenames::Settings,
    pub encryption: Encryption,
    pub school_validation: School,
    pub pipeline: Pipeline,
    pub typst: Typst,
    pub validation: BTreeMap<String, Value>,
}
#[derive(Deserialize, Serialize)]
#[serde(deny_unknown_fields, default)]
pub struct Bundling {
    pub bundle_size: usize,
    pub group_by: Value,
    pub sort_by: String,
}
impl Default for Bundling {
    fn default() -> Self {
        Self {
            bundle_size: 0,
            group_by: Value::Null,
            sort_by: "source".into(),
        }
    }
}
#[derive(Deserialize, Serialize, Default)]
#[serde(deny_unknown_fields, default)]
pub struct Encryption {
    pub enabled: bool,
    pub password: Password,
}
#[derive(Deserialize, Serialize, Default)]
#[serde(deny_unknown_fields, default)]
pub struct Password {
    pub template: String,
}
#[derive(Deserialize, Serialize, Default)]
#[serde(deny_unknown_fields, default)]
pub struct School {
    pub enabled: bool,
    pub reference_file: Option<String>,
    pub target_phu: String,
    pub column_prefix: Option<String>,
}
#[derive(Deserialize, Serialize, Default)]
#[serde(deny_unknown_fields, default)]
pub struct Pipeline {
    pub after_run: AfterRun,
}
#[derive(Deserialize, Serialize, Default)]
#[serde(deny_unknown_fields, default)]
pub struct AfterRun {
    pub remove_artifacts: bool,
}
#[derive(Deserialize, Serialize, Default)]
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
pub enum RowPreparation {
    Ready(Prepared),
    Failed {
        row_key: String,
        assignment: Value,
        checks: Vec<Value>,
    },
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
    let source = fs::read_to_string(path)?;
    // String deserialization can coerce YAML numbers; inspect their native types
    // first so an unquoted ID cannot silently lose leading zeros.
    let value: Value = parse_yaml(&source)?;
    if let Some(ids) = value.get("allowed_duplicate_client_ids") {
        ensure!(
            ids.as_array()
                .is_some_and(|items| items.iter().all(Value::is_string)),
            "allowed_duplicate_client_ids must be a list of strings; quote numeric IDs"
        );
    }
    let c: Config = parse_yaml(&source)?;
    validate_dates(&c)?;
    validate_allowed_duplicates(&c)?;
    ensure!(
        !c.pipeline.after_run.remove_artifacts,
        "pipeline.after_run.remove_artifacts is retired; remove the run directory manually when appropriate"
    );
    ensure!(
        c.school_validation.column_prefix.is_none(),
        "school_validation.column_prefix is retired; native findings use fixed measurement names"
    );
    if c.school_validation.enabled {
        ensure!(
            !c.school_validation.target_phu.trim().is_empty(),
            "school_validation.target_phu must be nonempty"
        );
    }
    if c.encryption.enabled {
        ensure!(
            !c.encryption.password.template.is_empty(),
            "encryption.password.template is required when encryption is enabled"
        );
    }
    if !c.encryption.password.template.is_empty() {
        format_password(&c.encryption.password.template, &BTreeMap::new(), false)?;
    }
    ensure!(
        c.typst.bin.is_none() && c.typst.timeouts_seconds.is_none(),
        "typst.bin and typst.timeouts_seconds are retired; remove them from parameters.yaml"
    );
    validate_bundling(&c)?;

    Ok(c)
}

fn validate_allowed_duplicates(config: &Config) -> Result<()> {
    let mut seen = BTreeSet::new();
    for id in &config.allowed_duplicate_client_ids {
        ensure!(
            !id.is_empty() && id.trim() == id && seen.insert(id),
            "allowed_duplicate_client_ids must contain unique nonblank strings without surrounding whitespace"
        );
    }
    Ok(())
}

/// Compare the dates that are actually supplied, including across omitted fields.
fn validate_dates(config: &Config) -> Result<()> {
    let dates = [
        ("date_as_of", Some(config.date_as_of.as_str())),
        ("date_of_delivery", Some(config.date_of_delivery.as_str())),
        ("date_due", config.date_due.as_deref()),
        ("date_of_suspension", config.date_of_suspension.as_deref()),
    ];
    let mut previous = None;
    for (name, value) in dates {
        let Some(value) = value.filter(|value| !value.is_empty()) else {
            continue;
        };
        let parsed = date(value).with_context(|| format!("Invalid {name}"))?;
        if let Some((earlier_name, earlier)) = previous {
            let same_day_delivery = earlier_name == "date_as_of" && name == "date_of_delivery";
            ensure!(
                parsed > earlier || (same_day_delivery && parsed == earlier),
                "{name} must be {} {earlier_name}",
                if same_day_delivery {
                    "on or after"
                } else {
                    "after"
                }
            );
        }
        previous = Some((name, parsed));
    }
    Ok(())
}
/// Parse the fields used to group notices into bundles.
pub fn grouping_fields(value: &Value) -> Result<Vec<String>> {
    let fields: Vec<&str> = match value {
        Value::Null => vec![],
        Value::String(s) if s.eq_ignore_ascii_case("size") => vec![],
        Value::String(s) => vec![s],
        Value::Array(a) => a
            .iter()
            .map(|v| v.as_str().context("Grouping fields must be strings"))
            .collect::<Result<_>>()?,
        _ => bail!("Grouping must be a field or a list of fields"),
    };
    let mut seen = BTreeSet::new();
    fields
        .into_iter()
        .map(|field| {
            let field = field.to_ascii_lowercase();
            ensure!(
                matches!(
                    field.as_str(),
                    "school" | "board" | "language" | "page_count" | "notice_variant"
                ),
                "Unknown grouping field: {field}"
            );
            ensure!(
                seen.insert(field.clone()),
                "Duplicate grouping field: {field}"
            );
            Ok(field)
        })
        .collect()
}
/// Validate fixed notice length and return the page count when enabled.
pub fn fixed_pages(config: &Config) -> Result<Option<u64>> {
    let Some(value) = config.validation.get("notice_length") else {
        return Ok(None);
    };
    let fields = value
        .as_object()
        .context("validation.notice_length must be a mapping")?;
    ensure!(
        fields
            .keys()
            .all(|k| matches!(k.as_str(), "enabled" | "count" | "unit")),
        "Unknown notice_length field"
    );
    let enabled = match fields.get("enabled") {
        Some(v) => v
            .as_bool()
            .context("notice_length.enabled must be boolean")?,
        None => false,
    };
    let count = fields
        .get("count")
        .map(|v| {
            v.as_u64()
                .filter(|n| *n > 0)
                .context("notice_length.count must be positive")
        })
        .transpose()?;
    if enabled || fields.contains_key("unit") {
        ensure!(
            fields.get("unit").and_then(Value::as_str) == Some("pages"),
            "notice_length.unit must be pages"
        );
    }
    if enabled {
        ensure!(
            config.bundling.bundle_size > 0,
            "Fixed notice length requires bundling"
        );
        Ok(Some(count.context("notice_length.count is required")?))
    } else {
        Ok(None)
    }
}
/// Apply the same bundle settings to new runs and saved runs.
pub fn validate_bundling(config: &Config) -> Result<()> {
    ensure!(
        config
            .validation
            .keys()
            .all(|k| matches!(k.as_str(), "rules" | "clients" | "notice_length")),
        "validation supports only rules, clients and notice_length"
    );
    config.filenames.validate()?;
    grouping_fields(&config.bundling.group_by)?;
    ensure!(
        matches!(config.bundling.sort_by.as_str(), "source" | "last_name_dob"),
        "bundling.sort_by must be source or last_name_dob"
    );
    fixed_pages(config)?;
    Ok(())
}
fn parse_yaml<T: serde::de::DeserializeOwned>(content: &str) -> Result<T> {
    // Reject merge keys: the YAML library applies explicit overrides before duplicate
    // detection, which otherwise hides repeated settings.
    let mut options = serde_saphyr::Options::default();
    options.merge_keys = serde_saphyr::MergeKeyPolicy::Error;
    serde_saphyr::from_str_with_options(content, options)
        .map_err(|_| anyhow::anyhow!("Invalid YAML, repeated fields, or unsupported merge keys"))
}
const PASSWORD_FIELDS: &[&str] = &[
    "client_id",
    "first_name",
    "last_name",
    "first_initial",
    "last_initial",
    "name",
    "date_of_birth_iso",
    "date_of_birth_iso_compact",
    "school",
    "board",
    "street_address",
    "city",
    "province",
    "postal_code",
    "language_code",
];
fn format_password(
    template: &str,
    values: &BTreeMap<&str, String>,
    require_values: bool,
) -> Result<String> {
    let out = crate::formatting::expand(template, |field| {
        ensure!(
            PASSWORD_FIELDS.contains(&field),
            "Invalid password template fields or formatting"
        );
        let value = values.get(field).map(String::as_str).unwrap_or("");
        ensure!(
            !require_values || !value.is_empty(),
            "A required password field is missing"
        );
        Ok(value.to_owned())
    })
    .context("Invalid password template fields or formatting")?;
    ensure!(
        !require_values || !out.is_empty(),
        "The generated password is empty"
    );
    Ok(out)
}
pub(crate) fn password_values(n: &Value) -> BTreeMap<&'static str, String> {
    let d = &n["client_data"];
    let v = |x: &Value| x.as_str().unwrap_or("").to_owned();
    let dob = v(&d["date_of_birth_iso"]);
    BTreeMap::from([
        ("client_id", v(&n["client_id"])),
        ("first_name", v(&d["first_name"])),
        ("last_name", v(&d["last_name"])),
        ("first_initial", v(&d["first_initial"])),
        ("last_initial", v(&d["last_initial"])),
        ("name", v(&d["name"])),
        ("date_of_birth_iso", dob.clone()),
        ("date_of_birth_iso_compact", dob.replace('-', "")),
        ("school", v(&n["school"]["name"])),
        ("board", v(&n["board"]["name"])),
        ("street_address", v(&d["address"])),
        ("city", v(&d["city"])),
        ("province", v(&d["province"])),
        ("postal_code", v(&d["postal_code"])),
        ("language_code", v(&n["language"])),
    ])
}
pub fn password(prepared: &Prepared, config: &Config) -> Result<String> {
    format_password(
        &config.encryption.password.template,
        &password_values(&prepared.notice),
        true,
    )
}
fn decode_csv(bytes: &[u8], encoding: Option<&str>) -> Result<String> {
    let utf = || std::str::from_utf8(bytes).map(str::to_owned).ok();
    let cp = || {
        let (value, _, errors) = encoding_rs::WINDOWS_1252.decode(bytes);
        if errors {
            None
        } else {
            Some(value.into_owned())
        }
    };
    let latin = || bytes.iter().map(|&b| char::from(b)).collect::<String>();
    match encoding {
        Some("utf-8-sig") => utf().context("CSV is not valid UTF-8"),
        Some("cp1252") => cp().context("CSV is not valid Windows-1252"),
        Some("latin-1") => Ok(latin()),
        None => Ok(utf().or_else(cp).unwrap_or_else(latin)),
        _ => bail!("CSV encoding must be utf-8-sig, cp1252 or latin-1"),
    }
}
fn detect_delimiter(content: &str) -> u8 {
    let first = content
        .lines()
        .find(|line| !line.trim().is_empty())
        .unwrap_or("");
    b"|\t;,"
        .iter()
        .copied()
        .max_by_key(|&delimiter| {
            let mut reader = csv::ReaderBuilder::new()
                .delimiter(delimiter)
                .has_headers(false)
                .from_reader(first.as_bytes());
            reader
                .records()
                .next()
                .and_then(Result::ok)
                .map(|r| r.len())
                .unwrap_or(0)
        })
        .unwrap_or(b',')
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
            .unwrap_or_else(|| agent.clone());
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

pub enum Selection {
    Manifest(PathBuf),
    Single(PathBuf),
}
pub struct PrepareOptions<'a> {
    pub csv: &'a Path,
    pub selection: &'a Selection,
    pub config_dir: &'a Path,
    pub templates: &'a Path,
    pub resources: &'a Path,
    pub encoding: Option<&'a str>,
}
// csv::Reader deliberately accepts malformed quoting; reject source corruption first.
fn strict_quotes(content: &str, delimiter: u8) -> Result<()> {
    #[derive(Clone, Copy)]
    enum State {
        Start,
        Unquoted,
        Quoted,
        Closed,
    }
    let mut state = State::Start;
    for byte in content.bytes() {
        state = match (state, byte) {
            (State::Start, b'"') => State::Quoted,
            (State::Start | State::Unquoted | State::Closed, b)
                if b == delimiter || b == b'\n' || b == b'\r' =>
            {
                State::Start
            }
            (State::Start, _) => State::Unquoted,
            (State::Quoted, b'"') => State::Closed,
            (State::Closed, b'"') => State::Quoted,
            (State::Closed, _) => bail!("CSV contains text after a closing quote"),
            (other, _) => other,
        };
    }
    ensure!(
        !matches!(state, State::Quoted),
        "CSV contains an unterminated quoted field"
    );
    Ok(())
}
fn read_source(path: &Path, encoding: Option<&str>) -> Result<(Vec<String>, Vec<Row>)> {
    let content = decode_csv(&fs::read(path)?, encoding)?;
    ensure!(
        !content
            .chars()
            .any(|c| (c < ' ' && !matches!(c, '\t' | '\r' | '\n'))
                || ('\u{7f}'..='\u{9f}').contains(&c)),
        "CSV contains control characters"
    );
    let content = content.trim_start_matches('\u{feff}');
    let delimiter = detect_delimiter(content);
    strict_quotes(content, delimiter)?;
    let mut reader = csv::ReaderBuilder::new()
        .delimiter(delimiter)
        .from_reader(content.as_bytes());
    let headers = reader.headers()?.clone();
    let mut seen = BTreeSet::new();
    for h in &headers {
        ensure!(
            !h.is_empty()
                && h.trim() == h
                && !h.contains(['\r', '\n'])
                && seen.insert(h.to_string()),
            "CSV has invalid or repeated headers"
        );
    }
    let mut rows = vec![];
    for r in reader.records() {
        let r = r?;
        rows.push(
            headers
                .iter()
                .zip(r.iter())
                .map(|(k, v)| (k.to_owned(), v.to_owned()))
                .collect(),
        );
    }
    Ok((headers.iter().map(str::to_owned).collect(), rows))
}
pub fn source_rows(path: &Path, encoding: Option<&str>) -> Result<Vec<Value>> {
    Ok(read_source(path, encoding)?
        .1
        .into_iter()
        .map(|row| json!(row))
        .collect())
}
pub fn prepare(options: &PrepareOptions<'_>, c: &Config) -> Result<Vec<RowPreparation>> {
    let config_dir = options.config_dir;
    let templates = options.templates;
    let schema: Value = crate::read_json(&options.resources.join("schemas/input_schema.json"))?;
    let fields = schema["fields"]
        .as_array()
        .context("Invalid input schema")?;
    let (headers, sources) = read_source(options.csv, options.encoding)?;
    let seen: BTreeSet<_> = headers.iter().cloned().collect();
    ensure!(!seen.contains("reader"), "Rename reader to intended_reader");
    ensure!(
        !seen.contains("imms_given"),
        "Rename the CSV column imms_given to immunizations_given; do not include both columns"
    );
    for f in fields {
        if f["constraints"]["required"] == true {
            ensure!(
                seen.contains(f["name"].as_str().unwrap()),
                "Missing required column {}",
                f["name"]
            );
        }
    }
    let rows: Vec<Row> = sources
        .iter()
        .map(|source| {
            source
                .iter()
                .map(|(k, v)| (k.clone(), v.trim().to_owned()))
                .collect()
        })
        .collect();
    let sources: Vec<Value> = sources.into_iter().map(|source| json!(source)).collect();
    ensure!(!rows.is_empty(), "CSV contains no clients");
    let mut counts = BTreeMap::<String, usize>::new();
    for r in &rows {
        let id = get(r, "client_id");
        if !id.is_empty() {
            *counts.entry(id.to_owned()).or_default() += 1;
        }
    }
    for (id, count) in &counts {
        ensure!(
            *count < 2 || c.allowed_duplicate_client_ids.contains(id),
            "Duplicate nonblank client_id {id}; add an intentional duplicate to allowed_duplicate_client_ids"
        );
    }
    let mut by_id = BTreeMap::new();
    let single = match options.selection {
        Selection::Manifest(path) => {
            let assignments: Vec<Assignment> = crate::read_json(path)?;
            for mut a in assignments {
                a.client_id = a.client_id.trim().to_owned();
                a.template = a.template.trim().to_owned();
                ensure!(
                    !a.client_id.is_empty() && by_id.insert(a.client_id.clone(), a).is_none(),
                    "Blank or ambiguous assignment client_id"
                );
            }
            None
        }
        Selection::Single(path) => {
            ensure!(path.is_file(), "Selected template is missing");
            Some(Assignment {
                client_id: String::new(),
                template: path
                    .file_name()
                    .and_then(|x| x.to_str())
                    .context("Invalid template path")?
                    .to_owned(),
                experiment_id: None,
                experiment_arm: None,
            })
        }
    };
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
    let school = if c.school_validation.enabled {
        let file = c
            .school_validation
            .reference_file
            .as_deref()
            .filter(|s| !s.trim().is_empty());
        let path = match file {
            None => config_dir.join("school_reference.json"),
            Some(file) if Path::new(file).is_absolute() => PathBuf::from(file),
            Some(file) => config_dir.join(file),
        };
        let bytes = fs::read(&path).context("Unable to read school reference")?;
        let data: Value = crate::parse_json(&bytes)?;
        let mapping = data
            .get("phus")
            .and_then(|v| v.get(&c.school_validation.target_phu))
            .and_then(Value::as_object)
            .context("School reference does not contain selected PHU")?;
        ensure!(
            mapping.iter().all(|(k, v)| !k.is_empty() && v.is_string()),
            "Invalid school reference mapping"
        );
        Some((
            mapping.clone(),
            crate::hash(&bytes),
            path.file_name()
                .unwrap_or_default()
                .to_string_lossy()
                .to_string(),
        ))
    } else {
        None
    };
    let mut histories = vec![];
    let (mut known, mut unknown) = (false, false);
    for r in &rows {
        let parsed = history(get(r, "immunizations_given"), &reference);
        if let Ok((_, k, u)) = &parsed {
            known |= *k;
            unknown |= *u;
        }
        histories.push(parsed);
    }
    let dataset_coverage = if histories.iter().any(Result::is_err) {
        "incomplete"
    } else {
        coverage(known, unknown)
    };
    let oiid_coverage = coverage(
        rows.iter().any(|r| !get(r, "oiid").is_empty()),
        rows.iter().any(|r| get(r, "oiid").is_empty()),
    );
    let extra_manifest_rows = single.is_none() && by_id.keys().any(|id| !counts.contains_key(id));
    let mut result = vec![];
    for (i, ((r, source), history_result)) in rows.iter().zip(sources).zip(histories).enumerate() {
        let id = get(r, "client_id");
        let row_key = format!("row-{:06}", i + 1);
        let a = match &single {
            Some(a) => a,
            None => by_id
                .get(id)
                .with_context(|| format!("Missing assignment for {row_key}"))?,
        };
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
            match options.selection {
                Selection::Manifest(_) => templates.join(&a.template).is_file(),
                Selection::Single(path) => path.is_file(),
            },
            "Assigned template is missing"
        );
        let assignment = json!({"template":a.template,"version_id":version,"language":language,"experiment_id":a.experiment_id,"experiment_arm":a.experiment_arm});
        let mut failures = vec![];
        if let Err(error) = &history_result {
            failures.push(check(
                "source.history_unusable",
                "fail",
                &format!("Invalid immunization history: {error}"),
            ));
        }
        if !matches!(get(r, "intended_reader"), "" | "student" | "guardian") {
            failures.push(check(
                "source.intended_reader_invalid",
                "fail",
                "Intended reader must be student, guardian, or blank.",
            ));
        }
        if !failures.is_empty() {
            result.push(RowPreparation::Failed {
                row_key,
                assignment,
                checks: failures,
            });
            continue;
        }
        let (history, hk, hu) = history_result.expect("History failure was recorded");
        let mut checks = vec![];
        if let Some(count) = counts.get(id).filter(|count| **count > 1) {
            checks.push(check(
                "data.duplicate_client_id",
                "warn",
                &format!("This allowed client ID appears in {count} source rows. All rows are retained and share the same notice assignment; review each row."),
            ));
        }
        if extra_manifest_rows {
            checks.push(check(
                "assignment.extra_manifest_row",
                "warn",
                "The assignment file contains clients who are not in the CSV.",
            ));
        }
        if let Some((mapping, hash, filename)) = &school {
            let raw = get(r, "school_name");
            let (name, id) = raw.rsplit_once(" - ").unwrap_or((raw, ""));
            let normalized = name
                .split_whitespace()
                .collect::<Vec<_>>()
                .join(" ")
                .to_uppercase();
            let id = id.trim();
            let direct = mapping.get(&normalized).and_then(Value::as_str);
            let reverse = mapping
                .iter()
                .find(|(_, v)| !id.is_empty() && v.as_str() == Some(id));
            let (status, reason, matched_name, matched_id) = match direct {
                Some(mid) if id.is_empty() => ("warn", "name_only", normalized.as_str(), mid),
                Some(mid) if id == mid => ("pass", "exact", normalized.as_str(), mid),
                Some(mid) => ("fail", "id_mismatch", normalized.as_str(), mid),
                None => match reverse {
                    Some((name, _)) => ("fail", "id_only", name.as_str(), id),
                    None => ("fail", "not_found", "", ""),
                },
            };
            let message = match reason {
                "exact" => format!("School name and ID match the reference: {raw}."),
                "name_only" => format!(
                    "School name matches {matched_name}, but the source has no school ID. The reference ID is {matched_id}."
                ),
                "id_mismatch" => format!(
                    "School ID does not match: {raw}. The reference ID for {matched_name} is {matched_id}."
                ),
                "id_only" => format!(
                    "School ID {id} belongs to {matched_name} in the reference, but the source school name is {name}."
                ),
                _ => format!("School was not found in the configured reference: {raw}."),
            };
            let mut finding = check("data.school_match", status, &message);
            finding["measurements"] = json!({"reference_file": filename, "reference_sha256": hash, "target_phu":c.school_validation.target_phu, "source_school":raw,"match_type": if reason == "exact" {"exact"} else if reason == "not_found" {"no_match"} else {"inexact"},"reason":reason,"matched_name":matched_name,"matched_id":matched_id});
            checks.push(finding);
        }
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
        let missing_address: Vec<_> = [
            ("street address", street.as_str()),
            ("city", get(r, "city")),
            ("province", get(r, "province")),
            ("postal code", get(r, "postal_code")),
        ]
        .into_iter()
        .filter_map(|(name, value)| value.is_empty().then_some(name))
        .collect();
        if !missing_address.is_empty() {
            let mut c = check(
                "source.address_incomplete",
                "warn",
                &format!(
                    "Source mailing address is incomplete. Missing: {}.",
                    missing_address.join(", ")
                ),
            );
            c["component"] = json!("address");
            c["measurements"] = json!({"missing_fields": missing_address});
            checks.push(c);
        }
        let birth = date(get(r, "date_of_birth")).ok();
        let dob = birth.map_or_default(|d| d.to_string());
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
        let mut disease_occurrences = BTreeMap::<String, Vec<String>>::new();
        for token in tokens(get(r, "overdue_disease")) {
            if token.is_empty() {
                checks.push(check(
                    "source.overdue_unusable",
                    "warn",
                    "Unusable overdue disease fragment; original source value retained.",
                ));
                continue;
            }
            if let Some((d, dose)) = token.rsplit_once(" -") {
                let d = normalize(d, &normalization);
                if d.is_empty() {
                    checks.push(check(
                        "source.overdue_unusable",
                        "warn",
                        "Unusable overdue disease; original source value retained.",
                    ));
                    continue;
                }
                disease_occurrences
                    .entry(d.clone())
                    .or_default()
                    .push(token.clone());
                if let Ok(n) = dose.trim().parse::<u64>()
                    && n > 0
                {
                    overdue.push(json!({"disease":d,"dose":n}));
                    continue;
                }
                checks.push(check(
                    "source.overdue_unusable",
                    "warn",
                    "Invalid overdue dose; displaying disease without a dose number.",
                ));
                overdue.push(json!({"disease":d,"dose":null,"dose_raw":dose.trim()}));
            } else {
                let disease = normalize(&token, &normalization);
                disease_occurrences
                    .entry(disease.clone())
                    .or_default()
                    .push(token.clone());
                overdue.push(json!({"disease":disease,"dose":null}));
            }
        }
        let agents: Vec<_> = tokens(get(r, "overdue_agent"))
            .into_iter()
            .filter(|a| {
                if a.is_empty() {
                    checks.push(check(
                        "source.overdue_unusable",
                        "warn",
                        "Unusable overdue agent fragment; original source value retained.",
                    ));
                    false
                } else {
                    true
                }
            })
            .collect();
        let disease_repeats: Vec<_> = disease_occurrences.into_iter()
            .filter(|(_, fragments)| fragments.len() > 1)
            .map(|(disease, fragments)| json!({"normalized_disease":disease,"count":fragments.len(),"source_fragments":fragments}))
            .collect();
        if !disease_repeats.is_empty() {
            let mut warning = check(
                "data.duplicate_overdue_diseases",
                "warn",
                "Some overdue diseases appear more than once after normalization. Review the source entries, including dose numbers.",
            );
            warning["measurements"] =
                json!({"source_value":source["overdue_disease"],"groups":disease_repeats});
            checks.push(warning);
        }
        let mut agent_counts = BTreeMap::<&str, usize>::new();
        for agent in &agents {
            *agent_counts.entry(agent).or_default() += 1;
        }
        let agent_repeats: Vec<_> = agent_counts
            .into_iter()
            .filter(|(_, count)| *count > 1)
            .map(|(agent, count)| json!({"agent":agent,"count":count}))
            .collect();
        if !agent_repeats.is_empty() {
            let mut warning = check(
                "data.duplicate_overdue_agents",
                "warn",
                "Some overdue agents appear more than once. Repetition may be expected when an agent covers multiple diseases; review the source entries.",
            );
            warning["measurements"] =
                json!({"source_value":source["overdue_agent"],"groups":agent_repeats});
            checks.push(warning);
        }
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
        let first = get(r, "first_name");
        let last = get(r, "last_name");
        let full_name = [first, last]
            .into_iter()
            .filter(|s| !s.is_empty())
            .collect::<Vec<_>>()
            .join(" ");
        let notice = json!({
            "schema_version": 2,
            "row_key": row_key,
            "client_id": id,
            "oiid": get(r, "oiid"),
            "oiid_coverage": oiid_coverage,
            "template": a.template,
            "version_id": version,
            "language": language,
            "intended_reader": if get(r, "intended_reader").is_empty() {
                None
            } else {
                Some(get(r, "intended_reader"))
            },
            "client_data": {
                "name": full_name,
                "first_name": first,
                "last_name": last,
                "first_initial": first.chars().take(1).collect::<String>(),
                "last_initial": last.chars().take(1).collect::<String>(),
                "address": street,
                "city": get(r, "city"),
                "province": get(r, "province"),
                "postal_code": get(r, "postal_code"),
                "date_of_birth_iso": dob,
                "age": age,
                "school": get(r, "school_name")
            },
            "school": {"name": get(r, "school_name"), "id": get(r, "school_id")},
            "board": {"name": get(r, "board_name"), "id": get(r, "board_id")},
            "date_of_delivery": c.date_of_delivery,
            "date_as_of": c.date_as_of,
            "date_due": c.date_due,
            "date_of_suspension": c.date_of_suspension,
            "overdue_diseases": overdue,
            "overdue_agents": agents,
            "forecast_coverage": {"missing_diseases":missing,"extra_diseases":extra,"unmapped_agents":unmapped},
            "history": history,
            "has_immunization_records": !history.is_empty(),
            "validity_coverage": dataset_coverage,
            "history_validity_coverage": coverage(hk, hu)
        });
        result.push(RowPreparation::Ready(Prepared {
            source,
            notice,
            checks,
            assignment,
        }));
    }
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn duplicate_id_allowlist_requires_unique_trimmed_strings() {
        let temp = tempfile::tempdir().unwrap();
        let path = temp.path().join("parameters.yaml");
        for source in [
            "{}",
            "allowed_duplicate_client_ids: ['0000000001', '0000000002']",
        ] {
            fs::write(&path, source).unwrap();
            assert!(config(&path).is_ok(), "rejected {source}");
        }
        for source in [
            "allowed_duplicate_client_ids: ['']",
            "allowed_duplicate_client_ids: ['   ']",
            "allowed_duplicate_client_ids: [' 0000000001']",
            "allowed_duplicate_client_ids: ['0000000001', '0000000001']",
            "allowed_duplicate_client_ids: [1234567890]",
            "allowed_duplicate_client_ids: null",
        ] {
            fs::write(&path, source).unwrap();
            assert!(config(&path).is_err(), "accepted {source}");
        }
    }
    #[test]
    fn project_dates_are_optional_but_ordered_when_present() {
        for source in [
            "{}",
            "date_as_of: '2026-11-01'\ndate_of_delivery: '2026-11-01'",
            "date_due: null\ndate_of_suspension: null",
            "date_due: ''\ndate_of_suspension: ''",
            "date_as_of: '2026-11-01'\ndate_of_delivery: '2026-11-15'\ndate_due: '2026-11-30'\ndate_of_suspension: '2026-12-01'",
            "date_of_delivery: '2026-11-15'\ndate_of_suspension: '2026-12-01'",
        ] {
            let config: Config = parse_yaml(source).unwrap();
            assert!(validate_dates(&config).is_ok(), "rejected {source}");
        }
        for source in [
            "date_as_of: '2026-11-15'\ndate_of_delivery: '2026-11-01'",
            "date_of_delivery: '2026-11-15'\ndate_due: '2026-11-15'",
            "date_due: '2026-12-01'\ndate_of_suspension: '2026-11-30'",
            "date_of_delivery: '2026-12-01'\ndate_of_suspension: '2026-11-30'",
            "date_as_of: '2026-12-01'\ndate_due: '2026-11-30'",
            "date_due: '2026-02-30'",
            "date_of_suspension: '2026-13-01'",
        ] {
            let config: Config = parse_yaml(source).unwrap();
            assert!(validate_dates(&config).is_err(), "accepted {source}");
        }
    }
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
    #[test]
    fn input_decoding_and_delimiters() {
        assert_eq!(
            decode_csv(b"\xef\xbb\xbfa,b", None)
                .unwrap()
                .trim_start_matches('\u{feff}'),
            "a,b"
        );
        assert_eq!(decode_csv(b"Caf\xe9", None).unwrap(), "Café");
        assert!(decode_csv(b"\xff", Some("utf-8-sig")).is_err());
        assert_eq!(detect_delimiter("a;b;c\n1;2;3"), b';');
        assert_eq!(detect_delimiter("single"), b',');
    }
    #[test]
    fn password_templates_require_valid_fields_and_values() {
        let values = BTreeMap::from([
            ("first_initial", "É".to_owned()),
            ("client_id", "123".to_owned()),
        ]);
        assert_eq!(
            format_password("{first_initial}-{client_id}", &values, true).unwrap(),
            "É-123"
        );
        assert!(format_password("{date_of_birth}", &values, false).is_err());
        assert!(format_password("{first_name}", &values, true).is_err());
        assert!(format_password("{client_id", &values, false).is_err());
    }
    #[test]
    fn bundle_order_is_explicit_and_survives_saved_settings() {
        let mut config: Config = serde_json::from_value(json!({})).unwrap();
        assert_eq!(config.bundling.sort_by, "source");
        assert!(validate_bundling(&config).is_ok());
        config.bundling.sort_by = "last_name_dob".into();
        let saved = serde_json::to_value(&config).unwrap();
        let restored: Config = serde_json::from_value(saved).unwrap();
        assert_eq!(restored.bundling.sort_by, "last_name_dob");
        assert!(validate_bundling(&restored).is_ok());
        config.bundling.sort_by = "last_name".into();
        assert!(validate_bundling(&config).is_err());
    }
    #[test]
    fn yaml_rejects_nested_duplicates_and_merges() {
        assert!(
            parse_yaml::<Value>(
                "validation:\n  rules:\n    abc: {enabled: true, enabled: false}\n"
            )
            .is_err()
        );
        assert!(
            parse_yaml::<Value>(
                "defaults: &d {enabled: true}\nvalidation: {<<: *d, enabled: false}\n"
            )
            .is_err()
        );
    }
}
