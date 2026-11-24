//! ISPA scope for supplied overdue diseases; upstream systems assess whether doses are overdue.
//! Keep in step with `resources/typst/src/ispa.typ`, which remains the fallback for notices
//! prepared without this classification.
//! https://www.ontario.ca/page/vaccines-children-school
//! https://www.ontario.ca/laws/regulation/900645 (Table 1)
use chrono::{Datelike, NaiveDate};
use serde_json::{Value, json};
use std::collections::BTreeSet;

const ALWAYS: &[&str] = &[
    "Diphtheria",
    "Tetanus",
    "Polio",
    "Measles",
    "Mumps",
    "Rubella",
    "Pertussis",
    "Meningococcal",
];

pub struct Classification {
    pub status: &'static str,
    pub overdue: Vec<Value>,
    pub undetermined: Vec<String>,
    /// Facts whose absence left ISPA applicability undecided: `date_of_birth` or `date_as_of`.
    pub missing: BTreeSet<&'static str>,
}

impl Classification {
    pub fn notice_value(&self) -> Value {
        json!({
            "status": self.status,
            "overdue_diseases": self.overdue,
            "undetermined_diseases": self.undetermined,
        })
    }
}

fn ymd(y: i32, m: u32, d: u32) -> NaiveDate {
    NaiveDate::from_ymd_opt(y, m, d).unwrap()
}

/// ISPA applies from junior kindergarten: births in or before the year the client turns 4
/// during the school year (September to August) containing `as_of`. Younger children are
/// CCEYA ages. There is no upper age limit.
fn school_age(birth: NaiveDate, as_of: NaiveDate) -> bool {
    let school_year = as_of.year() - i32::from(as_of.month() < 9);
    birth.year() <= school_year - 4
}

fn in_scope(disease: &str, birth: NaiveDate) -> bool {
    ALWAYS.contains(&disease) || (disease == "Varicella" && birth >= ymd(2010, 1, 1))
}

pub fn classify(
    overdue: &[Value],
    birth: Option<NaiveDate>,
    as_of: Option<NaiveDate>,
) -> Classification {
    let disease = |entry: &Value| entry["disease"].as_str().unwrap_or("").to_owned();
    let mut result = Classification {
        status: "no_ispa_overdue",
        overdue: vec![],
        undetermined: vec![],
        missing: BTreeSet::new(),
    };
    let (Some(birth), Some(as_of)) = (birth, as_of) else {
        result.status = "ispa_unknown";
        if birth.is_none() {
            result.missing.insert("date_of_birth");
        }
        if as_of.is_none() {
            result.missing.insert("date_as_of");
        }
        // Any disease ISPA can designate, since applicability and cohort are both unknown.
        for name in overdue.iter().map(disease) {
            if (ALWAYS.contains(&name.as_str()) || name == "Varicella")
                && !result.undetermined.contains(&name)
            {
                result.undetermined.push(name);
            }
        }
        return result;
    };
    if !school_age(birth, as_of) {
        result.status = "ispa_not_applicable";
        return result;
    }
    result.overdue = overdue
        .iter()
        .filter(|entry| in_scope(&disease(entry), birth))
        .cloned()
        .collect();
    if !result.overdue.is_empty() {
        result.status = "ispa_overdue";
    }
    result
}

fn iso(value: &Value) -> Option<NaiveDate> {
    let text = value.as_str()?;
    NaiveDate::parse_from_str(text, "%Y-%m-%d")
        .ok()
        .filter(|d| d.format("%Y-%m-%d").to_string() == text)
}

