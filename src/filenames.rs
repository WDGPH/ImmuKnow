//! Supported filename templates and deterministic, portable artifact basenames.
use anyhow::{Result, bail, ensure};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};
use unicode_normalization::UnicodeNormalization;

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
#[serde(default, deny_unknown_fields)]
pub struct Settings {
    pub individual: Option<Template>,
    pub bundle: Option<Template>,
    pub review_bundle: Option<Template>,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Template {
    pub template: String,
}
const INDIVIDUAL: &[&str] = &[
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
    "row_key",
    "school_id",
    "board_id",
    "notice_variant",
];
const BUNDLE: &[&str] = &[
    "school",
    "school_id",
    "board",
    "board_id",
    "language_code",
    "notice_variant",
    "bundle_number",
    "route",
];
impl Settings {
    pub fn validate(&self) -> Result<()> {
        for (name, pattern, fields) in [
            ("individual", &self.individual, INDIVIDUAL),
            ("bundle", &self.bundle, BUNDLE),
            ("review_bundle", &self.review_bundle, BUNDLE),
        ] {
            if let Some(pattern) = pattern {
                let template = &pattern.template;
                ensure!(
                    !template.trim().is_empty(),
                    "filenames.{name}.template must be nonempty"
                );
                ensure!(
                    !template.contains(['/', '\\', ':']) && !template.chars().any(char::is_control),
                    "filenames.{name}.template must be a basename, without paths or control characters"
                );
                ensure!(
                    ![".pdf", ".csv"]
                        .iter()
                        .any(|ext| template.to_lowercase().ends_with(ext)),
                    "filenames.{name}.template is a stem; omit the file extension"
                );
                crate::formatting::expand(template, |field| {
                    ensure!(
                        fields.contains(&field),
                        "Unsupported filename field {field} for {name}"
                    );
                    Ok("value".into())
                })?;
            }
        }
        Ok(())
    }
    pub(crate) fn bundle_template(&self, review: bool) -> Option<String> {
        if review {
            self.review_bundle
                .as_ref()
                .map(|p| p.template.clone())
                .or_else(|| {
                    self.bundle
                        .as_ref()
                        .map(|p| format!("review_{}", p.template))
                })
        } else {
            self.bundle.as_ref().map(|p| p.template.clone())
        }
    }
}
fn string(v: &Value) -> String {
    v.as_str().unwrap_or("").to_owned()
}
pub(crate) fn values(notice: &Value) -> BTreeMap<&'static str, String> {
    let mut values = crate::input::password_values(notice);
    values.extend([
        ("row_key", string(&notice["row_key"])),
        ("school_id", string(&notice["school"]["id"])),
        ("board_id", string(&notice["board"]["id"])),
        ("notice_variant", string(&notice["version_id"])),
    ]);
    values
}
pub(crate) fn bundle_values(
    entries: &[Value],
    indices: &[usize],
    number: usize,
    route: &str,
) -> BTreeMap<&'static str, String> {
    let mut common = values(&entries[indices[0]]["notice"]);
    for &index in &indices[1..] {
        let next = values(&entries[index]["notice"]);
        common.retain(|field, value| next.get(field) == Some(value));
    }
    common.insert("bundle_number", format!("{number:02}"));
    common.insert("route", route.to_owned());
    common
}
// Conservative Unicode basenames: keep letters/digits, underscores and hyphens;
// all other runs become one underscore. NFC and lowercase also reserve equivalent names.
fn safe_stem(value: &str) -> String {
    let mut out = String::new();
    for ch in value.nfc().flat_map(char::to_lowercase) {
        let ch = if ch.is_alphanumeric() || matches!(ch, '-' | '_') {
            ch
        } else {
            '_'
        };
        if ch != '_' || !out.ends_with('_') {
            out.push(ch);
        }
    }
    let out = out.trim_matches(['_', '-']);
    let reserved = matches!(out, "con" | "prn" | "aux" | "nul" | "conin" | "conout")
        || ["com", "lpt"].iter().any(|prefix| {
            out.strip_prefix(prefix).is_some_and(|n| {
                matches!(
                    n,
                    "0" | "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9" | "¹" | "²" | "³"
                )
            })
        });
    let mut out = if reserved {
        format!("_{out}")
    } else {
        out.to_owned()
    };
    truncate(&mut out, 160);
    out
}
fn truncate(value: &mut String, max: usize) {
    let mut end = max.min(value.len());
    while !value.is_char_boundary(end) {
        end -= 1;
    }
    value.truncate(end);
}
#[derive(Default)]
pub(crate) struct Names {
    used: BTreeSet<String>,
}
pub(crate) struct Name {
    pub stem: String,
    pub warning: Option<String>,
}
impl Names {
    pub(crate) fn resolve(
        &mut self,
        template: Option<&str>,
        values: &BTreeMap<&str, String>,
        fallback: &str,
        identity: &str,
    ) -> Name {
        let (mut stem, warning) = match template {
            None => (fallback.to_owned(), None),
            Some(template) => {
                let expanded = crate::formatting::expand(template, |field| {
                    match values
                        .get(field)
                        .filter(|value| !safe_stem(value).is_empty())
                    {
                        Some(value) => Ok(value.clone()),
                        None => bail!(
                            "Filename field {field} is missing or differs between bundle members"
                        ),
                    }
                })
                .map(|value| safe_stem(&value));
                match expanded {
                    Ok(stem) if !stem.is_empty() => (stem, None),
                    other => (
                        fallback.to_owned(),
                        Some(match other {
                            Err(error) => error.to_string(),
                            _ => "Filename template has no usable characters".into(),
                        }),
                    ),
                }
            }
        };
        if !self.used.insert(stem.to_lowercase()) {
            let base = stem.clone();
            let suffix = safe_stem(identity);
            let mut attempt = 0usize;
            loop {
                let suffix = if attempt == 0 {
                    suffix.clone()
                } else {
                    format!("{suffix}-{attempt}")
                };
                let mut prefix = base.clone();
                truncate(&mut prefix, 160usize.saturating_sub(suffix.len() + 1));
                stem = format!("{prefix}_{suffix}");
                if self.used.insert(stem.to_lowercase()) {
                    break;
                }
                attempt += 1;
            }
        }
        Name { stem, warning }
    }
}
pub(crate) fn warning(message: &str, path: &str) -> Value {
    json!({"code":"output.filename_fallback","stage":"output","status":"warn",
        "message":format!("{message}. A fallback filename was used."), "measurements":{"path":path}})
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn scopes_braces_and_paths_are_validated() {
        for pattern in [
            "{client_id",
            "{unknown}",
            "../{client_id}",
            "a\\b",
            "C:name",
            "name.pdf",
            "",
        ] {
            let settings = Settings {
                individual: Some(Template {
                    template: pattern.into(),
                }),
                ..Settings::default()
            };
            assert!(settings.validate().is_err(), "{pattern}");
        }
        assert!(
            Settings {
                bundle: Some(Template {
                    template: "{last_name}".into()
                }),
                ..Settings::default()
            }
            .validate()
            .is_err()
        );
        let mut names = Names::default();
        let name = names.resolve(
            Some("{{draft}}_{name}"),
            &BTreeMap::from([("name", "ÉLODIE / Example".into())]),
            "row-1",
            "row-1",
        );
        assert_eq!(name.stem, "draft_élodie_example");
        assert!(name.warning.is_none());
    }
    #[test]
    fn filenames_are_portable_bounded_and_never_overwritten() {
        let mut names = Names::default();
        let values = BTreeMap::new();
        assert_eq!(
            names.resolve(Some("CON"), &values, "row-1", "row-1").stem,
            "_con"
        );
        assert_eq!(
            names.resolve(Some("A B"), &values, "row-1", "row-1").stem,
            "a_b"
        );
        assert_eq!(
            names.resolve(Some("a_b"), &values, "row-2", "row-2").stem,
            "a_b_row-2"
        );
        assert!(
            names
                .resolve(Some("{first_name}"), &values, "row-3", "row-3")
                .warning
                .is_some()
        );
        let first = names.resolve(Some(&"É".repeat(300)), &values, "row-4", "row-4");
        let second = names.resolve(Some(&"É".repeat(300)), &values, "row-5", "row-5");
        assert!(first.stem.len() <= 160 && second.stem.len() <= 160);
        assert_ne!(first.stem, second.stem);
        assert_eq!(safe_stem("É"), safe_stem("E\u{301}"));
    }
    #[test]
    fn mixed_bundle_facts_do_not_use_the_first_member() {
        let entries = vec![
            json!({"notice":{"school":{"name":"A"}}}),
            json!({"notice":{"school":{"name":"B"}}}),
        ];
        let values = bundle_values(&entries, &[0, 1], 101, "review");
        assert!(!values.contains_key("school"));
        assert_eq!(values["bundle_number"], "101");
        let name = Names::default().resolve(
            Some("{school}_{bundle_number}"),
            &values,
            "review-0001",
            "review-0001",
        );
        assert_eq!(name.stem, "review-0001");
        assert!(name.warning.is_some());
    }
}