/// A prepared notice's ISPA status, classifying notices prepared before `notice.ispa` existed.
/// Rows without a notice have no status.
pub fn status(notice: &Value) -> String {
    if notice.is_null() {
        return String::new();
    }
    if let Some(status) = notice["ispa"]["status"].as_str() {
        return status.to_owned();
    }
    let overdue = notice["overdue_diseases"]
        .as_array()
        .map_or(&[][..], Vec::as_slice);
    classify(
        overdue,
        iso(&notice["client_data"]["date_of_birth_iso"]),
        iso(&notice["date_as_of"]),
    )
    .status
    .to_owned()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn date(text: &str) -> Option<NaiveDate> {
        Some(NaiveDate::parse_from_str(text, "%Y-%m-%d").unwrap())
    }
    fn diseases(names: &[&str]) -> Vec<Value> {
        names
            .iter()
            .map(|d| json!({"disease": d, "dose": null}))
            .collect()
    }
    fn scoped(names: &[&str], birth: &str, as_of: &str) -> Vec<String> {
        classify(&diseases(names), date(birth), date(as_of))
            .overdue
            .iter()
            .map(|e| e["disease"].as_str().unwrap().to_owned())
            .collect()
    }

    #[test]
    fn designated_diseases_include_meningococcal_for_every_cohort() {
        let all = &["Measles", "Meningococcal", "Hepatitis B"];
        assert_eq!(
            scoped(all, "2001-03-04", "2026-11-01"),
            ["Measles", "Meningococcal"]
        );
        assert_eq!(
            scoped(all, "2020-03-04", "2026-11-01"),
            ["Measles", "Meningococcal"]
        );
    }

    #[test]
    fn varicella_starts_with_the_2010_cohort() {
        assert!(scoped(&["Varicella"], "2009-12-31", "2026-11-01").is_empty());
        assert_eq!(
            scoped(&["Varicella"], "2010-01-01", "2026-11-01"),
            ["Varicella"]
        );
    }

    #[test]
    fn applicability_starts_with_the_junior_kindergarten_cohort() {
        let status =
            |birth, as_of| classify(&diseases(&["Measles"]), date(birth), date(as_of)).status;
        // The 2022 cohort enters JK in September 2026, before its fourth birthday.
        assert_eq!(status("2022-12-31", "2026-08-31"), "ispa_not_applicable");
        assert_eq!(status("2022-12-31", "2026-09-01"), "ispa_overdue");
        assert_eq!(status("2023-01-01", "2027-08-31"), "ispa_not_applicable");
        assert_eq!(status("2023-01-01", "2027-09-01"), "ispa_overdue");
        // Adult pupils remain in scope.
        assert_eq!(status("1990-06-01", "2026-11-01"), "ispa_overdue");
        let c = classify(
            &diseases(&["Measles"]),
            date("2024-01-01"),
            date("2026-11-01"),
        );
        assert!(c.overdue.is_empty() && c.undetermined.is_empty() && c.missing.is_empty());
    }

    #[test]
    fn missing_dates_leave_applicability_undetermined() {
        let c = classify(
            &diseases(&["Varicella", "Measles", "Varicella", "HPV"]),
            None,
            date("2026-11-01"),
        );
        assert_eq!(c.status, "ispa_unknown");
        assert!(c.overdue.is_empty());
        assert_eq!(c.undetermined, ["Varicella", "Measles"]);
        assert_eq!(c.missing, BTreeSet::from(["date_of_birth"]));

        let c = classify(&[], date("2015-05-01"), None);
        assert_eq!(c.status, "ispa_unknown");
        assert!(c.undetermined.is_empty());
        assert_eq!(c.missing, BTreeSet::from(["date_as_of"]));
    }

    #[test]
    fn nothing_in_scope() {
        for overdue in [vec![], diseases(&["Hepatitis B", "HPV"])] {
            let c = classify(&overdue, date("2012-01-01"), date("2026-11-01"));
            assert_eq!(c.status, "no_ispa_overdue");
            assert!(c.overdue.is_empty() && c.undetermined.is_empty());
        }
    }

    #[test]
    fn scoped_entries_keep_dose_details() {
        let entry = json!({"disease": "Polio", "dose": null, "dose_raw": "x"});
        let c = classify(
            &[entry.clone(), json!({"disease": "Polio", "dose": 2})],
            date("2015-01-01"),
            date("2026-11-01"),
        );
        assert_eq!(c.overdue, [entry, json!({"disease": "Polio", "dose": 2})]);
    }

    #[test]
    fn status_prefers_prepared_and_classifies_earlier_runs() {
        assert_eq!(status(&Value::Null), "");
        assert_eq!(
            status(&json!({"ispa": {"status": "ispa_unknown"}})),
            "ispa_unknown"
        );
        let earlier = |birth: &str| {
            json!({"client_data": {"date_of_birth_iso": birth}, "date_as_of": "2026-11-01",
                "overdue_diseases": diseases(&["Mumps"])})
        };
        assert_eq!(status(&earlier("2015-01-01")), "ispa_overdue");
        assert_eq!(status(&earlier("2024-01-01")), "ispa_not_applicable");
        assert_eq!(status(&earlier("")), "ispa_unknown");
        assert_eq!(status(&earlier("2015-02-30")), "ispa_unknown");
    }
}
